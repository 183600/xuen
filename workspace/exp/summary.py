import json, statistics as st
base='/home/runner/work/xuen/xuen/workspace/exp/'
tr=json.load(open(base+'proto_tent_root.json'))
print('=== root threshold (30) ===')
for key in ('L0','old','new'):
    vals=[r[key] for r in tr]
    print(key,'sum',sum(vals),'mean',round(sum(vals)/len(vals),3))
print('new>old',sum(r['new']>r['old'] for r in tr),
      'new<old',sum(r['new']<r['old'] for r in tr),
      'new==opt',sum(r['new']==r['opt'] for r in tr),
      'old==opt',sum(r['old']==r['opt'] for r in tr),
      'new<=opt',sum(r['new']<=r['opt'] for r in tr))
print('gains old',sum(r['old']-r['L0'] for r in tr),'new',sum(r['new']-r['L0'] for r in tr))
print('BP tests old',sum(r['nf'] for r in tr),'tent',sum(r['nt'] for r in tr))
pd=json.load(open(base+'proto_dom.json'))
print('\n=== quotient dominance ===')
print('c',sum(r['c'] for r in pd),'est',sum(r['est'] for r in pd),
      'wins',sum(r['est']<r['c'] for r in pd),'ties',sum(r['est']==r['c'] for r in pd),
      'loss',sum(r['est']>r['c'] for r in pd))
pe=json.load(open(base+'proto_eps.json'))
print('\n=== eps dominance ===')
print('d0',sum(r['n0'] for r in pe),'d1',sum(r['n1'] for r in pe),'d2',sum(r['n2'] for r in pe))
print('d1 wins',sum(r['n1']<r['n0'] for r in pe),'loss',sum(r['n1']>r['n0'] for r in pe),
      'd2 wins',sum(r['n2']<r['n0'] for r in pe),'loss',sum(r['n2']>r['n0'] for r in pe))
print('U>opt d1',sum(r['up1']>0 for r in pe),'d2',sum(r['up2']>0 for r in pe))
pf=json.load(open(base+'proto_full.json'))
print('\n=== full search ===')
for key in ('n0','nold','nt','nd'):
    print(key,sum(r[key] for r in pf))
print('TENT vs L0 wins',sum(r['nt']<r['n0'] for r in pf),'loss',sum(r['nt']>r['n0'] for r in pf))
print('TENT vs OLD wins',sum(r['nt']<r['nold'] for r in pf),'loss',sum(r['nt']>r['nold'] for r in pf))
print('delta1 vs TENT wins',sum(r['nd']<r['nt'] for r in pf),'loss',sum(r['nd']>r['nt'] for r in pf))
print('wall L0',round(sum(r['t0'] for r in pf),3),'OLD',round(sum(r['told'] for r in pf),3),
      'TENT',round(sum(r['tt'] for r in pf),3),'delta',round(sum(r['td'] for r in pf),3))
print('\nhard per-instance:')
for r in pf:
    if r['n0']>20 or r['nt']>20:
        print(r['k'],'opt',r['opt'],'L0',r['L0'],'Lg',r['Lg'],'n',r['n0'],r['nold'],r['nt'],'d1',r['nd'])
