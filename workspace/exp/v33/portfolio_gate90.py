import sys,pickle,time,statistics,json
sys.path[:0]=['exp/v33','exp/v31','exp/v30','exp/v29','exp/v13','exp/v15','exp/v16','exp/v20','exp/v25']
import turn

CASES=[('holdout50','exp/v20/holdout_cases50.pkl'),('hard3','exp/v13/hard3.pkl'),
       ('deep8','exp/v18/deep.pkl'),('large_a','exp/v14/large_a.pkl'),
       ('large_b','exp/v14/large_b.pkl'),('large_het','exp/v14/large_het.pkl'),
       ('synth45','exp/v28/synth2_45.pkl')]
def load(f):
    d=pickle.load(open(f,'rb')); out=[]
    for x in d:
        if isinstance(x,tuple): out.append((x[0],x[1]))
        else: out.append((x['inst'],x['opt']))
    return out
def lpt(durs,P=4):
    loads=[0.0]*P
    for d in sorted(durs,reverse=True):
        k=min(range(P),key=lambda i:loads[i]); loads[k]+=d
    return max(loads)
rows=[]
for name,f in CASES:
    for inst,opt in load(f):
        h=opt-1; rec=dict(name=name,t=0.0,kind='cascade',p=None,tf=None,tb=None)
        t=[]
        for rep in range(3):
            t0=time.time(); st={}; turn.bb_solve(inst,h,stats=st,icc_util_gate=0.90); t.append(time.time()-t0)
        rec['t']=statistics.median(t); rec['verdict']=st.get('verdict')
        if str(st.get('verdict','')).startswith('OS'):
            tf=[];tb=[]
            for rep in range(3):
                t0=time.time(); turn.bb_solve(inst,h,stats={},force_dir='f',icc_util_gate=0.90); tf.append(time.time()-t0)
                t0=time.time(); turn.bb_solve(inst,h,stats={},force_dir='b',icc_util_gate=0.90); tb.append(time.time()-t0)
            rec.update(kind='dual',p=st.get('p_bwd'),tf=statistics.median(tf),tb=statistics.median(tb))
        rows.append(rec)
pickle.dump(rows,open('exp/v33/portfolio_gate90.pkl','wb'))
print('cases',len(rows),'dual',sum(1 for r in rows if r['kind']=='dual'))
for tag in ['allF','allB','race','selector']:
    durs=[];work=0
    for r in rows:
        if r['kind']!='dual': durs.append(r['t']);work+=r['t'];continue
        if tag=='allF': d=r['tf']
        elif tag=='allB': d=r['tb']
        elif tag=='race': d=min(r['tf'],r['tb'])
        else: d=r['t']
        durs.append(d)
        work += (r['tf']+r['tb']) if tag=='race' else d
    print('%-8s work %.4f span4 %.4f max %.4f'%(tag,work,lpt(durs),max(durs)))
# per-set selector work
import collections
agg=collections.defaultdict(float)
for r in rows: agg[r['name']]+=r['t']
print('per-set',{k:round(v,4) for k,v in agg.items()},'total',round(sum(agg.values()),4))
