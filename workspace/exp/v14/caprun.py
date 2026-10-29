import sys, pickle, time, json
sys.path.insert(0,'exp/v14')
import lls, lls_cap
d=pickle.load(open('exp/v13/hard3.pkl','rb'))
rows=[]; tot=[0,0.0]; totc=[0,0.0]
for idx,(inst,opt,n0) in enumerate(d):
    t=time.time(); (ok,_),st=lls.decide_lls(inst,opt-1); dt=time.time()-t
    t2=time.time(); (ok2,_),st2=lls_cap.decide_lls(inst,opt-1); dt2=time.time()-t2
    tot[0]+=st['labels']; tot[1]+=dt; totc[0]+=st2['labels']; totc[1]+=dt2
    print(idx,'ok',ok,ok2,'EA',st['labels'],'cap',st2['labels'],'t',round(dt,3),round(dt2,3),'fmax',st2['front_max'],flush=True)
    rows.append(dict(idx=idx,ea=st['labels'],cap=st2['labels'],ea_t=round(dt,4),cap_t=round(dt2,4)))
    json.dump(rows,open('exp/v14/caprun.json','w'),indent=1)
print('EA',tot[0],round(tot[1],3),'CAP',totc[0],round(totc[1],3),'ratios',round(totc[0]/tot[0],3),round(totc[1]/tot[1],3))
