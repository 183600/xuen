"""A small DRAT/RUP checker for proof-carrying SAT experiments.

The checker maintains a clause database with two watched literals per
clause.  Every added clause must be RUP (reverse unit propagation) or,
optionally, RAT (resolution asymmetric tautology).  Deletions are
honoured.  The final empty clause is required.
"""


class Clause:
    __slots__ = ('lits', 'w0', 'w1', 'active', 'cid')

    def __init__(self, lits, cid):
        self.lits = list(lits)
        self.w0 = 0
        self.w1 = 1 if len(self.lits) > 1 else 0
        self.active = True
        self.cid = cid


class RUPChecker:
    def __init__(self, clauses, nvars=None):
        self.nvars = int(nvars or 0)
        self.db = {}
        self.clauses = []
        self.watch = {}
        self.units = []
        self.assign = {}
        self.trail = []
        self.qhead = 0
        self.rup_steps = 0
        self.rat_steps = 0
        self.taut_steps = 0
        self.fail = None
        self.max_var = self.nvars
        for cl in clauses:
            self.add_clause(cl, check=False)

    # ---------------------------------------------------------------- db
    def _lit_index(self, lit):
        v = abs(lit)
        if v > self.max_var:
            self.max_var = v
        return lit

    def _attach(self, cl):
        if len(cl.lits) >= 1:
            self.watch.setdefault(cl.lits[cl.w0], []).append(cl)
        if len(cl.lits) >= 2:
            self.watch.setdefault(cl.lits[cl.w1], []).append(cl)
        if len(cl.lits) == 0:
            self.fail = 'empty-input'
        if len(cl.lits) == 1:
            self.units.append(cl)

    def add_clause(self, lits, check=True):
        lits = [self._lit_index(l) for l in lits]
        if any(-l in lits for l in lits):
            self.taut_steps += 1
            return True
        if len(lits) == 0:
            self.fail = 'empty'
            return True
        cid = len(self.clauses)
        cl = Clause(lits, cid)
        self.clauses.append(cl)
        key = tuple(sorted(set(lits)))
        self.db.setdefault(key, []).append(cl)
        self._attach(cl)
        if check:
            return self.check_rup(lits)
        return True

    def delete_clause(self, lits):
        key = tuple(sorted(set(lits)))
        bucket = self.db.get(key)
        if not bucket:
            return
        cl = bucket.pop()
        cl.active = False
        if not bucket:
            self.db.pop(key, None)
        if len(cl.lits) == 1:
            try:
                self.units.remove(cl)
            except ValueError:
                pass

    # -------------------------------------------------------- assignment
    def _value(self, lit):
        v = self.assign.get(abs(lit), 0)
        return v if lit > 0 else -v

    def _assign_lit(self, lit, source=None):
        v = abs(lit)
        val = 1 if lit > 0 else -1
        old = self.assign.get(v, 0)
        if old == 0:
            self.assign[v] = val
            self.trail.append(lit)
            return True
        return old == val

    def _propagate(self):
        while self.qhead < len(self.trail):
            lit = self.trail[self.qhead]
            self.qhead += 1
            false_lit = -lit
            ws = self.watch.get(false_lit, [])
            i = 0
            while i < len(ws):
                cl = ws[i]
                if not cl.active:
                    ws[i] = ws[-1]
                    ws.pop()
                    continue
                # make sure the false literal is the first watch
                if cl.lits[cl.w1] == false_lit:
                    cl.w0, cl.w1 = cl.w1, cl.w0
                if cl.lits[cl.w0] != false_lit:
                    # stale watch
                    ws[i] = ws[-1]
                    ws.pop()
                    continue
                other = cl.lits[cl.w1]
                if self._value(other) == 1:
                    i += 1
                    continue
                found = -1
                for j, l in enumerate(cl.lits):
                    if j == cl.w0 or j == cl.w1:
                        continue
                    if self._value(l) != -1:
                        found = j
                        break
                if found >= 0:
                    cl.lits[cl.w0], cl.lits[found] = cl.lits[found], cl.lits[cl.w0]
                    ws[i] = ws[-1]
                    ws.pop()
                    self.watch.setdefault(cl.lits[cl.w0], []).append(cl)
                    continue
                if self._value(other) == -1:
                    return False
                self._assign_lit(other, cl)
                i += 1
        return True

    def _reset(self):
        self.assign = {}
        self.trail = []
        self.qhead = 0

    def check_rup(self, lits):
        self._reset()
        for l in lits:
            if not self._assign_lit(-l):
                self.rup_steps += 1
                return True
        for cl in self.units:
            if cl.active and not self._assign_lit(cl.lits[0]):
                self.rup_steps += 1
                return True
        ok = self._propagate()
        if ok:
            return False
        self.rup_steps += 1
        return True

    # ---------------------------------------------------------------- RAT
    def check_rat(self, lits):
        if not lits:
            return False
        pivot = lits[0]
        for cl in list(self.watch.get(-pivot, [])):
            if not cl.active:
                continue
            rest = [l for l in cl.lits if l != -pivot]
            resolvent = list(lits) + rest
            # tautology check
            s = set(resolvent)
            if any(-l in s for l in s):
                continue
            # dedupe
            rl = []
            seen = set()
            for l in resolvent:
                if l not in seen:
                    seen.add(l)
                    rl.append(l)
            if not self.check_rup(rl):
                return False
        self.rat_steps += 1
        return True

    def add_drat(self, line):
        toks = line.split()
        if not toks:
            return True
        if toks[0] == 'd':
            lits = [int(x) for x in toks[1:] if x != '0']
            self.delete_clause(lits)
            return True
        lits = [int(x) for x in toks if x != '0']
        if any(-l in lits for l in lits):
            self.taut_steps += 1
            return True
        cid = len(self.clauses)
        cl = Clause(lits, cid)
        self.clauses.append(cl)
        key = tuple(sorted(set(lits)))
        self.db.setdefault(key, []).append(cl)
        self._attach(cl)
        ok = self.check_rup(lits)
        if not ok:
            ok = self.check_rat(lits)
        if not ok:
            self.fail = 'non-rup line %r' % (lits,)
            return False
        return True
