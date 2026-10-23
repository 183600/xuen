import ctypes, os
HERE=os.path.dirname(os.path.abspath(__file__))
_L=ctypes.CDLL(os.path.join(HERE,'map_c.so'))
_L.map_solve.restype=ctypes.c_int
_L.map_solve.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_int,
    ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_ulonglong),ctypes.POINTER(ctypes.c_ulonglong),
    ctypes.POINTER(ctypes.c_int)]
def _arr(v,t=ctypes.c_int): return (t*len(v))(*v)
def map_check(inst, rem, A, est, q, h):
    n=inst['n']; idx=[i for i in range(n) if (rem>>i)&1]; k=len(idx)
    if k==0: return True
    pos={v:j for j,v in enumerate(idx)}
    p=[inst['p'][i] for i in idx]; e=[est[i] for i in idx]; qq=[q[i] for i in idx]
    succ=[]
    for i in idx:
        s=0
        for t in inst['succ'][i]:
            if (rem>>t)&1: s|=1<<pos[t]
        succ.append(s)
    elig=[]
    for i in idx:
        z=0
        for kk in inst['elig'][i]: z|=1<<kk
        elig.append(z)
    return _L.map_solve(k,inst['m'],h,_arr(p),_arr(e),_arr(qq),
                        _arr(succ,ctypes.c_ulonglong),_arr(elig,ctypes.c_ulonglong),
                        _arr(list(A)))!=0
