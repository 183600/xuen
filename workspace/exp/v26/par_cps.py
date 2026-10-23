import pickle,sys,time,statistics,os,signal
sys.path[:0]=['exp/v13','exp/v14','exp/v15','exp/v16','exp/v17','exp/v18','exp/v19','exp/v20','exp/v24','exp/v25']
import po,cps_lib
C=pickle.load(open('exp/v20/holdout_cases50.pkl','rb'))

def placements(inst,rem,A,est,q,h,chain):
    S=h-(est[chain[0]]+sum(inst['p'][i] for i in chain)+q[chain[-1]])
    out=[]
    if S<0: return out
    for g in cps_lib._compositions(S,len(chain)+1):
        s=[]; t=est[chain[0]]+g[0]; ok=True
        for a,i in enumerate(chain):
            if a>0: t=s[-1]+inst['p'][chain[a-1]]+g[a]
            if t<est[i] or t+inst['p'][i]>h-q[i]: ok=False; break
            s.append(t)
        if ok: out.append(tuple(s))
    return out

def work_chunk(inst,rem,A,est,q,h,chain,chunk,nodecap=300000):
    anyunk=False
    for s in chunk:
        st={}
        rr=cps_lib._residual_feasible(inst,rem,A,est,q,h,list(chain),list(s),nodecap=nodecap,stats=st)
        if rr is True: return b'F'
        if rr is None: anyunk=True
    return b'U' if anyunk else b'N'

def run(inst,h,W,chain=None,nodecap=300000):
    n=inst['n']; est,q=po.heads_tails(inst,0,[0]*n); A=tuple([0]*inst['m']); rem=inst['full']
    if chain is None: chain,cp=cps_lib.critical_path(inst,rem,tuple(est),q)
    ps=placements(inst,rem,A,tuple(est),q,h,chain)
    if not ps: return dict(W=W,nplace=0,verdict='NO',time=0.0)
    t0=time.time()
    if W==1:
        r=work_chunk(inst,rem,A,tuple(est),q,h,tuple(chain),ps,nodecap)
        return dict(W=W,nplace=len(ps),verdict={'F':'FEAS','U':'UNK','N':'NO'}[r.decode()],time=time.time()-t0)
    # round-robin chunks
    chunks=[ps[i::W] for i in range(W)]
    pipes=[]; pids=[]
    for w in range(W):
        rp,wp=os.pipe(); pid=os.fork()
        if pid==0:
            os.close(rp)
            try:
                r=work_chunk(inst,rem,A,tuple(est),q,h,tuple(chain),chunks[w],nodecap)
                os.write(wp,r)
            finally:
                os._exit(0)
        else:
            os.close(wp); pipes.append(rp); pids.append(pid)
    results=[]
    for rp in pipes:
        data=os.read(rp,1); os.close(rp); results.append(data)
    for pid in pids:
        try: os.kill(pid,signal.SIGKILL)
        except ProcessLookupError: pass
        os.waitpid(pid,0)
    if b'F' in results: verdict='FEAS'
    elif b'U' in results: verdict='UNK'
    else: verdict='NO'
    return dict(W=W,nplace=len(ps),verdict=verdict,time=time.time()-t0)

if __name__=='__main__':
    for idx in [5,21,32,42,47]:
        inst,opt=C[idx]; h=opt-1
        print('idx',idx,'n',inst['n'],flush=True)
        for W in [1,2,4]:
            ts=[]; r=None
            for _ in range(3):
                r=run(inst,h,W); ts.append(r['time'])
            print('  ',r,'median',round(statistics.median(ts),4),flush=True)
