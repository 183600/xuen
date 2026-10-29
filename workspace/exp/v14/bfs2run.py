import sys, pickle, time, json
sys.path.insert(0,'exp/v14')
import bfs2
d=pickle.load(open('exp/v13/hard3.pkl','rb'))
rows=[]; tot=[0,0.0,0]
for idx,(inst,opt,n0) in enumerate(d):
    t=time.time(); (ok,_),st=bfs2.decide_lls(inst,opt-1); dt=time.time()-t
    tot[0]+=st['labels']; tot[1]+=dt; tot[2]+=st['packs']
    print(idx,'n',inst['n'],'ok',ok,'labels',st['labels'],'exp',st['expanded'],'packs',st['packs'],'hits',st['pack_hits'],'g',st['greedy'],'dff',st['dff'],'t',round(dt,3),'fmax',st['front_max'],flush=True)
    rows.append(dict(idx=idx,n=inst['n'],ok=ok,labels=st['labels'],expanded=st['expanded'],packs=st['packs'],pack_hits=st['pack_hits'],t=round(dt,4),fmax=st['front_max'],levels=st['levels']))
    json.dump(rows,open('exp/v14/bfs2.json','w'),indent=1)
print('tot',tot,'ratios labels',round(tot[0]/69690,3),'time',round(tot[1]/1.184,3))
