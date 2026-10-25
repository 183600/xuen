"""Suffix-array proof archive for FTC-ALC certificates.

A certificate is canonicalized to a token sequence.  The archive reverses
each sequence (so a shared *suffix* becomes a shared prefix), concatenates
them with unique separators, and builds one suffix array plus its LCP
array.  Each certificate is stored as a prefix plus a back-reference to a
previously stored suffix.  Verification is unchanged: decompression is a
bijection back to the canonical token sequence, then the ordinary checker
replays the certificate.

The archive is an engineering layer, not part of the decision procedure.
"""
import time


def sa_doubling(s, upper=None):
    n = len(s)
    if n == 0:
        return []
    sa = list(range(n))
    rank = list(s)
    k = 1
    while True:
        sa.sort(key=lambda i: (rank[i], rank[i + k] if i + k < n else -1))
        new = [0] * n
        for j in range(1, n):
            a, b = sa[j - 1], sa[j]
            new[b] = new[a] + ((rank[a], rank[a + k] if a + k < n else -1)
                               < (rank[b], rank[b + k] if b + k < n else -1))
        rank = new
        if rank[sa[-1]] == n - 1:
            break
        k <<= 1
    return sa


def lcp_kasai(s, sa):
    n = len(s)
    rank = [0] * n
    for r, p in enumerate(sa):
        rank[p] = r
    lcp = [0] * max(0, n - 1)
    h = 0
    for i in range(n):
        r = rank[i]
        if r == n - 1:
            h = 0
            continue
        j = sa[r + 1]
        while i + h < n and j + h < n and s[i + h] == s[j + h]:
            h += 1
        lcp[r] = h
        if h:
            h -= 1
    return lcp


def _packing_tokens(d):
    toks = ['P', 's' + str(d.get('scale')), 'o' + str(d.get('obj'))]
    toks += ['b%s' % (tuple(t),) for t in d.get('beta', [])]
    toks += ['d%s' % (tuple(t),) for t in d.get('dom', [])]
    toks += ['e%s' % (tuple(t),) for t in d.get('exp', [])]
    toks += ['a%s' % (int(v),) for v in d.get('alpha', [])]
    toks += ['c%s' % (tuple(t),) for t in d.get('cuts', [])]
    return toks


def _energy_tokens(d):
    return ['E', 'a' + str(d.get('a')), 'b' + str(d.get('b')),
            'D' + str(d.get('demand')), 'C' + str(d.get('cap')),
            'M' + ','.join(map(str, d.get('M', []))),
            'J' + ','.join(map(str, d.get('jobs', [])))]


def cert_tokens(cert):
    if not isinstance(cert, dict):
        return ['?' + repr(cert)]
    kind = cert.get('kind')
    if kind == 'packing':
        return _packing_tokens(cert)
    if kind == 'energy':
        return _energy_tokens(cert)
    if kind == 'window':
        return ['W', str(cert.get('job')), str(cert.get('est')),
                str(cert.get('lst'))]
    return ['?' + repr(sorted(cert.items()))]


class SuffixProofStore:
    def __init__(self, min_match=4):
        self.min_match = min_match
        self.strings = []
        self.entries = []
        self.stats = dict(original=0, stored=0, refs=0, matches=0,
                          sa_t=0.0, build_t=0.0)

    def add(self, cert):
        toks = cert_tokens(cert)
        self.strings.append(toks)
        self.stats['original'] += len(toks)
        return len(self.strings) - 1

    def build(self):
        t0 = time.time()
        if not self.strings:
            return self
        # unique separator per string; 0 is the global terminator
        alphabet = {}
        seq = []
        starts = []
        owner = []
        for k, toks in enumerate(self.strings):
            starts.append(len(seq))
            rev = list(reversed(toks))
            for t in rev:
                v = alphabet.setdefault(t, len(alphabet) + 1)
                seq.append(v)
                owner.append(k)
            seq.append(-(k + 1))
            owner.append(k)
        seq.append(0)
        owner.append(-1)
        self.seq, self.starts, self.owner = seq, starts, owner
        sa = sa_doubling(seq)
        lcp = lcp_kasai(seq, sa)
        rank = [0] * len(seq)
        for r, p in enumerate(sa):
            rank[p] = r
        self.sa, self.lcp, self.rank = sa, lcp, rank
        self.stats['sa_t'] = round(time.time() - t0, 5)
        # Greedy: store prefix, back-reference the longest shared suffix.
        stored_full = []
        for k, toks in enumerate(self.strings):
            L = len(toks)
            pos = self.starts[k]
            r = rank[pos]
            best = 0
            best_src = None
            for nr in range(r - 64, r + 65):
                if nr < 0 or nr >= len(sa) or nr == r:
                    continue
                p = sa[nr]
                src = owner[p]
                if src is None or src < 0 or src >= k:
                    continue
                lim = min(L, self.starts[src + 1] - 1 - p if src + 1 < len(self.starts) else L)
                h = 0
                while h < lim and self.seq[pos + h] == self.seq[p + h]:
                    h += 1
                if h > best:
                    best, best_src, best_off = h, src, p - self.starts[src]
            if best >= self.min_match and best_src is not None:
                self.entries.append(('ref', L - best, best_src, best_off, best))
                self.stats['stored'] += (L - best) + 4
                self.stats['refs'] += 1
                self.stats['matches'] += best
            else:
                self.entries.append(('lit', toks))
                self.stats['stored'] += L + 1
                stored_full.append(k)
        self.stats['build_t'] = round(time.time() - t0, 5)
        return self

    def get(self, k):
        e = self.entries[k]
        if e[0] == 'lit':
            return list(e[1])
        _, plen, src, off, ln = e
        Lsrc = len(self.strings[src])
        return self.strings[k][:plen] + self.strings[src][Lsrc - off - ln:Lsrc - off]

    def _full(self, k):
        return list(self.strings[k])
