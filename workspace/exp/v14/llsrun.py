import sys, pickle, time, json
sys.path.insert(0,'exp/v14')
import lls
d=pickle.load(open('exp/v13/hard3.pkl','rb'))
rows=[]; tot=[0,0.0]
for idx,(inst,opt,n0) in enumerate(d):
    t=time.time(); (ok,_),st=lls.decide_lls(inst,opt-1); dt=time.time()-t
    tot[0]+=st['labels']; tot[1]+=dt
    print(idx,'ok',ok,'labels',st['labels'],'exp',st['expanded'],'dead',st['dead'],'pr',st['pruned'],'packs',st['packs'],'ex',st['exact'],'g',st['greedy'],'d',st['dff'],'fmax',st['front_max'],'t',round(dt,3),flush=True)
    rows.append(dict(idx=idx,n=inst['n'],ok=ok,labels=st['labels'],expanded=st['expanded'],dead=st['dead'],pruned=st['pruned'],packs=st['packs'],exact=st['exact'],greedy=st['greedy'],dff=st['dff'],fmax=st['front_max'],t=round(dt,4)))
    json.dump(rows,open('exp/v14/lls.json','w'),indent=1)
print('tot labels',tot[0],'time',round(tot[1],3),'ratios',round(tot[0]/69690,3),round(tot[1]/1.184,3))
