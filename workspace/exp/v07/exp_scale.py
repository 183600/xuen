import sys, json, random, time
sys.path.insert(0, '.'); sys.path.insert(0, '..')
import exp_da as E, kern, ge

def main():
    rng = random.Random(4242)
    rows = []
    for n in (11, 12, 13):
        for t in range(4):
            inst = E.gen_instance(n, 0.3, 8, rng)
            inst['pmask'] = [sum(1 << j for j in inst['pred'][i]) for i in range(n)]
            S0, A0, c0 = 0, (0, 0), (-1,) * n
            try:
                t0 = time.time(); opt = kern.state_opt(inst, S0, A0, c0, nodecap=4_000_000)
                t_opt = time.time() - t0
            except TimeoutError:
                opt = None; t_opt = None
            U = E.guide(inst, S0, A0, c0)
            memo = ge.make_memo()
            t0 = time.time()
            proved, U2, st = ge.ge_step(inst, S0, A0, c0, U, memo, nodecap=2_000_000)
            t_ge = time.time() - t0
            rows.append(dict(n=n, t=t, opt=opt, U0=U, proved=proved, U2=U2,
                             nodes=st['nodes'], calls=st['calls'],
                             t_ge=round(t_ge, 3), t_opt=round(t_opt, 3) if t_opt else None,
                             ok=(opt is None or U2 == opt)))
            print(rows[-1], flush=True)
    json.dump(rows, open('scale.json', 'w'), indent=1)

if __name__ == '__main__':
    main()
