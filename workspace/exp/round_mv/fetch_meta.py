import json, os, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

DATASETS = ["HangCup","ArrangePlates","ArrangeTestTubes","ZipUp","ColorArrangement","Unlock",
 "DisconnectEthernet","ConveyorSorting","FruitCollection","FoldTowel","OrganizeBookshelf",
 "FruitSorting","SpellRobot","OrganizePencilCase","OrganizeStationery","StackBowls","StoreCups",
 "OrganizeTools","PackDoll","PackBag","PackPhone","StoreEarphones","StorePaddle","PaperCupStacking",
 "PickOutBatteries","ToolboxStorage","PlugCharger","SyringeWaterTransfer","PlugInEthernet",
 "PlacePhotoFrame","RemovePinnedNote","PourOutMedicine"]

def get(ds, kind):
    path = f"{ds}_{kind}.json"
    if os.path.exists(path) and os.path.getsize(path) > 50:
        return "cached"
    url = f"https://huggingface.co/datasets/unitreerobotics/G1_Dex1_{ds}/resolve/main/meta/{kind}.json"
    for a in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                data = r.read()
            json.loads(data)
            open(path,"wb").write(data)
            return "ok"
        except Exception as e:
            err=str(e); time.sleep(1.0+a)
    return "ERR "+err

jobs=[(d,k) for d in DATASETS for k in ("info","stats")]
with ThreadPoolExecutor(max_workers=4) as ex:
    res=list(ex.map(lambda a:get(*a), jobs))
from collections import Counter
print(Counter(res))
