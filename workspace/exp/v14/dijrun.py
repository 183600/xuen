import sys, pickle, time, json
sys.path.insert(0,'exp/v14')
import dij
d=pickle.load(open('exp/v13/hard3.pkl','rb'))
rows=[]; tot=[0,0.0,0]
for idx,(inst,opt,n0) in enumerate(d):
    t=time.time(); (ok,_),st=dij.decide_dij(inst,opt-1); dt=time.time()-t
    tot[0]+=st['pops']; tot[1]+=dt; tot[2]+=st['packs']
    print(idx,'n',inst['n'],'ok',ok,'pops',st['pops'],'push',st['pushes'],'fin',st['final'],'skip',st['dom_skip'],'packs',st['packs'],'fmax',st['front_max'],'t',round(dt,3),flush=True)
    rows.append(dict(idx=idx,n=inst['n'],ok=ok,pops=st['pops'],pushes=st['pushes'],final=st['final'],skip=st['dom_skip'],packs=st['packs'],fmax=st['front_max'],t=round(dt,4)))
    json.dump(rows,open('exp/v14/dij.json','w'),indent=1)
print('tot',tot,'ratio pops',round(tot[0]/69690,3),'time',round(tot[1]/1.184,3))
