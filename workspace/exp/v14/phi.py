import sys, pickle, time
sys.path.insert(0,'exp/v14')
import lls
d=pickle.load(open('exp/v13/hard3.pkl','rb'))
for idx in [int(x) for x in sys.argv[1:]] or [4,10,0]:
    inst,opt,n0=d[idx]
    print('=== inst',idx,flush=True)
    for phi in ['lin','sq','max','est','mix']:
        t=time.time(); (ok,_),st=lls.decide_lls(inst,opt-1,phi=phi); dt=time.time()-t
        print(f'{phi:5s} labels={st["labels"]:6d} exp={st["expanded"]:5d} pr={st["pruned"]:6d} fmax={st["front_max"]:3d} t={dt:.3f}',flush=True)
