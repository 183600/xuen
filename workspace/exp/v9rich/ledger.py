"""RICH ledger: durable, content-addressed certificates for ICF/frontier.

The ledger is deliberately not a solver.  It stores *audited* states and
proofs as canonical JSON objects, indexes them by a full-content SHA-256
key, and (for proof leaves) builds a suffix-array archive that lets a new
certificate share a long suffix with an old one.  Every read is followed
by the ordinary checker; a hash collision or a corrupted entry is a cache
miss, never a verdict.
"""
import base64
import hashlib
import json
import pickle
import sys
import time

sys.path[:0] = [
    'exp/v9rich', 'exp/v9acf', 'exp/v9ai', 'exp/v9a', 'exp/v10d',
    'exp/v9y', 'exp/v9z', 'exp/v9m', 'exp/v8u', 'exp/v8o', 'exp/v8i',
    'exp/v8h', 'exp/v8j', 'exp/v8f', 'exp/v8e', 'exp/v8g', 'exp/v8c',
    'exp/v9d', 'exp/v9c', 'exp/v9b', 'exp/v8a', 'exp/v76', 'exp/v72',
    'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13', 'exp/v9f']

from icf import CertLeafProof, FrontierProof, PartialCertificate, ICFCertificate
from sage import BranchProof, SubsumptionProof, _domain
from apex import BoundProof, EnergyProof, FarkasProof
from cert import verify
from rdf import check_schedule
from suffix_store import SuffixProofStore, cert_tokens
from aidf import (AIDFrontierProof, LiftedFrontierProof, Closed, Open,
                  Split, leaves as aid_leaves)


class UnsupportedProof(Exception):
    pass


# --------------------------------------------------------------- JSON
def _jsonify(x):
    if x is None or isinstance(x, (bool, int, str)):
        return x
    if isinstance(x, float):
        return x
    if isinstance(x, dict):
        return {str(k): _jsonify(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonify(v) for v in x]
    if isinstance(x, (set, frozenset)):
        return sorted((_jsonify(v) for v in x), key=repr)
    try:
        import numpy as np
        if isinstance(x, np.integer):
            return int(x)
        if isinstance(x, np.floating):
            return float(x)
    except Exception:
        pass
    if hasattr(x, 'item'):
        try:
            return _jsonify(x.item())
        except Exception:
            pass
    raise UnsupportedProof('not json-safe: %r' % (type(x),))


def dumps(obj):
    return json.dumps(_jsonify(obj), sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False)


def digest(obj):
    return hashlib.sha256(dumps(obj).encode('utf-8')).hexdigest()


def short_digest(obj, bits=16):
    return digest(obj)[:max(1, bits // 4)]


def instance_fp(inst):
    return digest(dict(n=inst['n'], m=inst['m'], p=list(inst['p']),
                       pred=[list(x) for x in inst['pred']],
                       elig=[list(x) for x in inst['elig']]))


def cmax(inst, starts):
    return max(starts[i] + inst['p'][i] for i in range(inst['n']))


# ------------------------------------------------------------- proofs
def _enc_F(F):
    return sorted((int(i), int(t)) for i, t in F)


def _enc_branch_tree(node):
    tag = node[0]
    if tag == 'leaf':
        return {'t': 'leaf', 'F': _enc_F(node[1]),
                'cert': _jsonify(node[2])}
    if tag == 'empty':
        return {'t': 'empty', 'F': _enc_F(node[1]), 'job': int(node[2])}
    _, i, mid, F, lo, hi = node
    return {'t': 'node', 'i': int(i), 'mid': int(mid), 'F': _enc_F(F),
            'lo': _enc_branch_tree(lo), 'hi': _enc_branch_tree(hi)}


def _dec_branch_tree(obj):
    tag = obj['t']
    if tag == 'leaf':
        return ('leaf', frozenset(map(tuple, obj['F'])), obj['cert'])
    if tag == 'empty':
        return ('empty', frozenset(map(tuple, obj['F'])), int(obj['job']))
    return ('node', int(obj['i']), int(obj['mid']),
            frozenset(map(tuple, obj['F'])),
            _dec_branch_tree(obj['lo']), _dec_branch_tree(obj['hi']))


def _enc_aid_node(x):
    if isinstance(x, Split):
        return {'t': 'split', 'lo': list(x.lo), 'hi': list(x.hi),
                'i': int(x.job), 'mid': int(x.mid), 'depth': int(x.depth),
                'left': _enc_aid_node(x.left),
                'right': _enc_aid_node(x.right)}
    if isinstance(x, Open):
        return {'t': 'open', 'lo': list(x.lo), 'hi': list(x.hi),
                'lb': int(x.lb), 'depth': int(x.depth)}
    return {'t': 'closed', 'lo': list(x.lo), 'hi': list(x.hi),
            'kind': x.kind,
            'cert': _jsonify(x.cert) if x.cert is not None else None,
            'lb': None if x.lb is None else int(x.lb),
            'why': _jsonify(x.why) if x.why is not None else None}


def _dec_aid_node(obj):
    t = obj['t']
    if t == 'split':
        return Split(obj['lo'], obj['hi'], int(obj['i']), int(obj['mid']),
                     _dec_aid_node(obj['left']),
                     _dec_aid_node(obj['right']), int(obj['depth']))
    if t == 'open':
        return Open(obj['lo'], obj['hi'], int(obj['lb']),
                    int(obj['depth']))
    return Closed(obj['lo'], obj['hi'], obj['kind'], cert=obj.get('cert'),
                  lb=obj.get('lb'), why=obj.get('why'))


def encode_proof(p):
    if p is None:
        return None
    if isinstance(p, CertLeafProof):
        return {'t': 'icf-leaf', 'h': int(p.h), 'F': _enc_F(p.forbid0),
                'cert': _jsonify(p.cert)}
    if isinstance(p, BranchProof):
        return {'t': 'branch', 'h': int(p.h),
                'forbid0': _enc_F(p.forbid0),
                'tree': _enc_branch_tree(p.tree)}
    if isinstance(p, SubsumptionProof):
        return {'t': 'lb-no', 'h': int(p.h),
                'source': encode_proof(p.source)}
    if isinstance(p, BoundProof):
        return {'t': 'bound', 'h': int(p.h), 'value': int(p.value)}
    if isinstance(p, EnergyProof):
        return {'t': 'energy', 'h': int(p.h),
                'cert': _jsonify(p.cert)}
    if isinstance(p, FarkasProof):
        return {'t': 'farkas', 'h': int(p.h),
                'cert': _jsonify(p.cert)}
    if isinstance(p, AIDFrontierProof):
        return {'t': 'aid-frontier', 'h': int(p.h),
                'box_h': int(p.box_h), 'tree': _enc_aid_node(p.tree)}
    if isinstance(p, LiftedFrontierProof):
        return {'t': 'aid-lift', 'h': int(p.h),
                'source_h': int(p.source_h), 'box_h': int(p.box_h),
                'tree': _enc_aid_node(p.tree)}
    raise UnsupportedProof(type(p).__name__)


def decode_proof(inst, obj):
    if obj is None:
        return None
    t = obj['t']
    h = int(obj['h'])
    if t == 'icf-leaf':
        return CertLeafProof(inst, h, frozenset(map(tuple, obj['F'])),
                             obj['cert'])
    if t == 'branch':
        return BranchProof(inst, h, _dec_branch_tree(obj['tree']),
                           forbid0=frozenset(map(tuple, obj['forbid0'])))
    if t == 'lb-no':
        return SubsumptionProof(inst, h, decode_proof(inst, obj['source']))
    if t == 'bound':
        return BoundProof(inst, h, int(obj['value']))
    if t == 'energy':
        return EnergyProof(inst, h, obj['cert'])
    if t == 'farkas':
        return FarkasProof(inst, h, obj['cert'])
    if t == 'aid-frontier':
        return AIDFrontierProof(inst, h, _dec_aid_node(obj['tree']),
                                box_h=obj.get('box_h', h))
    if t == 'aid-lift':
        return LiftedFrontierProof(inst, h, int(obj['source_h']),
                                   _dec_aid_node(obj['tree']),
                                   box_h=obj.get('box_h', obj['source_h']))
    raise UnsupportedProof(t)


def leaf_certs(p):
    """All leaf certificates in a proof, in a deterministic order."""
    if p is None:
        return []
    if isinstance(p, CertLeafProof):
        return [p.cert]
    if isinstance(p, BranchProof):
        out = []

        def rec(node):
            tag = node[0]
            if tag == 'leaf':
                out.append(node[2])
            elif tag == 'empty':
                out.append({'kind': 'empty', 'job': int(node[2])})
            else:
                rec(node[4])
                rec(node[5])

        rec(p.tree)
        return out
    if isinstance(p, SubsumptionProof):
        return leaf_certs(p.source)
    if isinstance(p, (AIDFrontierProof, LiftedFrontierProof)):
        out = []
        for x in aid_leaves(p.tree):
            if isinstance(x, Closed) and x.cert is not None and \
                    x.kind in ('farkas', 'packing'):
                out.append(x.cert)
        return out
    return []


# ----------------------------------------------------------- ICF state
def encode_icf_state(inst, C):
    return {'kind': 'icf-state', 'fp': instance_fp(inst),
            'L': int(C.L), 'U': int(C.U),
            's': list(C.schedule) if C.schedule is not None else None,
            'm': list(C.machine) if C.machine is not None else None,
            'probe': int(getattr(C, 'probe', 0)),
            'proof': encode_proof(C.lb_proof)}


class FrontierStateCertificate:
    """L <= OPT <= U with a frontier NO(L-1) proof and a schedule of U."""

    kind = 'rich-frontier'

    def __init__(self, inst, L, U, schedule, machine, frontier):
        self.inst = inst
        self.L = int(L)
        self.U = int(U)
        self.schedule = list(schedule) if schedule is not None else None
        self.machine = list(machine) if machine is not None else None
        self.frontier = frontier

    def audit_rdf(self):
        try:
            if self.frontier is None:
                return False
            target = getattr(self.frontier, 'target', None)
            if target is None:
                target = getattr(self.frontier, 'h', None)
            if target != self.L - 1:
                return False
            if not self.frontier.audit_rdf():
                return False
            if self.L > self.U:
                return False
            if self.schedule is None or self.machine is None:
                return False
            c = cmax(self.inst, self.schedule)
            return c == self.U and bool(check_schedule(
                self.inst, c, self.schedule, self.machine))
        except Exception:
            return False

    def proof_complete(self):
        return self.audit_rdf()


def encode_frontier_tree(node):
    tag = node[0]
    if tag == 'leaf':
        _, F, h, proof = node
        return {'t': 'leaf', 'F': _enc_F(F), 'h': int(h),
                'proof': encode_proof(proof)}
    _, i, mid, F, lo, hi = node
    return {'t': 'split', 'i': int(i), 'mid': int(mid), 'F': _enc_F(F),
            'lo': encode_frontier_tree(lo),
            'hi': encode_frontier_tree(hi)}


def decode_frontier_tree(inst, obj):
    if obj['t'] == 'leaf':
        return ('leaf', frozenset(map(tuple, obj['F'])), int(obj['h']),
                decode_proof(inst, obj['proof']))
    return ('split', int(obj['i']), int(obj['mid']),
            frozenset(map(tuple, obj['F'])),
            decode_frontier_tree(inst, obj['lo']),
            decode_frontier_tree(inst, obj['hi']))


def encode_frontier_state(inst, C):
    if isinstance(C.frontier, (AIDFrontierProof, LiftedFrontierProof)):
        return {'kind': 'frontier-state', 'ft': 'aid',
                'fp': instance_fp(inst),
                'L': int(C.L), 'U': int(C.U),
                's': list(C.schedule) if C.schedule is not None else None,
                'm': list(C.machine) if C.machine is not None else None,
                'proof': encode_proof(C.frontier)}
    return {'kind': 'frontier-state', 'fp': instance_fp(inst),
            'L': int(C.L), 'U': int(C.U),
            'target': int(C.frontier.target),
            's': list(C.schedule) if C.schedule is not None else None,
            'm': list(C.machine) if C.machine is not None else None,
            'tree': encode_frontier_tree(C.frontier.tree)}


def decode_frontier_state(inst, obj):
    if obj.get('fp') != instance_fp(inst):
        raise ValueError('instance fingerprint mismatch')
    if obj.get('ft') == 'aid':
        fp = decode_proof(inst, obj['proof'])
        return FrontierStateCertificate(inst, int(obj['L']),
                                        int(obj['U']), obj['s'],
                                        obj['m'], fp)
    tree = decode_frontier_tree(inst, obj['tree'])
    fp = FrontierProof(inst, int(obj['target']), tree)
    return FrontierStateCertificate(inst, int(obj['L']), int(obj['U']),
                                    obj['s'], obj['m'], fp)


def encode_state(inst, C):
    if isinstance(C, (PartialCertificate, ICFCertificate)):
        return encode_icf_state(inst, C)
    if isinstance(C, FrontierStateCertificate):
        return encode_frontier_state(inst, C)
    raise UnsupportedProof('state %r' % (type(C),))


def decode_state(inst, obj):
    if obj['kind'] == 'icf-state':
        if obj.get('fp') != instance_fp(inst):
            raise ValueError('instance fingerprint mismatch')
        proof = decode_proof(inst, obj['proof'])
        C = PartialCertificate(inst, obj['L'], obj['U'], obj['s'],
                               obj['m'], proof, probe=obj.get('probe', 0))
        if C.L == C.U:
            return ICFCertificate(inst, C.U, C.schedule, C.machine, proof)
        return C
    if obj['kind'] == 'frontier-state':
        return decode_frontier_state(inst, obj)
    raise UnsupportedProof(obj['kind'])


# ----------------------------------------------------------- ledger
class StateLedger:
    """Full-content hash table plus a hash-chain checkpoint sequence.

    `hash_bits` is deliberately configurable so the collision test can use
    a tiny digest.  Even then, a lookup compares the entire canonical JSON
    string, so a collision cannot produce a wrong state.
    """

    def __init__(self, hash_bits=256):
        self.hash_bits = int(hash_bits)
        self.entries = []
        self.buckets = {}
        self.chain = []
        self.stats = dict(commits=0, hits=0, collisions=0,
                          restore_ok=0, restore_bad=0,
                          corrupt_detected=0, corrupt_missed=0)

    def _key(self, text):
        h = hashlib.sha256(text.encode('utf-8')).hexdigest()
        return h[:max(1, self.hash_bits // 4)]

    def commit(self, obj):
        text = dumps(obj)
        key = self._key(text)
        bucket = self.buckets.setdefault(key, [])
        for full, idx in bucket:
            if full == text:
                self.stats['hits'] += 1
                self.chain.append(idx)
                return idx
        if bucket:
            self.stats['collisions'] += 1
        idx = len(self.entries)
        self.entries.append(text)
        bucket.append((text, idx))
        self.chain.append(idx)
        self.stats['commits'] += 1
        return idx

    def get(self, idx):
        return json.loads(self.entries[idx])

    def lookup(self, obj):
        text = dumps(obj)
        key = self._key(text)
        for full, idx in self.buckets.get(key, []):
            if full == text:
                return idx
        return None

    def audit_entry(self, inst, idx):
        try:
            return bool(decode_state(inst, self.get(idx)).audit_rdf())
        except Exception:
            return False

    def latest_verified(self, inst):
        """Walk the chain backwards until an entry audits."""
        for idx in reversed(self.chain):
            if self.audit_entry(inst, idx):
                self.stats['restore_ok'] += 1
                return idx
        self.stats['restore_bad'] += 1
        return None


class ProofLeafArchive:
    """Suffix-array archive over leaf-certificate token strings."""

    def __init__(self, min_match=2):
        self.store = SuffixProofStore(min_match=min_match)
        self.certs = []

    def add(self, cert):
        self.certs.append(cert)
        self.store.add(cert)

    def build(self):
        t0 = time.time()
        self.store.build()
        self.stats = dict(self.store.stats)
        self.stats['build_wall'] = round(time.time() - t0, 5)
        return self.stats

    def reconstruct_all(self):
        bad = 0
        for k in range(len(self.certs)):
            if self.store.get(k) != cert_tokens(self.certs[k]):
                bad += 1
        return bad


# ----------------------------------------------------------- corruption
def mutate_semantic(inst, obj):
    """A deterministic semantic corruption of an encoded state."""
    z = json.loads(dumps(obj))
    kind = z.get('kind')
    if kind == 'icf-state':
        if z.get('s'):
            z['s'][0] = int(z['s'][0]) + 1
        else:
            z['L'] = int(z['L']) + 1
    elif kind == 'frontier-state':
        if z.get('s'):
            z['s'][0] = int(z['s'][0]) + 1
        else:
            z['L'] = int(z['L']) + 1
    else:
        z['tampered'] = True
    return z


def mutate_bytes(obj, pos=None):
    text = dumps(obj)
    if not text:
        return {'tampered': True}
    if pos is None:
        pos = len(text) // 2
    ch = '0' if text[pos] != '0' else '1'
    return json.loads(text[:pos] + ch + text[pos + 1:]) if False else \
        {'raw': text[:pos] + ch + text[pos + 1:]}
