import sys,pickle,json,time
sys.path[:0]=['exp/v84','exp/v71','exp/v61','exp/v60','exp/v13']
from qnc import QNC
from qrc import QRC

D=pickle.load(open('exp/v81/h5h47_branch.pkl','rb'))
VAR={'qnc':(QNC,{}),
     'prop':(QRC,dict(res_on=False)),
     'res':(QRC,dict(use_prop=False)),
     'full':(QRC,{})}
rows=[]; agg={k:[0,0,0,0,0,0] for k in VAR}
for n,r in enumerate(D):
    inst,h=r['inst'],r['h']; row=dict(n=n,src=r['src'],idx=r['idx'])
    for name,(cls,kw) in VAR.items():
        t0=time.time(); q=cls(inst,h,**kw); v,st=q.decide(); dt=time.time()-t0
        row[name]=(v,st['lp_solves'],st['nodes'],st.get('res_steps',0),
                   st.get('res_units',0),st.get('local_steps',0),q.audit(),dt)
        a=agg[name]; a[0]+=int(v is False); a[1]+=st['lp_solves']; a[2]+=st['nodes']; a[3]+=int(bool(q.audit())); a[4]+=st.get('res_steps',0); a[5]+=st.get('local_steps',0)
    rows.append(row)
    if n%10==0: print('done',n,flush=True)
for k,a in agg.items(): print(k,dict(no=a[0],lp=a[1],nodes=a[2],audit=a[3],res_steps=a[4],local_steps=a[5]))
json.dump(dict(rows=rows,agg=agg),open('exp/v84/ablate51.json','w'),indent=1)
