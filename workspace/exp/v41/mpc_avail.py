import ctypes, os
_lib = ctypes.CDLL(os.path.join(os.path.dirname(__file__), 'libmpc_avail.so'))
_lib.mpc_avail_no.argtypes = [ctypes.c_int]*2 + [ctypes.c_int] + [ctypes.POINTER(ctypes.c_int)]*5
_lib.mpc_avail_no.restype = ctypes.c_int
_lib.mpc_avail_nodes.restype = ctypes.c_longlong
def mpc_avail_no(n, m, h, p, r, d, succ, av):
    if n > 12 or h > 63: return None
    P=(ctypes.c_int*n)(*p); R=(ctypes.c_int*n)(*r); D=(ctypes.c_int*n)(*d)
    S=(ctypes.c_int*n)(*succ); A=(ctypes.c_int*m)(*av)
    v=_lib.mpc_avail_no(n,m,h,P,R,D,S,A)
    return None if v<0 else bool(v)
