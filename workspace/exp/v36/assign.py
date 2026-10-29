import ctypes, os, time
import numpy as np
_lib = ctypes.CDLL(os.path.join(os.path.dirname(__file__), 'libassign.so'))
_lib.assign_no.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int,
                           ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                           ctypes.POINTER(ctypes.c_int)]
_lib.assign_no.restype = ctypes.c_int

def assign_no(inst, h, est):
    n = inst['n']
    if n > 16 or h > 63:
        return None
    p = (ctypes.c_int * n)(*inst['p'])
    r = (ctypes.c_int * n)(*est)
    d = (ctypes.c_int * n)(*(h - q for q in inst['q']))
    return bool(_lib.assign_no(n, inst['m'], h, p, r, d))
