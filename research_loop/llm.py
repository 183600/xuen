"""极简 OpenAI 兼容 Chat Completions 客户端（流式 + 工具调用）。"""
from __future__ import annotations

import json
import random
import time
from typing import Callable, Dict, List, Optional

import requests

from .config import ModelConfig
from .ui import ui


class LLMError(RuntimeError):
    pass


class _Retryable(Exception):
    pass


class LLMClient:
    def __init__(self, cfg: ModelConfig):
        self.cfg = cfg
        self.api_key = cfg.resolve_api_key()
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        if self.api_key:
            self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})
        if cfg.extra_headers:
            self.session.headers.update(cfg.extra_headers)
        self.endpoint = cfg.base_url.rstrip("/") + "/chat/completions"

    # ------------------------------------------------------------------
    def chat(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        *,
        on_text: Optional[Callable[[str], None]] = None,
        on_reasoning: Optional[Callable[[str], None]] = None,
    ) -> Dict:
        last = None
        for attempt in range(4):
            try:
                return self._chat_once(messages, tools, on_text, on_reasoning)
            except _Retryable as e:
                last = e
                delay = min(20.0, (2 ** attempt) * 1.5 + random.random())
                ui.warn(f"LLM 请求失败（{e}），{delay:.1f}s 后重试（{attempt + 1}/4）")
                time.sleep(delay)
        raise LLMError(f"LLM 请求重试耗尽：{last}")

    # ------------------------------------------------------------------
    def _chat_once(self, messages, tools, on_text, on_reasoning) -> Dict:
        payload: Dict = {
            "model": self.cfg.name,
            "messages": messages,
            "temperature": self.cfg.temperature,
            "max_tokens": self.cfg.max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            resp = self.session.post(
                self.endpoint,
                json=payload,
                stream=self.cfg.stream,
                timeout=(30, self.cfg.request_timeout),
            )
        except requests.RequestException as e:
            raise _Retryable(f"网络错误: {e}") from e

        if resp.status_code != 200:
            body = resp.text[:400].replace("\n", " ")
            if resp.status_code in (408, 409, 429) or 500 <= resp.status_code < 600:
                raise _Retryable(f"HTTP {resp.status_code}: {body}")
            raise LLMError(f"HTTP {resp.status_code}: {body}")

        if not self.cfg.stream:
            try:
                data = resp.json()
                msg = data["choices"][0]["message"]
            except (ValueError, KeyError, IndexError, TypeError) as e:
                raise _Retryable(f"响应解析失败: {e}") from e
            return self._normalize(msg)

        return self._stream(resp, on_text, on_reasoning)

    # ------------------------------------------------------------------
    def _stream(self, resp, on_text, on_reasoning) -> Dict:
        content: List[str] = []
        tool_acc: Dict[int, Dict] = {}
        emitted = False
        try:
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw or not raw.startswith("data:"):
                    continue
                payload = raw[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}

                piece = delta.get("content")
                if piece:
                    content.append(piece)
                    emitted = True
                    if on_text:
                        on_text(piece)

                rp = delta.get("reasoning_content") or delta.get("reasoning")
                if rp:  # DeepSeek-R1 等模型的思考流
                    emitted = True
                    if on_reasoning:
                        on_reasoning(rp)

                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    acc = tool_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                    if tc.get("id"):
                        acc["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name") and not acc["name"]:
                        acc["name"] = fn["name"]
                    if fn.get("arguments"):
                        acc["arguments"] += fn["arguments"]
        except requests.RequestException as e:
            if emitted:  # 已上屏的内容不能重放，直接失败
                raise LLMError(f"流式传输中断: {e}") from e
            raise _Retryable(f"流式请求失败: {e}") from e

        msg: Dict = {"role": "assistant", "content": "".join(content)}
        if tool_acc:
            msg["tool_calls"] = [
                {
                    "id": acc["id"] or f"call_{i}",
                    "type": "function",
                    "function": {"name": acc["name"], "arguments": acc["arguments"] or "{}"},
                }
                for i, acc in sorted(tool_acc.items())
            ]
        return msg

    # ------------------------------------------------------------------
    @staticmethod
    def _normalize(msg: Dict) -> Dict:
        msg = dict(msg)
        msg.setdefault("role", "assistant")
        if msg.get("content") is None:
            msg["content"] = ""
        tcs = msg.get("tool_calls")
        if tcs:
            fixed = []
            for i, tc in enumerate(tcs):
                tc = dict(tc)
                tc.setdefault("id", f"call_{i}")
                tc.setdefault("type", "function")
                fn = dict(tc.get("function") or {})
                fn.setdefault("name", "unknown")
                fn.setdefault("arguments", "{}")
                tc["function"] = fn
                fixed.append(tc)
            msg["tool_calls"] = fixed
        return msg
