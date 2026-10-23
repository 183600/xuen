import sys,time,json,pickle,statistics
sys.path[:0]=['exp/v41','exp/v30','exp/v29','exp/v13','exp/v15','exp/v16','exp/v20','exp/v24','exp/v25']
import root_bb, root_v30, root_v41
def load(f):
    d=pickle.load(open(f,'rb'))
    return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]
def bench(cs,reps=3):
    mods=(root_bb,root_v30,root_v41); ts=[[],[],[]]
    for r in range(reps):
        for inst,opt in cs:
            for j,mod in enumerate(mods):
                st={}; t=time.time(); mod.bb_solve(inst,opt-1,stats=st); ts[j].append(time.time()-t)
    return [statistics.median([sum(x[r*len(cs):(r+1)*len(cs)]) for r in range(reps)]) for x in ts]
sets={'holdout50':'exp/v20/holdout_cases50.pkl','hard3':'exp/v13/hard3.pkl','deep8':'exp/v18/deep.pkl',
      'large_a':'exp/v14/large_a.pkl','large_b':'exp/v14/large_b.pkl','large_het':'exp/v14/large_het.pkl',
      'synth45':'exp/v28/synth2_45.pkl'}
out={}
for name,f in sets.items():
    cs=load(f); out[name]=bench(cs)
    print(name,out[name],flush=True)
tot=[sum(out[n][j] for n in sets) for j in range(3)]
print('TOTAL141',tot)
json.dump(out,open('exp/v41/res_v25.json','w'),indent=1)
