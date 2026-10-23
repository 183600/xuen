import sys,pickle,json,time
sys.path[:0]=['exp/v84','exp/v71','exp/v61','exp/v60','exp/v13']
from qrc import QRC
from ft import FTQRC
D=pickle.load(open('exp/v81/h5h47_branch.pkl','rb'))
rows=[]; agg={k:[0,0,0,0,0,0,0] for k in ['base','f1','f2','f3']}
for n,r in enumerate(D):
    inst,h=r['inst'],r['h']; row=dict(n=n,src=r['src'],idx=r['idx'])
    for name,k in [('base',0),('f1',1),('f2',2),('f3',3)]:
        cls=QRC if name=='base' else FTQRC
        kw={} if name=='base' else dict(fail_calls=k)
        t0=time.time(); q=cls(inst,h,**kw); v,st=q.decide(); dt=time.time()-t0
        row[name]=(v,st['lp_solves'],st['nodes'],st.get('heals',0),
                   st.get('forced_fail',0),q.audit(),dt)
        a=agg[name]; a[0]+=int(v is False); a[1]+=st['lp_solves']; a[2]+=st['nodes']; a[3]+=int(bool(q.audit())); a[4]+=st.get('heals',0); a[5]+=st.get('forced_fail',0); a[6]+=dt
    rows.append(row)
    if n%10==0: print('done',n,flush=True)
for k,a in agg.items():
    print(k,dict(no=a[0],lp=a[1],nodes=a[2],audit=a[3],heals=a[4],fails=a[5],t=round(a[6],2)))
json.dump(dict(rows=rows,agg=agg),open('exp/v84/ft51.json','w'),indent=1)
