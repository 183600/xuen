"""Anytime curves with a *total* LP budget (search + cover calls)."""
import sys, pickle, json, time
sys.path[:0] = ['exp/v75', 'exp/v73', 'exp/v71', 'exp/v61', 'exp/v60', 'exp/v13']
from qnc import QNC, Budget
from qcc import QCC
from qlc import QLC

FILES = {
    'holdout50': 'exp/v20/holdout_cases50.pkl',
    'synth45': 'exp/v28/synth2_45.pkl',
    'large_a': 'exp/v14/large_a.pkl',
    'large_b': 'exp/v14/large_b.pkl',
    'large_het': 'exp/v14/large_het.pkl',
    'hard3': 'exp/v13/hard3.pkl',
    'deep8': 'exp/v18/deep.pkl',
}


def load(f):
    d = pickle.load(open(f, 'rb'))
    return [(x[0], x[1]) if isinstance(x, tuple) else (x['inst'], x['opt'])
            for x in d]


def corpus():
    return [(name, idx, inst, opt - 1)
            for name, f in FILES.items()
            for idx, (inst, opt) in enumerate(load(f))]


def perturb():
    return [(name, k, inst, opt - 1) for (name, k, inst, opt, an, al)
            in pickle.load(open('exp/v71/perturb60.pkl', 'rb'))]


def branch51():
    return [(r['src'], r['idx'], r['inst'], r['h'])
            for r in pickle.load(open('exp/v81/h5h47_branch.pkl', 'rb'))]


class TotalQLC(QLC):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.total_lp = 0

    def _solve(self, bounds, max_rounds, topk):
        before = self.lp_solves
        res, z = super()._solve(bounds, max_rounds, topk)
        self.total_lp += self.lp_solves - before
        return res, z

    def _cover_lp(self):
        if self.total_lp >= self.budget:
            raise Budget
        self.total_lp += 1
        return super()._cover_lp()


class TotalQCC(QCC):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.total_lp = 0

    def _solve(self, bounds, max_rounds, topk):
        before = self.lp_solves
        res, z = super()._solve(bounds, max_rounds, topk)
        self.total_lp += self.lp_solves - before
        return res, z

    def _cover_lp(self):
        if self.total_lp >= self.budget:
            raise Budget
        self.total_lp += 1
        return super()._cover_lp()


def run(cases, budgets, cls, kw):
    out = []
    for b in budgets:
        no = unk = 0
        for name, idx, inst, h in cases:
            q = cls(inst, h, **kw)
            v, st = q.decide(budget=b, nodecap=10000)
            no += int(v is False)
            unk += int(v is None)
        out.append(dict(budget=b, no=no, unk=unk))
        print(cls.__name__, b, no, unk, flush=True)
    return out


if __name__ == '__main__':
    budgets = list(range(0, 13))
    cases = corpus() + perturb()
    out = {}
    out['corpus201'] = {}
    out['corpus201']['qnc'] = run(cases, budgets, QNC, {})
    out['corpus201']['qcc'] = run(cases, budgets, TotalQCC,
                                  dict(use_cover=True, cover_min_k=1))
    out['corpus201']['qlc'] = run(cases, budgets, TotalQLC,
                                  dict(use_cover=True, cover_min_k=1))
    cases = branch51()
    out['branch51'] = {}
    out['branch51']['qnc'] = run(cases, budgets, QNC, {})
    out['branch51']['qcc'] = run(cases, budgets, TotalQCC,
                                 dict(use_cover=True, cover_min_k=1))
    out['branch51']['qlc'] = run(cases, budgets, TotalQLC,
                                 dict(use_cover=True, cover_min_k=1))
    json.dump(out, open('exp/v75/anytime_qlc.json', 'w'), indent=1)
    print('saved exp/v75/anytime_qlc.json')
