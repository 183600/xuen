import sys, pickle, time, os, json
sys.path[:0]=['exp/v31','exp/v30','exp/v29','exp/v13','exp/v15','exp/v16','exp/v20','exp/v25']
import root_v30

def load(f):
    d=pickle.load(open(f,'rb')); out=[]
    for x in d:
        if isinstance(x,tuple): out.append((x[0],x[1]))
        else: out.append((x['inst'],x['opt']))
    return out
CASES={'holdout50':'exp/v20/holdout_cases50.pkl','hard3':'exp/v13/hard3.pkl','deep8':'exp/v18/deep.pkl','large_a':'exp/v14/large_a.pkl','large_b':'exp/v14/large_b.pkl','large_het':'exp/v14/large_het.pkl','synth45':'exp/v28/synth2_45.pkl'}
jobs=[]
for name,f in CASES.items():
    for inst,opt in load(f): jobs.append((name,inst,opt))

def work(job):
    name,inst,opt=job
    st={}; ok,s=root_v30.bb_solve(inst,opt-1,stats=st)
    return (name,s.get('t',0),ok)

def run_shard(k,P,path):
    res=[]
    for i,j in enumerate(jobs):
        if i%P==k: res.append((i,work(j)))
    pickle.dump(res,open(path,'wb'))

if __name__=='__main__':
    P=int(sys.argv[1]) if len(sys.argv)>1 else 4
    t0=time.time()
    pids=[]
    for k in range(P):
        pid=os.fork()
        if pid==0:
            run_shard(k,P,'exp/v33/shard_%d.pkl'%k)
            os._exit(0)
        pids.append(pid)
    for pid in pids: os.waitpid(pid,0)
    dt=time.time()-t0
    res=[]
    for k in range(P): res += pickle.load(open('exp/v33/shard_%d.pkl'%k,'rb'))
    res.sort()
    print('P',P,'wall',round(dt,4),'sum',round(sum(x[1][1] for x in res),4),'jobs',len(res),'yes',sum(1 for x in res if x[1][2]))
