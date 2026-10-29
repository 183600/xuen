import sys
import json
import time

sys.path[:0] = ['exp/v9talc']
from loose import rows, init_loose, probe_table, static_features


def main():
    out = []
    t0 = time.time()
    for k, (tag, name, idx, inst, known) in enumerate(rows()):
        z = init_loose(inst)
        if z is None:
            out.append(dict(corpus=tag, name=name, idx=idx,
                            known=known, error='init'))
            continue
        sf = static_features(inst, z['est'], z['q'])
        tab = probe_table(inst, z['L'], z['U'])
        out.append(dict(corpus=tag, name=name, idx=idx, known=known,
                        L=z['L'], U=z['U'], init_lp=z['init_lp'],
                        sf=sf,
                        tab={str(h): r for h, r in tab.items()}))
        if (k + 1) % 25 == 0:
            print('built', k + 1, 'elapsed', round(time.time() - t0, 1),
                  flush=True)
    with open('exp/v9talc/loose_data.json', 'w') as f:
        json.dump(out, f)
    print('rows', len(out), 'elapsed', round(time.time() - t0, 1))
    print('errors', sum('error' in r for r in out))


if __name__ == '__main__':
    main()
