import sys, pickle, time
sys.path.insert(0,'exp/v14')
import sp, lls
d=pickle.load(open('exp/v13/hard3.pkl','rb'))
for idx in [1,2,10,0,4]:
    inst,opt,n0=d[idx]
    t=time.time(); (ok,s),st=sp.decide(inst,opt,mode='sub',nodecap=2_000_000); dt=time.time()-t
    t2=time.time(); (ok2,_),st2=lls.decide_lls(inst,opt,labelcap=300_000); dt2=time.time()-t2
    print(idx,'n',inst['n'],'h=OPT',opt,'DFS',ok,st['nodes'],round(dt,3),'LLS',ok2,st2['labels'],st2['expanded'],round(dt2,3),'to',st2['timeout'],flush=True)
