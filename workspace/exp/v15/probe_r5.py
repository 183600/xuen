import sys,pickle,time
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v14'); sys.path.insert(0,'exp/v15')
import po, pace_i, mint
SETS=[('hard3','exp/v13/hard3.pkl',[2,5]),('large_het','exp/v14/large_het.pkl',[1])]
for tag,path,idxs in SETS:
    d=pickle.load(open(path,'rb'))
    for k in idxs:
        rec=d[k]
        if isinstance(rec,tuple): inst,opt=rec[0],rec[1]
        else: inst,opt=rec['inst'],rec['opt']
        print('='*70); print(tag,k,'n',inst['n'],'m',inst['m'],'opt',opt)
        print('p',inst['p']); print('pred',inst['pred']); print('elig',inst['elig'])
        est0,q0=po.heads_tails(inst,0,[0]*inst["n"])
        print('est0',est0); print('q0',q0)
        # feasible schedule at h=opt
        (ok,out),st=pace_i.decide(inst,opt,mode='pot',nodecap=2_000_000,
             mint_on=True,mint_depth=0,packset_on=True,packset_depth=0)
        print('h=opt ->',ok,'nodes',st['nodes'])
        if ok:
            for (i,kk,t) in out:
                print('   task %2d m%d [%d,%d) r=%d d=%d'%(i,kk,t,t+inst['p'][i],est0[i],opt-q0[i]))
        # root at h=opt-1: tight slack
        h=opt-1
        p=inst['p']; m=inst['m']; n=inst['n']
        cap=[h-0]*m
        r=est0; dd=[h-q0[i] for i in range(n)]; ps=p
        starts=sorted(set(list(r)+[dd[i]-ps[i] for i in range(n)]))
        ends=sorted(set(list(dd)+[r[i]+ps[i] for i in range(n)]))
        rows=[]
        for a in starts:
            for b in ends:
                if b<=a: continue
                c=sum(max(0,b-max(a,0)) for _ in range(m))
                tot=0; mand=[]
                for i in range(n):
                    v=ps[i]
                    v=min(v,r[i]+ps[i]-a); v=min(v,b-(dd[i]-ps[i])); v=min(v,b-a); v=max(0,v)
                    mand.append(v); tot+=v
                rows.append((c-tot,a,b,tot,c,mand))
        rows.sort()
        print('h=opt-1 min interval slack',rows[0][0])
        for row in rows[:5]:
            print('   slack %d [%d,%d] W=%d cap=%d mand=%s'%(row[0],row[1],row[2],row[3],row[4],[x for x in row[5]]))
