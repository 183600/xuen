import sys, json, pickle, time
sys.path.insert(0,'..'); sys.path.insert(0,'.'); sys.path.insert(0,'../v07')
import exp_da as E
from solve import solve
R=json.load(open('results.json')); pool=pickle.load(open('../pool30.pkl','rb'))
configs=[('base',False,False,False),('nodePACK',False,True,False),
         ('IPbound',True,False,False),('full',True,True,True)]
out={}
for fam in ('dense','part2','part3'):
    rows=[]
    for r in R[fam]:
        if fam=='dense': inst=pool[r['k']][0]
        else:
            p=r['p']; m=r['m']; n=len(p); pred=[[] for _ in range(n)]; succ=[[] for _ in range(n)]
            inst={'n':n,'m':m,'p':p,'pred':pred,'succ':succ,'ep':0.0,'pmax':max(p)}
            E.compute_desc(inst); inst['pmask']=[0]*n
        row={'k':r['k'],'OPT':r['OPT']}
        for name,ip,pk,cb in configs:
            row[name]=solve(inst,use_ip=ip,use_pack=pk,use_cbj=cb)
        rows.append(row)
        print(fam,r['k'],{name:(row[name]['nodes'],row[name]['U']) for name,_,_,_ in configs},flush=True)
    out[fam]=rows
json.dump(out,open('ablate.json','w'),indent=1)
print('== summary')
for fam in out:
    print(fam)
    for name,_,_,_ in configs:
        ns=[x[name]['nodes'] for x in out[fam]]
        tm=[x[name]['t'] for x in out[fam]]
        wrong=sum(1 for x in out[fam] if x[name]['U']!=x['OPT'])
        print(' ',name,'nodes',sum(ns),'time',round(sum(tm),3),'wrong',wrong,'max',max(ns))
