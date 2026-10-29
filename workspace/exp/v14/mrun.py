import sys, pickle, time, json
sys.path.insert(0,'exp/v14')
import lls, lls_m
d=pickle.load(open('exp/v13/hard3.pkl','rb'))
rows=[]; tot=[0,0.0]; totm=[0,0.0]
for idx,(inst,opt,n0) in enumerate(d):
    t=time.time(); (ok,_),st=lls.decide_lls(inst,opt-1); dt=time.time()-t
    t2=time.time(); (ok2,_),st2=lls_m.decide_lls(inst,opt-1); dt2=time.time()-t2
    tot[0]+=st['labels']; tot[1]+=dt; totm[0]+=st2['labels']; totm[1]+=dt2
    print(idx,'ok',ok,ok2,'EA labels',st['labels'],'M labels',st2['labels'],'EA t',round(dt,3),'M t',round(dt2,3),'M fmax',st2['front_max'],flush=True)
    rows.append(dict(idx=idx,ea=st['labels'],m=st2['labels'],ea_t=round(dt,4),m_t=round(dt2,4)))
    json.dump(rows,open('exp/v14/mrun.json','w'),indent=1)
print('EA',tot[0],round(tot[1],3),'M',totm[0],round(totm[1],3),'label ratio',round(totm[0]/tot[0],3),'time ratio',round(totm[1]/tot[1],3))
