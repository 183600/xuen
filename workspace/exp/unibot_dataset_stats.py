"""Pull official challenge-dataset statistics (meta/info.json + meta/tasks.parquet)
for the 32 UniBot-V1 datasets. Source: huggingface.co unitreerobotics."""
import json, io, urllib.request, concurrent.futures as cf
import pyarrow.parquet as pq

DS = ["HangCup","ArrangePlates","ArrangeTestTubes","ZipUp","ColorArrangement","Unlock",
      "DisconnectEthernet","ConveyorSorting","FruitCollection","FoldTowel","OrganizeBookshelf",
      "FruitSorting","SpellRobot","OrganizePencilCase","OrganizeStationery","StackBowls",
      "StoreCups","OrganizeTools","PackDoll","PackBag","PackPhone","StoreEarphones","StorePaddle",
      "PaperCupStacking","PickOutBatteries","ToolboxStorage","PlugCharger","SyringeWaterTransfer",
      "PlugInEthernet","PlacePhotoFrame","RemovePinnedNote","PourOutMedicine"]
BASE = "https://huggingface.co/datasets/unitreerobotics/G1_Dex1_{}/resolve/main/"

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent":"research-script"})
    return urllib.request.urlopen(req, timeout=90).read()

def one(tag):
    rec = {"repo": f"unitreerobotics/G1_Dex1_{tag}"}
    try:
        info = json.loads(get(BASE.format(tag) + "meta/info.json"))
        rec.update({
            "total_episodes": info.get("total_episodes"),
            "total_frames": info.get("total_frames"),
            "total_tasks": info.get("total_tasks"),
            "fps": info.get("fps"),
            "chunks_size": info.get("chunks_size"),
            "codebase_version": info.get("codebase_version"),
            "robot_type": info.get("robot_type"),
            "data_files_size_mb": info.get("data_files_size_in_mb"),
            "video_files_size_mb": info.get("video_files_size_in_mb"),
            "features_count": len(info.get("features", {})),
            "has_video": any(k.startswith("video") for k in info.get("features", {})),
            "has_image": any("image" in k for k in info.get("features", {})),
        })
    except Exception as e:
        rec["info_error"] = repr(e)
    try:
        tb = pq.read_table(io.BytesIO(get(BASE.format(tag) + "meta/tasks.parquet")))
        rec["task_columns"] = tb.column_names
        d = tb.to_pydict()
        key = "task" if "task" in d else tb.column_names[-1]
        rec["n_distinct_instructions"] = len(set(d[key]))
        rec["instructions"] = sorted(set(d[key]))[:40]
    except Exception as e:
        rec["tasks_error"] = repr(e)
    if rec.get("total_episodes") and rec.get("total_frames"):
        rec["frames_per_episode"] = round(rec["total_frames"]/rec["total_episodes"], 1)
        if rec.get("fps"): rec["demo_seconds_per_episode"] = round(rec["frames_per_episode"]/rec["fps"], 2)
    return rec

with cf.ThreadPoolExecutor(8) as ex:
    out = list(ex.map(one, DS))
json.dump(out, open("exp/unibot_dataset_stats.json","w"), indent=1, ensure_ascii=False)

print(f"{'dataset':24s} {'eps':>6s} {'frames':>9s} {'f/ep':>7s} {'sec/ep':>7s} {'tasks':>6s} {'instr':>6s}")
for r in out:
    print(f"{r['repo'].split('_')[-1]:24s} {str(r.get('total_episodes')):>6s} {str(r.get('total_frames')):>9s} "
          f"{str(r.get('frames_per_episode')):>7s} {str(r.get('demo_seconds_per_episode')):>7s} "
          f"{str(r.get('total_tasks')):>6s} {str(r.get('n_distinct_instructions')):>6s}")
tot_eps=sum(r.get('total_episodes') or 0 for r in out); tot_fr=sum(r.get('total_frames') or 0 for r in out)
print(f"\nTOTAL episodes {tot_eps}  frames {tot_fr}  hours@30fps {tot_fr/30/3600:.1f}")
print("distinct instruction counts:", sorted(set(r.get('n_distinct_instructions') for r in out)))
for r in out[:3]:
    print("\n", r["repo"], "->", r.get("instructions"))
