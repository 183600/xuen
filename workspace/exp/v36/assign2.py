import ctypes, os
_lib = ctypes.CDLL(os.path.join(os.path.dirname(__file__), 'libassign2.so'))
_lib.assign2_no.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int,
                            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                            ctypes.POINTER(ctypes.c_int)]
_lib.assign2_no.restype = ctypes.c_int

def assign2_no(inst, h, est, q):
    n = inst['n']
    if n > 16 or h > 63:
        return None
    p = (ctypes.c_int * n)(*inst['p'])
    r = (ctypes.c_int * n)(*est)
    d = (ctypes.c_int * n)(*(h - x for x in q))
    return bool(_lib.assign2_no(n, inst['m'], h, p, r, d))
