"""Fetch HF datasets-server rows for UniBot-V1 task datasets into duo_rows_cache.

Retrieved: 2026-11-03 (UTC). 30 pages x 100 rows = 3000 frames per task.
Rate-limited to avoid HTTP 429.
"""
import json, os, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://datasets-server.huggingface.co/rows"
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "duo_rows_cache")
os.makedirs(CACHE, exist_ok=True)

DATASETS = [
    "HangCup", "ArrangePlates", "ArrangeTestTubes", "ZipUp", "ColorArrangement", "Unlock",
    "DisconnectEthernet", "ConveyorSorting", "FruitCollection", "FoldTowel",
    "OrganizeBookshelf", "FruitSorting", "SpellRobot", "OrganizePencilCase",
    "OrganizeStationery", "StackBowls", "StoreCups", "OrganizeTools", "PackDoll",
    "PackBag", "PackPhone", "StoreEarphones", "StorePaddle", "PaperCupStacking",
    "PickOutBatteries", "ToolboxStorage", "PlugCharger", "SyringeWaterTransfer",
    "PlugInEthernet", "PlacePhotoFrame", "RemovePinnedNote", "PourOutMedicine",
]
PAGES = 30
MIN_INTERVAL = 0.12  # seconds between requests (global)

_last = [0.0]
_lock = __import__("threading").Lock()

def _throttle():
    with _lock:
        dt = time.time() - _last[0]
        if dt < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - dt)
        _last[0] = time.time()

def fetch(ds, offset):
    path = os.path.join(CACHE, f"{ds}_{offset}.json")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return "cached"
    q = urllib.parse.urlencode({
        "dataset": f"unitreerobotics/G1_Dex1_{ds}", "config": "default",
        "split": "train", "offset": offset, "length": 100})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(6):
        _throttle()
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            json.loads(data)
            with open(path, "wb") as f:
                f.write(data)
            return "ok"
        except Exception as e:
            err = str(e)
            time.sleep(1.5 * (attempt + 1))
    return f"ERR {err}"

if __name__ == "__main__":
    jobs = [(ds, o * 100) for ds in DATASETS for o in range(PAGES)]
    with ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(lambda a: fetch(*a), jobs))
    from collections import Counter
    print(Counter(res))
