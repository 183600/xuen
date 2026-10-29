import ctypes, os
HERE=os.path.dirname(os.path.abspath(__file__))
_L=ctypes.CDLL(os.path.join(HERE,'pi_kernel.so'))
_L.pi_solve.restype=ctypes.c_int
_L.pi_solve.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_int,
    ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_ulonglong),ctypes.POINTER(ctypes.c_ulonglong),
    ctypes.c_ulonglong,ctypes.POINTER(ctypes.c_int),ctypes.c_int,ctypes.c_int]

def _arr(v,t=ctypes.c_int): return (t*len(v))(*v)

def beta(inst,h,rem,est,q,parts_out=None,cap=None):
    n=inst['n']; idx=[i for i in range(n) if (rem>>i)&1]; k=len(idx)
    if k==0: return 0,[]
    pos={v:j for j,v in enumerate(idx)}
    p=[inst['p'][i] for i in idx]; e=[est[i] for i in idx]; qq=[q[i] for i in idx]
    succ=[0]*k
    for j,i in enumerate(idx):
        s=0
        for t in inst['succ'][i]:
            if (rem>>t)&1: s|=1<<pos[t]
        succ[j]=s
    elig=[]
    for i in idx:
        m=0
        for kk in inst['elig'][i]: m|=1<<kk
        elig.append(m)
    W=(1<<k)-1
    out=(ctypes.c_int*max(1,inst['m']+1))()
    m=inst['m']; c=cap if cap is not None else m+1
    b=_L.pi_solve(k,m,h,_arr(p),_arr(e),_arr(qq),_arr(succ,ctypes.c_ulonglong),
                  _arr(elig,ctypes.c_ulonglong),W,out,len(out),c)
    return b,[out[i] for i in range(min(b,m))] if b<=m else []
