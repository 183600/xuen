import json
import math
import os
import random
import re
import urllib.request

DATASETS = [
    ("HangCup", "G1_Dex1_HangCup"), ("ArrangePlates", "G1_Dex1_ArrangePlates"),
    ("ArrangeTestTubes", "G1_Dex1_ArrangeTestTubes"), ("ZipUp", "G1_Dex1_ZipUp"),
    ("ColorArrangement", "G1_Dex1_ColorArrangement"), ("Unlock", "G1_Dex1_Unlock"),
    ("DisconnectEthernet", "G1_Dex1_DisconnectEthernet"),
    ("ConveyorSorting", "G1_Dex1_ConveyorSorting"), ("FruitCollection", "G1_Dex1_FruitCollection"),
    ("FoldTowel", "G1_Dex1_FoldTowel"), ("OrganizeBookshelf", "G1_Dex1_OrganizeBookshelf"),
    ("FruitSorting", "G1_Dex1_FruitSorting"), ("SpellRobot", "G1_Dex1_SpellRobot"),
    ("OrganizePencilCase", "G1_Dex1_OrganizePencilCase"),
    ("OrganizeStationery", "G1_Dex1_OrganizeStationery"), ("StackBowls", "G1_Dex1_StackBowls"),
    ("StoreCups", "G1_Dex1_StoreCups"), ("OrganizeTools", "G1_Dex1_OrganizeTools"),
    ("PackDoll", "G1_Dex1_PackDoll"), ("PackBag", "G1_Dex1_PackBag"),
    ("PackPhone", "G1_Dex1_PackPhone"), ("StoreEarphones", "G1_Dex1_StoreEarphones"),
    ("StorePaddle", "G1_Dex1_StorePaddle"), ("PaperCupStacking", "G1_Dex1_PaperCupStacking"),
    ("PickOutBatteries", "G1_Dex1_PickOutBatteries"), ("ToolboxStorage", "G1_Dex1_ToolboxStorage"),
    ("PlugCharger", "G1_Dex1_PlugCharger"), ("SyringeWaterTransfer", "G1_Dex1_SyringeWaterTransfer"),
    ("PlugInEthernet", "G1_Dex1_PlugInEthernet"), ("PlacePhotoFrame", "G1_Dex1_PlacePhotoFrame"),
    ("RemovePinnedNote", "G1_Dex1_RemovePinnedNote"), ("PourOutMedicine", "G1_Dex1_PourOutMedicine"),
]

STOP = set("""a an the and or of to in on at into with by for from is are be been it its this that
these those put place set lay make all every each onto into over under off beside alongside then
so such use using means via do does done please""".split())


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=60).read()


def parse_tasks_parquet(raw):
    try:
        import io
        import pyarrow.parquet as pq
        t = pq.read_table(io.BytesIO(raw)).to_pylist()
        s = t[0]["task"]
        return [x.strip() for x in s.split("@") if x.strip()]
    except Exception:
        txt = raw.decode("latin-1")
        frags = re.findall(r"[\x20-\x7e]{18,}", txt)
        cand = [f for f in frags if f.count(" ") >= 3 and "@" in f or (f.count(" ") >= 4 and f.endswith("."))]
        if not cand:
            return []
        s = max(cand, key=len)
        return [x.strip() for x in s.split("@") if x.strip()]


def tok(s):
    s = s.lower().replace("\"", " ").replace("'", " ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return [w for w in s.split() if w not in STOP and len(w) > 1]


def ngrams(s, n=3):
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    return [s[i:i + n] for i in range(max(1, len(s) - n + 1))]


def cos(a, b, w=None):
    if not a or not b:
        return 0.0
    if w is None:
        keys = set(a) | set(b)
        va = {k: a.count(k) for k in keys}
        vb = {k: b.count(k) for k in keys}
    else:
        keys = set(a) | set(b)
        va = {k: a.count(k) * w.get(k, 1.0) for k in keys}
        vb = {k: b.count(k) * w.get(k, 1.0) for k in keys}
    dot = sum(va[k] * vb[k] for k in keys)
    na = math.sqrt(sum(x * x for x in va.values()))
    nb = math.sqrt(sum(x * x for x in vb.values()))
    return dot / (na * nb) if na and nb else 0.0


def idf(docs):
    df = {}
    for d in docs:
        for w in set(d):
            df[w] = df.get(w, 0) + 1
    n = len(docs)
    return {w: math.log((n + 1) / (c + 1)) + 1.0 for w, c in df.items()}


def dropout(words, rate, rng):
    return [w for w in words if rng.random() > rate]


def main():
    tasks = {}
    fetch_log = []
    for name, repo in DATASETS:
        url = f"https://huggingface.co/datasets/unitreerobotics/{repo}/resolve/main/meta/tasks.parquet"
        try:
            raw = fetch(url)
            paras = parse_tasks_parquet(raw)
            tasks[name] = paras
            fetch_log.append({"task": name, "repo": repo, "n_paraphrases": len(paras), "bytes": len(raw)})
        except Exception as e:
            tasks[name] = []
            fetch_log.append({"task": name, "repo": repo, "error": str(e)})
    complete = {k: v for k, v in tasks.items() if len(v) >= 2}
    flat = [(k, p) for k, ps in complete.items() for p in ps]
    toks = [tok(p) for _, p in flat]
    weights = idf(toks)

    results = {"source": "https://huggingface.co/datasets/unitreerobotics/<repo>/resolve/main/meta/tasks.parquet",
               "retrieved": "2026-11-04",
               "fetch_log": fetch_log,
               "n_tasks_parsed": len(complete),
               "n_paraphrases_total": len(flat)}

    def loo(score_kind, noise_rate, seed=0):
        rng = random.Random(seed)
        ok = 0
        total = 0
        confusions = {}
        for i, (task, para) in enumerate(flat):
            gallery = [flat[j] for j in range(len(flat)) if j != i]
            q = tok(para)
            if noise_rate > 0:
                q = dropout(q, noise_rate, rng)
            best, best_s = None, -1.0
            for gtask, gpara in gallery:
                gt = tok(gpara)
                if score_kind == "idf":
                    s = cos(q, gt, weights)
                else:
                    s = cos(ngrams(para), ngrams(gpara))
                if s > best_s:
                    best_s, best = s, gtask
            total += 1
            if best == task:
                ok += 1
            else:
                confusions[f"{task}->{best}"] = confusions.get(f"{task}->{best}", 0) + 1
        return {"accuracy": round(ok / total, 4), "n": total,
                "top_confusions": sorted(confusions.items(), key=lambda x: -x[1])[:8]}

    results["loo_idf_token"] = loo("idf", 0.0)
    results["loo_char3gram"] = loo("char", 0.0)
    for r in (0.2, 0.35, 0.5):
        results[f"loo_idf_token_dropout{int(r*100)}"] = loo("idf", r, seed=int(r * 100))
    for r in (0.2, 0.35):
        results[f"loo_char3gram_dropout{int(r*100)}"] = loo("char", r, seed=int(r * 100))

    gallery_all = [(k, p) for k, ps in complete.items() for p in ps]
    self_top1 = 0
    for task, para in gallery_all:
        q = tok(para)
        best, best_s = None, -1.0
        for gtask, gpara in gallery_all:
            s = cos(q, tok(gpara), weights)
            if s > best_s:
                best_s, best = s, gtask
        self_top1 += int(best == task)
    results["full_gallery_idf_self_accuracy"] = round(self_top1 / len(gallery_all), 4)
    results["example_paraphrases"] = {k: v[:2] for k, v in list(complete.items())[:6]}

    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "fsb_langmatch_results.json"), "w") as f:
        json.dump(results, f, indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in results.items() if k != "fetch_log"}, indent=1, ensure_ascii=False))
    bad = [x for x in fetch_log if x.get("n_paraphrases", 0) < 2]
    print("parse problems:", bad)


if __name__ == "__main__":
    main()
