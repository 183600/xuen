import sys
import json
import time
import argparse

sys.path[:0] = ['exp/pano']
import pano

SYNTH_ARMS = [
    'single-lower-first',
    'single-lower-always',
    'single-geometric',
    'single-binary',
    'frontier-geometric-cap',
    'frontier-geometric-full',
    'frontier-lower-first-full',
]

CORPUS_ARMS = [
    'single-lower-first',
    'single-lower-always',
    'single-geometric',
    'single-binary',
    'frontier-geometric-cap',
    'frontier-geometric-full',
    'frontier-lower-first-full',
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('what', choices=('synth', 'corpus'))
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()
    if args.what == 'synth':
        rows = list(pano.synthetic_corpus())
        arms = SYNTH_ARMS
        init = 'chip'
        path = 'exp/pano/arms_synth.json'
        max_probes = 64
        max_leaves = 64
    else:
        rows = list(pano.corpora())
        arms = CORPUS_ARMS
        init = 'pact'
        path = 'exp/pano/arms_252.json'
        max_probes = 32
        max_leaves = 32
    if args.limit:
        rows = rows[:args.limit]
    out = []
    t0 = time.time()
    for n, (corpus, name, idx, inst, known) in enumerate(rows):
        feat = pano.instance_features(inst).tolist()
        for arm in arms:
            r = pano.run_arm(inst, known, name, idx, arm,
                             max_probes=max_probes, max_leaves=max_leaves,
                             init=init, audit=False)
            r['corpus'] = corpus
            r['features'] = feat
            r.pop('steps', None)
            out.append(r)
        if (n + 1) % 10 == 0:
            print(args.what, n + 1, '/', len(rows),
                  't', round(time.time() - t0, 1), flush=True)
    with open(path, 'w') as f:
        json.dump(dict(arms=arms, init=init, max_probes=max_probes,
                       max_leaves=max_leaves, rows=out), f, indent=1)
    print('wrote', path, 'rows', len(out), 'wall', round(time.time() - t0, 2))


if __name__ == '__main__':
    main()
