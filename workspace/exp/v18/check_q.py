"""Independent check of every HPACK witness produced on the benchmarks."""
import sys,pickle,json
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v15'); sys.path.insert(0,'exp/v16')
sys.path.insert(0,'exp/v17'); sys.path.insert(0,'exp/v18')
import po, pace_q
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000,
         odom=True,hpack_on=True)
def check(inst,h):
    (ok,out),st=pace_q.decide(inst,h,omd=all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n'])),**CFG)
    bad=[]; n_hp=0
    for (rem,A,est,w) in st['wits']:
        if w[0]!='hpack': continue
        n_hp+=1
        q=po.tails(inst,rem)
        if not pace_q.check_potential_witness(inst,rem,A,est,q,h,w):
            bad.append(w)
    return ok,st,n_hp,bad
tot=0; bad=0; rows=[]
sets=[('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
      ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]
for tag,path in sets:
    d=pickle.load(open(path,'rb'))
    for k,rec in enumerate(d):
        inst,opt=(rec[0],rec[1]) if isinstance(rec,tuple) else (rec['inst'],rec['opt'])
        ok,st,nhp,b=check(inst,opt-1)
        tot+=nhp; bad+=len(b)
        if nhp: rows.append((tag,k,nhp,len(b)))
D=pickle.load(open('exp/v18/deep.pkl','rb'))
for idx in range(len(D)):
    inst,opt,*_=D[idx]
    ok,st,nhp,b=check(inst,opt-1)
    tot+=nhp; bad+=len(b)
    if nhp: rows.append(('deep',idx,nhp,len(b)))
out=dict(hpack_witnesses=tot,bad=bad,rows=rows)
json.dump(out,open('exp/v18/res_check.json','w'),indent=1)
print(out)
