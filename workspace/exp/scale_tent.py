import sys, random, time, json
sys.path.insert(0,'.')
import exp_da as E
from proto_tent_root import tent_thresh

def main():
    rng=random.Random(777)
    rows=[]
    for n in (12,15,18,22,26,30):
        for rep in range(2):
            inst=E.gen_instance(n,rng.choice([0.12,0.18,0.25]),8,rng,2)
            S0,A0,c0=0,(0,0),(-1,)*n
            L0=E.lower_L0(inst,S0,A0,c0); U=E.guide(inst,S0,A0,c0)
            t=time.time(); new,nt,nw=tent_thresh(inst,S0,A0,c0,U,L0); dt=time.time()-t
            t=time.time(); old,nf=E.thresh(inst,S0,A0,c0,U,L0,'full'); do=time.time()-t
            row=dict(n=n,rep=rep,U=U,L0=L0,old=old,new=new,nw=nw,nt=nt,nf=nf,
                     t_new=round(dt,3),t_old=round(do,3))
            rows.append(row); print(row,flush=True)
    json.dump(rows,open('scale_tent.json','w'),indent=1)
if __name__=='__main__': main()
