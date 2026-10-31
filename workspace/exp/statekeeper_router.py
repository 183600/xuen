#!/usr/bin/env python3
"""STATEKEEPER intent-router pre-experiment (pure Python, no external deps).

Input : JSON dict {dataset_slug: [{"task": "p1@p2@...", ...}, ...]}
        Produced from the 32 official tasks.parquet files at 2026-10-31.
Output: JSON with leave-one-out top-5 accuracy, per-cluster errors, and
        within-/between-task cosine similarity.

Usage: python3 statekeeper_router.py /tmp/all_tasks.json
"""
import collections
import json
import math
import re
import statistics
import sys


def tokenize(s):
    words = re.findall(r"(?u)\b\w\w+\b", s.lower())
    return words + [a + " " + b for a, b in zip(words, words[1:])]


def build(mapping):
    texts, labels = [], []
    for slug, rows in mapping.items():
        for row in rows:
            for sent in row["task"].split("@"):
                sent = sent.strip()
                if sent:
                    texts.append(sent)
                    labels.append(slug)
    docs = [tokenize(t) for t in texts]
    n = len(docs)
    df = collections.Counter()
    for doc in docs:
        for tok in set(doc):
            df[tok] += 1
    idf = {tok: math.log((1 + n) / (1 + c)) + 1 for tok, c in df.items()}
    vecs = []
    for doc in docs:
        tf = collections.Counter(doc)
        v = {tok: (1 + math.log(c)) * idf[tok] for tok, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({tok: x / norm for tok, x in v.items()})
    return texts, labels, vecs


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(tok, 0.0) for tok, x in a.items())


def main(path):
    mapping = json.load(open(path))
    texts, labels, vecs = build(mapping)
    n = len(texts)
    sim = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            sim[i][j] = sim[j][i] = cosine(vecs[i], vecs[j])

    within, between = [], []
    for i in range(n):
        for j in range(i + 1, n):
            (within if labels[i] == labels[j] else between).append(sim[i][j])

    correct, errors = 0, []
    for i in range(n):
        order = sorted((j for j in range(n) if j != i), key=lambda j: -sim[i][j])[:5]
        votes = collections.Counter(labels[j] for j in order)
        weight = collections.defaultdict(float)
        for j in order:
            weight[labels[j]] += sim[i][j]
        pred = max(votes, key=lambda k: (votes[k], weight[k]))
        if pred == labels[i]:
            correct += 1
        else:
            errors.append({
                "text": texts[i],
                "gold": labels[i],
                "pred": pred,
                "top5": [[labels[j], round(sim[i][j], 4)] for j in order],
            })

    pairs = collections.Counter()
    for e in errors:
        pairs[tuple(sorted((e["gold"].split("_")[-1], e["pred"].split("_")[-1])))] += 1

    result = {
        "n_texts": n,
        "n_tasks": len(set(labels)),
        "within_mean_cosine": round(statistics.mean(within), 4),
        "between_mean_cosine": round(statistics.mean(between), 4),
        "separability_ratio": round(statistics.mean(within) / statistics.mean(between), 2),
        "loo_top5_correct": correct,
        "loo_top5_accuracy": round(correct / n, 4),
        "n_errors": len(errors),
        "error_clusters": [
            {"pair": list(k), "count": v} for k, v in pairs.most_common()
        ],
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/all_tasks.json")
