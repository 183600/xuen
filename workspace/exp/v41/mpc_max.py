import ctypes, os
_lib = ctypes.CDLL(os.path.join(os.path.dirname(__file__), 'libmpc_max.so'))
_lib.mpc_no.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int,
                        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
_lib.mpc_no.restype = ctypes.c_int
_lib.mpc_nodes.restype = ctypes.c_longlong

def mpc_no(inst, h, est, q, stats=None):
    n = inst['n']
    if n > 16 or h > 63:
        return None
    p = (ctypes.c_int * n)(*inst['p'])
    r = (ctypes.c_int * n)(*est)
    d = (ctypes.c_int * n)(*(h - q[i] for i in range(n)))
    pm = [0] * n
    for i in range(n):
        for j in inst['succ'][i]:
            pm[i] |= 1 << j
    pmv = (ctypes.c_int * n)(*pm)
    v = _lib.mpc_no(n, inst['m'], h, p, r, d, pmv)
    if stats is not None:
        stats['mpc_nodes'] = _lib.mpc_nodes()
    return None if v < 0 else bool(v)
