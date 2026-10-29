import sys, pickle, time, json
sys.path.insert(0,'exp/v13')
import po
MODES=['plain','canon','front','sub','ladder_front']
d=pickle.load(open('v13/hard3.pkl','rb'))
res=[]
for idx,(inst,opt,nodes0) in enumerate(d):
    out={}
    print('inst',idx,'n',inst['n'],'opt',opt,'base_nodes',nodes0,flush=True)
    for mode in MODES:
        t=time.time(); (ok,_),st=po.decide(inst,opt-1,mode=mode,nodecap=2_500_000); dt=time.time()-t
        out[mode]=dict(ok=ok,t=round(dt,4),nodes=st['nodes'],memo=st['memo_hits'],
                       packfh=st['pack_front_hits'],subfh=st['sub_front_hits'],
                       tables=st['tables'],greedy=st['greedy_yes'],dff=st['dff_no'],
                       inserts=st['inserts'],
                       fmax=max(st['front_sizes']) if st['front_sizes'] else 0,
                       fmed=(sorted(st['front_sizes'])[len(st['front_sizes'])//2] if st['front_sizes'] else 0),
                       timeout=st.get('timeout',False))
        print('  ',mode,ok,st['nodes'],round(dt,3),'pf',st['pack_front_hits'],'sf',st['sub_front_hits'],'tab',st['tables'],flush=True)
    res.append(dict(n=inst['n'],opt=opt,bench=out))
    json.dump(res,open('v13/bench3.json','w'),indent=1)
print('saved')
