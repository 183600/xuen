import json, glob, os, numpy as np
from collections import OrderedDict

DATASETS = ["HangCup","ArrangePlates","ArrangeTestTubes","ZipUp","ColorArrangement","Unlock",
 "DisconnectEthernet","ConveyorSorting","FruitCollection","FoldTowel","OrganizeBookshelf",
 "FruitSorting","SpellRobot","OrganizePencilCase","OrganizeStationery","StackBowls","StoreCups",
 "OrganizeTools","PackDoll","PackBag","PackPhone","StoreEarphones","StorePaddle","PaperCupStacking",
 "PickOutBatteries","ToolboxStorage","PlugCharger","SyringeWaterTransfer","PlugInEthernet",
 "PlacePhotoFrame","RemovePinnedNote","PourOutMedicine"]

out={}
for ds in DATASETS:
    info=json.load(open(f"{ds}_info.json")); st=json.load(open(f"{ds}_stats.json"))
    piv=st.get("action.pivot",{})
    std=np.array(piv.get("std",[0]*7),dtype=float)
    rng=np.array(piv.get("max",[0]*7),dtype=float)-np.array(piv.get("min",[0]*7),dtype=float)
    # pivot active dims: std > 1e-3
    active=[int(x) for x in (std>1e-3)]
    gl=st.get("observation.state.left_gripper",{}); gr=st.get("observation.state.right_gripper",{})
    def frac_closed(g):
        # use q01/q10/mean: closed if value below 1.0; report min, q01, mean
        return dict(min=g.get("min",[None])[0], q01=g.get("q01",[None])[0],
                    q10=g.get("q10",[None])[0], mean=g.get("mean",[None])[0], q90=g.get("q90",[None])[0])
    out[ds]=dict(episodes=info["total_episodes"], frames=info["total_frames"], fps=info["fps"],
                 hours=info["total_frames"]/info["fps"]/3600,
                 pivot_std=std.tolist(), pivot_range=rng.tolist(), active_dims=sum(active),
                 gripper_L=frac_closed(gl), gripper_R=frac_closed(gr))

json.dump(out,open("task_meta_summary.json","w"),indent=1)
print("tasks",len(out),"total episodes",sum(v['episodes'] for v in out.values()),
      "total hours",round(sum(v['hours'] for v in out.values()),1))
print("\nPivot activity per task (active dims / 7, std sum):")
for ds,v in out.items():
    print(f"{ds:22s} eps={v['episodes']:5d} h={v['hours']:5.1f} pivot_active={v['active_dims']} std_sum={sum(v['pivot_std']):.4f} p3std={v['pivot_std'][2]:.4f} p5std={v['pivot_std'][5]:.4f} p7std={v['pivot_std'][6]:.4f}")
