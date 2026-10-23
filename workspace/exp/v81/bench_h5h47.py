import sys,pickle,json,time
sys.path[:0]=['exp/v81','exp/v71','exp/v61','exp/v60','exp/v13']
from aqc1 import AQC1
from aqc import AQC
from qcc2 import QCC2
from qnc import QNC
cases=pickle.load(open('exp/v81/h5h47_branch.pkl','rb'))
rows=[]; t0=time.time()
for k,r in enumerate(cases):
    inst,h=r['inst'],r['h']
    q=QNC(inst,h); vq,sq=q.decide()
    c=QCC2(inst,h,cut_kind='uniform'); vc,sc=c.decide()
    a=AQC1(inst,h,cut_kind='uniform'); va,sa=a.decide()
    rows.append(dict(k=k,src=r['src'],idx=r['idx'],
      q=(sq['lp_solves'],sq['nodes']),c=(sc['lp_solves'],sc['nodes']),
      a=(sa['lp_solves'],sa['nodes']),probes=sa['probes'],pairs=sa['pairs'],
      why=sa['why'],audit=a.audit(),force=sa['force'],cover_root=sa['why']=='cover-root'))
json.dump(rows,open('exp/v81/h5h47_bench.json','w'),indent=1)
for key in ['q','c','a']:
    print(key,'LP',sum(r[key][0] for r in rows),'nodes',sum(r[key][1] for r in rows))
print('audit',sum(r['audit'] for r in rows),'probes',sum(r['probes'] for r in rows),'cover_root',sum(r['cover_root'] for r in rows))
print('improved',sum(r['a'][0]<r['q'][0] for r in rows),'worse',sum(r['a'][0]>r['q'][0] for r in rows))
print('median q/a',sorted(r['q'][0] for r in rows)[len(rows)//2],sorted(r['a'][0] for r in rows)[len(rows)//2])
for r in rows:
    if not r['cover_root'] or r['a'][0]>r['q'][0]:
        print(r)
print('wall',round(time.time()-t0,1))
