import sys, pickle, json, time
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v14'); sys.path.insert(0,'exp/v15')
import po, pace_i
def load(p):
    d=pickle.load(open(p,'rb')); return [{'inst':x[0],'opt':x[1]} if isinstance(x,tuple) else x for x in d]
SETS=[('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]
cfg=dict(mint_depth=0,packset_depth=0)
rows=[]; T=0
for tag,path in SETS:
    for k,rec in enumerate(load(path)):
        inst=rec['inst']; h=rec['opt']-1
        t=time.time(); (ok,o),st=pace_i.decide(inst,h,mode='pot',**cfg); dt=time.time()-t
        T+=dt
        rows.append(dict(tag=tag,k=k,n=inst['n'],opt=rec['opt'],nodes=st['nodes'],time=dt,
                         tables=st['tables'],wit=(st.get('root_wit') or [None])[0],
                         mint=st.get('mint_calls',0),mp=st.get('mint_prunes',0),
                         pc=st.get('packset_calls',0),pp=st.get('packset_prunes',0),
                         mt=st.get('mint_time',0),pt=st.get('packset_time',0)))
print('TOTAL nodes',sum(r['nodes'] for r in rows),'time',round(T,3),'tables',sum(r['tables'] for r in rows))
for r in rows:
    if r['nodes']>1 or r['wit'] in ('mint','packset'):
        print(r['tag'],r['k'],'n',r['n'],'OPT',r['opt'],'nodes',r['nodes'],'t',round(r['time'],4),
              'tab',r['tables'],'wit',r['wit'],'mint',r['mint'],r['mp'],'pack',r['pc'],r['pp'])
json.dump(rows,open('exp/v15/final_rows.json','w'),indent=0)
