import sys,json,time
sys.path[:0]=['/tmp/opencode','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from chip import base_corpus, pert_corpus, stress_corpus
from rdf import check_schedule
import core_search as cs

def load():
    out=[]
    for tag,rs in [('base',base_corpus()),('pert',pert_corpus()),('stress',stress_corpus())]:
        for row in rs:
            if len(row)==4: name,idx,inst,known=row
            else: idx,known,inst=row; name=tag
            out.append((tag,name,idx,known,inst))
    return out

def main(out,nmax=None):
    insts=load(); rows=json.load(open('exp/v8o/pact_depth.json')); res=[]; t0=time.time()
    for k,r in enumerate(rows):
        if r['label']!='YES': continue
        tag,name,idx,known,inst=insts[k//2]
        h=r['h']
        for mode,kw in [('base',dict(use_clauses=False,use_res=False,use_guide=False,use_force=False)),
                        ('clauses',dict(use_clauses=True,use_res=False,use_guide=False,use_force=False)),
                        ('force',dict(use_clauses=True,use_res=False,use_guide=False,use_force=True)),
                        ('res',dict(use_clauses=True,use_res=True,use_guide=False,use_force=True)),
                        ('guide',dict(use_clauses=True,use_res=True,use_guide=True,use_force=True))]:
            z=cs.core_decide(inst,h,max_nodes=nmax,**kw)
            ok=False
            if z['verdict'] is True:
                s,m=z['schedule'],z['machine']
                cmax=max(s[i]+inst['p'][i] for i in range(inst['n']))
                ok=check_schedule(inst,cmax,s,m)
            res.append(dict(tag=tag,name=name,idx=idx,known=known,h=h,mode=mode,
                            v=z['verdict'],ok=ok,nodes=z['nodes'],lp=z['lp'],cert=z['cert'],
                            support_ok=z['support_ok'],clauses=z['clauses'],res_steps=z['res_steps'],
                            back=z['backjumps'],guides=z['guides'],forces=z.get('forces',0),t=z['t']))
        print('.',end='',flush=True)
    json.dump(res,open(out,'w'),indent=1)
    print('\nwall',round(time.time()-t0,2),'rows',len(res))
    for mode in ['base','clauses','force','res','guide']:
        rs=[r for r in res if r['mode']==mode]
        print(mode,'yes',sum(r['v'] is True for r in rs),'no',sum(r['v'] is False for r in rs),'none',sum(r['v'] is None for r in rs),
              'ok',sum(r['ok'] for r in rs),'nodes',sum(r['nodes'] for r in rs),'lp',sum(r['lp'] for r in rs),
              'maxnodes',max(r['nodes'] for r in rs),'t',round(sum(r['t'] for r in rs),2),
              'prune',sum(r['clauses'] for r in rs),'res',sum(r['res_steps'] for r in rs),'back',sum(r['back'] for r in rs),'forces',sum(r['forces'] for r in rs))
if __name__=='__main__':
    main(sys.argv[1] if len(sys.argv)>1 else '/tmp/core_yes.json')
