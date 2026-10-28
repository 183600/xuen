import sys,json,time
sys.path[:0]=['exp/v9x','exp/v91','exp/v8u','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from icf import corpora
from po import heads_tails
from rdf import check_schedule
from sparc import Swarm, _strong_init
from proto_beam3 import beam

def main():
    rows=list(corpora()); idx={(c,n,i):(c,n,i,inst,k) for c,n,i,inst,k in rows}
    sp=json.load(open('exp/v91/bench_sparc.json'))['rows']['strong_pso1_lower']
    hard=[r for r in sp if r['known']==r['lb0'] and r['ub_pso']>r['lb0']]
    yes46=[r for r in sp if r['known']==r['lb0'] and r['ub0']>r['lb0']]
    for tag,cases in [('hard12',hard),('yes46',yes46)]:
      print('==',tag,len(cases))
      for np_,it in [(8,12),(16,20),(8,30)]:
       for width in (20,30,50):
        ok=0; tt=0; nn=0; rr=0
        for r in cases:
            c,n,i,inst,known=idx[(r['corpus'],r['name'],r['idx'])]
            L,U,s,m,proof,pin=_strong_init(inst)
            sw=Swarm(inst,U,s,m,n_particles=np_,iters=it,seed=11,stall=4)
            best,st=sw.run(); cc,s2,m2=best
            rank1={i:s2[i]+1e-6*i for i in range(inst['n'])}
            sol,stt=beam(inst,r['lb0'],width=width,ranks=[rank1])
            tt+=stt['t']+st['t']; nn+=stt['nodes']; rr+=stt['rollouts']
            if sol is not None:
                ok+=1; ss,mm,ccc=sol
                assert check_schedule(inst,ccc,ss,mm)
        print(' pso',np_,it,'width',width,'ok',ok,'/',len(cases),'nodes',nn,'roll',rr,'t',round(tt,2))

if __name__=='__main__': main()
