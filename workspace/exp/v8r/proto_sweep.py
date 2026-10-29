import sys, time, json, itertools
sys.path[:0] = ['exp/v8r']
from proto_probe import corpora, probe_decide
from pact import pact_decide

rows = list(corpora())
configs = []
for which in ('stress','base','pert'):
    for budget in (2,4,8,16):
        for policy in ('frac_mass','frac_peak','wide'):
            for sp in ('zero','support','all'):
                configs.append((which,budget,policy,4,sp))
# only stress first
configs=[c for c in configs if c[0] in ('stress',)]

def run(cfg):
    which,budget,policy,n_jobs,sp=cfg
    sel=[r for r in rows if r[0]==which]
    agg=dict(base_lp=0,base_nodes=0,base_t=0,lp=0,nodes=0,cert=0,t=0,
             probes=0,forbid=0,ok=0,n=0,pre=0,search=0)
    for tag,name,idx,inst,known in sel:
        for h,label in ((known-1,'NO'),(known,'YES')):
            b=pact_decide(inst,h,depthcap=None,nodecap=None)
            p=probe_decide(inst,h,budget,policy,n_jobs,sp)
            agg['base_lp']+=b['lp_solves']+1
            agg['base_nodes']+=b['nodes']
            agg['lp']+=p['lp_solves']
            agg['nodes']+=p['nodes']
            agg['cert']+=p['cert_lp']
            agg['probes']+=p['probes']
            agg['forbid']+=p['forbid']
            agg['pre']+=p['pre_t']
            agg['search']+=p.get('search_t',0)+p.get('pre_t',0)*0
            agg['t']+=p['t']
            agg['ok']+=(p['verdict']==b['verdict'])
            agg['n']+=1
    return agg

for cfg in configs:
    t0=time.time(); a=run(cfg)
    print(cfg,'ok',a['ok'],'/',a['n'],'base_lp',a['base_lp'],'new_lp',a['lp'],'probes',a['probes'],
          'search_nodes',a['nodes'],'base_nodes',a['base_nodes'],'pre',round(a['pre'],2),'t',round(a['t'],2),'wall',round(time.time()-t0,1))
