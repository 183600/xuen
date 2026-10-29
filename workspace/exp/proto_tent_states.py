import sys, random, json, pickle
sys.path.insert(0,'.')
import exp_da as E
from proto_tent_root import tent_thresh

def main():
    rng=random.Random(5150)
    pool=pickle.load(open('pool30.pkl','rb'))
    rows=[]
    for k,(inst,opt,nd) in enumerate(pool):
        for trial in range(3):
            S,A,c=E.random_prefix(inst,rng,rng.choice([0.25,0.4,0.55]))
            L0=E.lower_L0(inst,S,A,c); U=E.guide(inst,S,A,c)
            if L0>=U: continue
            old,nf=E.thresh(inst,S,A,c,U,L0,'full')
            new,nt,nw=tent_thresh(inst,S,A,c,U,L0)
            row=dict(k=k,trial=trial,L0=L0,U=U,old=old,new=new,opt=opt,nf=nf,nt=nt,nw=nw)
            rows.append(row)
    print('states',len(rows))
    print('new>old',sum(r['new']>r['old'] for r in rows),
          'new<old',sum(r['new']<r['old'] for r in rows),
          'equal',sum(r['new']==r['old'] for r in rows))
    print('new<=opt',sum(r['new']<=r['opt'] for r in rows),'/',len(rows),
          'new==opt',sum(r['new']==r['opt'] for r in rows))
    print('old==opt',sum(r['old']==r['opt'] for r in rows))
    print('sum L0',sum(r['L0'] for r in rows),'old',sum(r['old'] for r in rows),'new',sum(r['new'] for r in rows))
    print('BP old',sum(r['nf'] for r in rows),'tent',sum(r['nt'] for r in rows))
    for r in rows:
        if r['new']>r['old']:
            print('gain',r)
    json.dump(rows,open('proto_tent_states.json','w'),indent=1)

if __name__=='__main__': main()
