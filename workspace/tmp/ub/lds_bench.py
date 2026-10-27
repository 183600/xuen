import sys,time,json
sys.path[:0]=['tmp/ub','exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from hap import weak_rows
from lds_proto import lds
from rdf import check_schedule

rows=weak_rows(4)
out=[];t0=time.time();tot_nodes=0
for j,(c,name,idx,inst,known,initial) in enumerate(rows):
    L,U,s,m,proof=initial
    best=U;bs=s;bm=m; used=[]
    for D in range(0,5):
        if best<=known or best<=L:break
        r,nodes,t=lds(inst,best-1,D,3000,seed=j,time_cap=0.15)
        tot_nodes+=nodes;used.append((D,nodes,round(t,4)))
        if r is not None:
            s2,m2=r;c2=max(s2[i]+inst['p'][i] for i in range(inst['n']))
            if c2<=best-1 and check_schedule(inst,c2,s2,m2):
                best=c2;bs=s2;bm=m2
    out.append(best-known)
    print(j,c,name,idx,'known',known,'U0',U,'best',best,'gap',best-known,'used',used,flush=True)
print('opt',sum(x==0 for x in out),'/',len(out),'avg gap',sum(out)/len(out),'time',round(time.time()-t0,2),'nodes',tot_nodes)
