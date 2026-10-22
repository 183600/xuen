import sys,pickle,time,json
sys.path[:0]=['exp/v13','exp/v14','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v23']
import pace_v23
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
def fe(inst): return all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n']))
def load(path):
 d=pickle.load(open(path,'rb')); return [x if isinstance(x,dict) else {'inst':x[0],'opt':x[1]} for x in d]
sets=[]
for tag,path in [('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]:
 for rec in load(path): sets.append((tag,rec['inst'],rec['opt']))
D=pickle.load(open('exp/v18/deep.pkl','rb')); deep=[('deep%d'%k,D[k][0],D[k][1]) for k in range(8)]
def run(ss,cap,wcap):
 tot=0; tt=0
 for tag,inst,opt in ss:
  t=time.time(); (b,o),st=pace_v23.decide(inst,opt-1,omd=fe(inst),dcd=True,dhd=True,hpack_on=True,pi=True,pi_depth=0,pi_ncap=cap,pi_tau=4,pi_gap=4,pi_wcap=wcap,**CFG); tt+=time.time()-t; tot+=st['nodes']
 return {'nodes':tot,'time':round(tt,4)}
out={}
for name,cap,wcap in [('full16',16,16),('top15',15,15),('staged',16,15)]:
 out[name]={'38':run(sets,cap,wcap),'deep':run(deep,cap,wcap)}
print(out); json.dump(out,open('exp/v23/res_ablate.json','w'),indent=1)
