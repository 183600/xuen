"""v9.0 PAGE-ALC: compact paged proofs and a one-pass external-memory audit.

The search core is R-ACT's residual DFS (`exp/v8p/residual.py`).  This
module changes the *proof representation*, not the search:

  * an internal node stores only (job, split); its forbidden set F is
    reconstructed from the root box while streaming;
  * a leaf stores its certificate/bound/schedule, but not F;
  * the proof is a preorder byte stream, written once and read once;
  * the auditor keeps a stack of boxes (one interval per job), so the
    live memory is O(height * n + block), independent of the proof size;
  * a residual (open) proof certifies an interval [L,U], not only a
    closed NO.

The module is deliberately independent of the search code: it consumes
the RNode trees produced by `residual.decide` and can be used as the
proof store of any PACT/R-ACT probe.
"""
import sys
import os
import io
import json
import struct
import time
import tempfile

sys.path[:0] = ['exp/v8q', 'exp/v8p', 'exp/v8o', 'exp/v8i', 'exp/v8h',
                'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c', 'exp/v9d',
                'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
                'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']

from apex import Proof
from sage import _domain
from cert import verify
from rdf import check_schedule
from po import heads_tails
from ract import local_bound, topo_order


MAGIC = b'PAGE1\n'
REASONS = ('budget', 'depth', 'cert', 'lp', 'choice', 'machine', 'width')
R2I = {r: i for i, r in enumerate(REASONS)}
I2R = {i: r for r, i in R2I.items()}


def _cert_bytes(cert):
    return json.dumps(cert, sort_keys=True, separators=(',', ':')).encode()


def _base_dom(inst, h):
    return tuple(_domain(inst, h, i) for i in range(inst['n']))


def _F(inst, h, dom):
    """Materialise the forbidden set of a box. O(nT) transient."""
    n = inst['n']
    out = set()
    for i in range(n):
        lo0, hi0 = _domain(inst, h, i)
        lo, hi = dom[i]
        for t in range(lo0, hi0 + 1):
            if t < lo or t > hi:
                out.add((i, t))
    return frozenset(out)


def _allowed(inst, h, i, dom):
    lo, hi = dom[i]
    return list(range(max(lo, _domain(inst, h, i)[0]),
                      min(hi, _domain(inst, h, i)[1]) + 1))


# --------------------------------------------------------------- encoding
def _node_lb(x, inst, h):
    if hasattr(x, 'lb'):
        return int(x.lb)
    if inst is None:
        return 0
    est, q = heads_tails(inst, 0, [0] * inst['n'])
    return int(local_bound(inst, h, x.F, est, q, topo_order(inst))[0])


def encode_compact(node, inst=None, h=None):
    out = bytearray(MAGIC)
    stack = [node]
    while stack:
        x = stack.pop()
        if x is None:
            out += b'Z'
            continue
        tag = x.tag
        if tag == 'node':
            out += b'N' + struct.pack('<HI', x.i, x.mid)
            # preorder: left (times > mid) then right (times <= mid)
            stack.append(x.children[1])
            stack.append(x.children[0])
        elif tag == 'leaf':
            cb = _cert_bytes(x.cert)
            out += b'L' + struct.pack('<I', len(cb)) + cb
        elif tag == 'empty':
            out += b'E' + struct.pack('<H', x.job)
        elif tag == 'bound':
            out += b'B' + struct.pack('<H', int(x.lb))
        elif tag == 'open':
            out += b'O' + struct.pack('<H', _node_lb(x, inst, h)) + bytes([R2I[x.reason]])
        elif tag == 'yes':
            n = len(x.starts)
            out += b'Y' + struct.pack('<H', n)
            out += struct.pack('<%dH' % n, *[int(s) for s in x.starts])
            out += bytes([int(m) & 255 for m in x.machines])
        else:
            raise ValueError('bad tag %r' % (tag,))
    return bytes(out)


def encode_fbased(node, inst=None, h=None):
    """Logical F-carrying encoding, for comparison with the compact log."""
    out = bytearray(MAGIC)
    stack = [node]
    while stack:
        x = stack.pop()
        if x is None:
            out += b'Z'
            continue
        tag = x.tag
        F = sorted(x.F)
        head = b''
        if tag == 'node':
            head = b'N' + struct.pack('<HI', x.i, x.mid)
        elif tag == 'leaf':
            cb = _cert_bytes(x.cert)
            head = b'L' + struct.pack('<I', len(cb)) + cb
        elif tag == 'empty':
            head = b'E' + struct.pack('<H', x.job)
        elif tag == 'bound':
            head = b'B' + struct.pack('<H', int(x.lb))
        elif tag == 'open':
            head = b'O' + struct.pack('<H', _node_lb(x, inst, h)) + bytes([R2I[x.reason]])
        elif tag == 'yes':
            n = len(x.starts)
            head = (b'Y' + struct.pack('<H', n)
                    + struct.pack('<%dH' % n, *[int(s) for s in x.starts])
                    + bytes([int(m) & 255 for m in x.machines]))
        else:
            raise ValueError('bad tag %r' % (tag,))
        # F pairs: 2-byte job + 2-byte time; F length 4 bytes
        out += head + struct.pack('<I', len(F))
        for i, t in F:
            out += struct.pack('<HH', i, t)
        if tag == 'node':
            stack.append(x.children[1])
            stack.append(x.children[0])
    return bytes(out)


# --------------------------------------------------------------- reader
class BlockReader:
    """A sequential reader that charges one I/O per block refill."""
    def __init__(self, path, block):
        self.f = open(path, 'rb')
        self.block = block
        self.buf = b''
        self.pos = 0
        self.reads = 0
        self.bytes = 0

    def _fill(self):
        chunk = self.f.read(self.block)
        if not chunk:
            return False
        self.reads += 1
        self.bytes += len(chunk)
        self.buf = self.buf[self.pos:] + chunk
        self.pos = 0
        return True

    def read(self, n):
        while len(self.buf) - self.pos < n:
            if not self._fill():
                raise EOFError('short proof stream')
        b = self.buf[self.pos:self.pos + n]
        self.pos += n
        return b

    def remaining(self):
        return len(self.buf) - self.pos + max(0, os.fstat(self.f.fileno()).st_size
                                              - self.f.tell())

    def close(self):
        self.f.close()


# --------------------------------------------------------------- audit
def audit_compact(inst, h, data=None, path=None, block=256,
                  want_interval=True):
    """One-pass preorder audit.

    Returns dict(ok, L, U, nodes, max_stack, reads, bytes, t, reason,
    ledger).  The auditor never receives an RNode tree when `path` is
    used: it reconstructs each box from the stream.
    """
    if path is None:
        fd, path = tempfile.mkstemp()
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        own = True
    else:
        own = False
    t0 = time.time()
    rd = BlockReader(path, block)
    try:
        magic = rd.read(len(MAGIC))
        if magic != MAGIC:
            return dict(ok=False, reason='magic', L=None, U=None,
                        nodes=0, max_stack=0, reads=rd.reads,
                        bytes=rd.bytes, t=time.time() - t0, ledger={})
        n = inst['n']
        base = _base_dom(inst, h)
        # stack entries: (dom, depth)
        stack = [(base, 0)]
        max_stack = 1
        nodes = 0
        closed = 0
        opens = 0
        yes_vals = []
        lower = []
        ledger = dict(nodes=0, expanded=0, closed_leaves=0, open_leaves=0,
                      cert_lp=0, lp=0, height=0, holes=0)
        while stack:
            dom, depth = stack.pop()
            tag = rd.read(1)
            nodes += 1
            if tag == b'N':
                i, mid = struct.unpack('<HI', rd.read(6))
                if i >= n:
                    raise ValueError('job out of range')
                # split the interval of job i
                lo, hi = dom[i]
                if not (lo <= mid < hi):
                    raise ValueError('degenerate split')
                low = list(dom)
                high = list(dom)
                low[i] = (lo, mid)
                high[i] = (mid + 1, hi)
                # child 0 is the low side (t <= mid); child 1 is the high side
                stack.append((tuple(high), depth + 1))
                stack.append((tuple(low), depth + 1))
                max_stack = max(max_stack, len(stack))
                ledger['expanded'] += 1
                ledger['lp'] += 1
                ledger['height'] = max(ledger['height'], depth)
            elif tag == b'L':
                ln = struct.unpack('<I', rd.read(4))[0]
                cert = json.loads(rd.read(ln).decode())
                F = _F(inst, h, dom)
                if cert.get('kind') == 'empty':
                    j = cert.get('job')
                    if j is None or _allowed(inst, h, j, dom):
                        raise ValueError('bad empty cert')
                else:
                    if not verify(inst, h, cert, forbid=F):
                        raise ValueError('bad Farkas cert')
                closed += 1
                lower.append(h + 1)
                ledger['closed_leaves'] += 1
                ledger['expanded'] += 1
                ledger['lp'] += 1
                ledger['cert_lp'] += 1
                ledger['height'] = max(ledger['height'], depth)
            elif tag == b'E':
                j = struct.unpack('<H', rd.read(2))[0]
                if _allowed(inst, h, j, dom):
                    raise ValueError('nonempty empty leaf')
                closed += 1
                lower.append(h + 1)
                ledger['closed_leaves'] += 1
                ledger['expanded'] += 1
                ledger['lp'] += 1
                ledger['height'] = max(ledger['height'], depth)
            elif tag == b'B':
                lb = struct.unpack('<H', rd.read(2))[0]
                F = _F(inst, h, dom)
                real, width, wit = local_bound(inst, h, F, *_est_q(inst),
                                               topo_order(inst))
                if real <= h or real != lb:
                    raise ValueError('bad bound leaf')
                closed += 1
                lower.append(h + 1)
                ledger['closed_leaves'] += 1
                ledger['expanded'] += 1
                ledger['height'] = max(ledger['height'], depth)
            elif tag == b'O':
                lb = struct.unpack('<H', rd.read(2))[0]
                reason = I2R.get(rd.read(1)[0])
                if reason is None:
                    raise ValueError('bad open reason')
                F = _F(inst, h, dom)
                real, width, wit = local_bound(inst, h, F, *_est_q(inst),
                                               topo_order(inst))
                if real != lb:
                    raise ValueError('bad open bound')
                for j in range(n):
                    if not _allowed(inst, h, j, dom):
                        raise ValueError('empty open box')
                opens += 1
                lower.append(lb)
                ledger['open_leaves'] += 1
                ledger['holes'] += 1
                if reason not in ('budget', 'depth'):
                    ledger['expanded'] += 1
                    ledger['lp'] += 1
                    if reason == 'cert':
                        ledger['cert_lp'] += 1
                ledger['height'] = max(ledger['height'], depth)
            elif tag == b'Y':
                cnt = struct.unpack('<H', rd.read(2))[0]
                if cnt != n:
                    raise ValueError('bad schedule length')
                starts = list(struct.unpack('<%dH' % n, rd.read(2 * n)))
                machs = list(rd.read(n))
                cmax = max(starts[i] + inst['p'][i] for i in range(n))
                if not check_schedule(inst, cmax, starts, machs):
                    raise ValueError('bad schedule')
                yes_vals.append(cmax)
                lower.append(local_bound(inst, h, _F(inst, h, dom),
                                         *_est_q(inst),
                                         topo_order(inst))[0])
                ledger['expanded'] += 1
                ledger['height'] = max(ledger['height'], depth)
            else:
                raise ValueError('bad tag %r' % (tag,))
        ok = True
        ledger['nodes'] = nodes
        L = min(lower) if lower else h + 1
        U = min(yes_vals) if yes_vals else None
        return dict(ok=ok, L=L, U=U, nodes=nodes, max_stack=max_stack,
                    reads=rd.reads, bytes=rd.bytes,
                    t=time.time() - t0, ledger=ledger, reason=None,
                    closed=closed, opens=opens)
    except Exception as e:
        return dict(ok=False, reason=type(e).__name__ + ':' + str(e),
                    L=None, U=None, nodes=locals().get('nodes', 0),
                    max_stack=locals().get('max_stack', 0),
                    reads=rd.reads, bytes=rd.bytes,
                    t=time.time() - t0, ledger={})
    finally:
        rd.close()
        if own:
            try:
                os.remove(path)
            except OSError:
                pass


_ESTQ = {}


def _est_q(inst):
    key = id(inst)
    v = _ESTQ.get(key)
    if v is None:
        v = heads_tails(inst, 0, [0] * inst['n'])
        _ESTQ[key] = v
    return v


class PagedProof(Proof):
    """A Proof wrapper around a compact PAGE stream."""
    kind = 'paged'

    def __init__(self, inst, h, data, stats=None, interval=None):
        super().__init__(inst, h)
        self.data = bytes(data)
        self.stats = dict(stats or {})
        self.interval = interval

    def audit_rdf(self):
        r = audit_compact(self.inst, self.h, data=self.data, block=256)
        return bool(r['ok'])

    def proof_complete(self):
        return self.audit_rdf()

    def audit(self, block=256):
        return audit_compact(self.inst, self.h, data=self.data, block=block)
