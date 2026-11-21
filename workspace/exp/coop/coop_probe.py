#!/usr/bin/env python3
"""COOP local probe (pure python, reproducible).

E-COOP-1  lexical routing audit: dataset name -> teaser task name.
E-COOP-2  consensus decoding toy: independent vs correlated surface noise.
Only the 32 public task names / dataset names are used; no private eval data.
"""
import json, glob, os, re, random, math, itertools

WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LB = json.load(open(os.path.join(WS, 'exp/r16_leaderboard_data.json')))
TASKS = LB['tasks']
DS = sorted(os.path.basename(p)[:-10] for p in glob.glob(os.path.join(WS, 'exp/round_mv/*_info.json')))

# verified semantic mapping dataset -> teaser task (manual, auditable)
PAIRS = {
 'ArrangePlates':'Clear Plates','ArrangeTestTubes':'Arrange Test Tubes','ColorArrangement':'Color Arrangement',
 'ConveyorSorting':'Conveyor Food Sorting','DisconnectEthernet':'Disconnect Ethernet','FoldTowel':'Fold Towel',
 'FruitCollection':'Fruit Basket Collection','FruitSorting':'Fruit Sorting','HangCup':'Hang the Cup',
 'OrganizeBookshelf':'Organize Bookshelf','OrganizePencilCase':'Organize Pencil Case','OrganizeStationery':'Organize Stationery',
 'OrganizeTools':'Organize Tools','PackBag':'Pack Bag','PackDoll':'Pack the Doll','PackPhone':'Pack Phone',
 'PaperCupStacking':'Paper Cup Stacking','PickOutBatteries':'Pick Out Battery','PlacePhotoFrame':'Place Photo Frames',
 'PlugCharger':'Plug Charger','PlugInEthernet':'Plug In Ethernet','PourOutMedicine':'Open Pill Bottle',
 'RemovePinnedNote':'Remove Pinned Note','SpellRobot':'Spell robot','StackBowls':'Stack Bowls','StoreCups':'Stack Cups',
 'StoreEarphones':'Store Earphones','StorePaddle':'Store Racket','SyringeWaterTransfer':'Syringe Water Transfer',
 'ToolboxStorage':'Toolbox Storage','Unlock':'Unlock','ZipUp':'Zip Up'}
assert len(PAIRS) == 32 and set(PAIRS.values()) == set(TASKS)

def split_camel(s): return re.sub(r'(?<!^)(?=[A-Z])', ' ', s).lower()
def toks(s): return re.findall(r'[a-z0-9]+', s.lower())
def trigrams(s):
    s = ' ' + re.sub(r'[^a-z0-9]', '', s.lower()) + ' '
    return set(s[i:i+3] for i in range(len(s)-2))

def cosine(a, b):
    if not a or not b: return 0.0
    inter = len(a & b)
    return inter / math.sqrt(len(a) * len(b))

def route(query, protos):
    q = trigrams(query)
    scores = [(cosine(q, p), k) for k, p in protos.items()]
    scores.sort(reverse=True)
    return scores[0][1], scores

# ---- E-COOP-1: baseline lexical router on dataset names ----
protos = {t: trigrams(t) for t in TASKS}
base_ok, hard = 0, []
for d in DS:
    gold = PAIRS[d]
    pred, _ = route(split_camel(d), protos)
    if pred == gold: base_ok += 1
    else: hard.append((d, gold, pred))
print('E-COOP-1 baseline lexical top-1: %d/32' % base_ok)
for d, g, p in hard: print('   MISS %-22s gold=%-22s pred=%s' % (d, g, p))

# ---- E-COOP-1b: alias-aware co-created ontology (add known surface forms) ----
surface = {t: {t} for t in TASKS}
for d, g in PAIRS.items():
    surface[g].add(split_camel(d))
    surface[g].add(d)
def route_cloud(query, clouds):
    q = trigrams(query)
    best = (-1, None)
    for t, forms in clouds.items():
        s = max(cosine(q, trigrams(f)) for f in forms)
        if s > best[0]: best = (s, t)
    return best[1]
ok2 = sum(route_cloud(split_camel(d), surface) == PAIRS[d] for d in DS)
print('E-COOP-1b alias-aware cloud top-1: %d/32' % ok2)

# ---- E-COOP-2: consensus decoding under surface noise ----
SYN = {'clear':'arrange','plates':'dishes','stack':'store','cups':'mugs','open':'pour out','pill':'medicine',
       'bottle':'vial','racket':'paddle','basket':'collection','food':'conveyor','battery':'batteries',
       'frames':'frame','towel':'cloth','bag':'backpack','tools':'tool','bookshelf':'shelf'}
def perturb(s, rng):
    w = toks(s)
    out = []
    for x in w:
        r = rng.random()
        if r < 0.18: continue                      # drop
        if r < 0.36 and x in SYN: out.append(SYN[x])  # synonym
        else: out.append(x)
    if not out: out = w[:1]
    rng.shuffle(out)                                # order noise
    return ' '.join(out)

def vote(views, protos):
    c = {}
    for v in views:
        p, _ = route(v, protos)
        c[p] = c.get(p, 0) + 1
    return max(c.items(), key=lambda kv: kv[1])[0]

def run(K, correlated, trials=200, seed=0):
    rng = random.Random(seed); hit = 0; tot = 0
    for t in TASKS:
        for _ in range(trials):
            if correlated:
                # one shared noise draw = all 'languages' share the same MT errors
                shared = rng.random()
                views = [perturb(t, random.Random(shared)) for _ in range(K)]
            else:
                views = [perturb(t, random.Random(rng.random())) for _ in range(K)]
            hit += (vote(views, protos) == t); tot += 1
    return hit / tot

print('E-COOP-2 consensus accuracy (single-view base = %.3f)' % run(1, False))
for K in (3, 5, 9, 15):
    print('   K=%2d  independent=%.3f  correlated=%.3f' % (K, run(K, False), run(K, True)))

out = {'baseline_lexical_top1': base_ok, 'alias_aware_top1': ok2,
       'hard_misses': hard, 'n_tasks': len(TASKS),
       'consensus': {'K%d' % K: {'indep': run(K, False), 'corr': run(K, True)} for K in (1,3,5,9,15)}}
json.dump(out, open(os.path.join(WS, 'exp/coop/coop_probe.json'), 'w'), ensure_ascii=False, indent=2)
print('wrote exp/coop/coop_probe.json')
