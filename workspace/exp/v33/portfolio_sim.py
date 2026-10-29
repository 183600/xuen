import sys,pickle,time,statistics,json
sys.path[:0]=['exp/v33','exp/v31','exp/v30','exp/v29','exp/v13','exp/v15','exp/v16','exp/v20','exp/v25']
import turn, po, root_v31

def load(f):
    d=pickle.load(open(f,'rb')); out=[]
    for x in d:
        if isinstance(x,tuple): out.append((x[0],x[1]))
        else: out.append((x['inst'],x['opt']))
    return out

CASES=[('holdout50','exp/v20/holdout_cases50.pkl'),('hard3','exp/v13/hard3.pkl'),
       ('deep8','exp/v18/deep.pkl'),('large_a','exp/v14/large_a.pkl'),
       ('large_b','exp/v14/large_b.pkl'),('large_het','exp/v14/large_het.pkl'),
       ('synth45','exp/v28/synth2_45.pkl')]

def measure():
    rows=[]
    for name,f in CASES:
        for inst,opt in load(f):
            h=opt-1; n=inst['n']; m=inst['m']
            full=all(len(set(inst['elig'][i]))==m for i in range(n))
            st={}; ok,s=root_v31.bb_solve(inst,h,stats=st)
            rec=dict(name=name,n=n,m=m,full=full,t=s.get('t',0),kind='cascade',p=None,tf=None,tb=None)
            if s.get('verdict','').startswith('OS') and full and n<=16:
                est,q=po.heads_tails(inst,0,[0]*n)
                cp=max(est[i]+inst['p'][i]+q[i] for i in range(n)); S=h-cp
                if 0<=S<=4:
                    p=turn.select(inst,h,est,q)
                    tf=[]; tb=[]
                    for rep in range(3):
                        t0=time.time(); turn.solve_dir(inst,h,est,q,False,10000); tf.append(time.time()-t0)
                        t0=time.time(); turn.solve_dir(inst,h,est,q,True,10000); tb.append(time.time()-t0)
                    rec.update(kind='dual',p=p,tf=statistics.median(tf),tb=statistics.median(tb))
            rows.append(rec)
    return rows

def lpt_span(durs,P=4):
    # LPT list scheduling
    loads=[0.0]*P
    for d in sorted(durs,reverse=True):
        k=min(range(P),key=lambda i:loads[i]); loads[k]+=d
    return max(loads)

if __name__=='__main__':
    rows=measure(); pickle.dump(rows,open('exp/v33/portfolio_rows.pkl','wb'))
    print('cases',len(rows))
    for tag in ['allF','allB','race','oracleF']:
        durs=[]; work=0
        for r in rows:
            if r['kind']!='dual':
                durs.append(r['t']); work+=r['t']
            else:
                if tag=='allF': d=r['tf']
                elif tag=='allB': d=r['tb']
                elif tag=='race': d=min(r['tf'],r['tb'])
                else: d=min(r['tf'],r['tb'])
                durs.append(d)
                work += (r['tf']+r['tb']) if tag=='race' else d
        print('%-7s work %.4f  span4 %.4f  maxjob %.4f'%(tag,work,lpt_span(durs),max(durs)))
    for delta in [0.0,0.1,0.2,0.3,0.4]:
        durs=[]; work=0; spec=0
        for r in rows:
            if r['kind']!='dual': durs.append(r['t']); work+=r['t']; continue
            conf=abs(r['p']-0.5)
            if conf>=delta:
                d=r['tb'] if r['p']>0.5 else r['tf']; durs.append(d); work+=d
            else:
                d=min(r['tf'],r['tb']); durs.append(d); work+=r['tf']+r['tb']; spec+=1
        print('delta %.2f spec %d work %.4f span4 %.4f'%(delta,spec,work,lpt_span(durs)))
