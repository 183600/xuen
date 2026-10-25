import sys,json,time
sys.path[:0]=['/tmp/opencode','exp/v8o','exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from chip import base_corpus, pert_corpus, stress_corpus
import core_search as cs

def load():
    out=[]
    for tag,rs in [('base',base_corpus()),('pert',pert_corpus()),('stress',stress_corpus())]:
        for row in rs:
            if len(row)==4: name,idx,inst,known=row
            else: idx,known,inst=row; name=tag
            out.append((tag,name,idx,known,inst))
    return out

def main(label,out):
    insts=load(); rows=json.load(open('exp/v8o/pact_depth.json'))
    res=[]; t0=time.time()
    for k,r in enumerate(rows):
        if r['label']!=label: continue
        tag,name,idx,known,inst=insts[k//2]
        h=r['h']
        for mode,kw in [('base',dict(use_clauses=False,use_res=False,use_guide=False,use_force=False)),
                        ('clauses',dict(use_clauses=True,use_res=False,use_guide=False,use_force=False)),
                        ('force',dict(use_clauses=True,use_res=False,use_guide=False,use_force=True)),
                        ('res',dict(use_clauses=True,use_res=True,use_guide=False,use_force=True)),
                        ('guide',dict(use_clauses=True,use_res=True,use_guide=True,use_force=True))]:
            z=cs.core_decide(inst,h,max_nodes=None,**kw)
            res.append(dict(tag=r['tag'],name=r['name'],idx=r['idx'],known=r['known'],h=h,mode=mode,
                            v=z['verdict'],nodes=z['nodes'],lp=z['lp'],cert=z['cert'],
                            support_ok=z['support_ok'],support_fail=z['support_fail'],
                            empty=z.get('empty',0),clauses=z['clauses'],res_steps=z['res_steps'],
                            back=z['backjumps'],guides=z['guides'],forces=z.get('forces',0),t=z['t'],
                            audit=(z['proof'].audit_rdf() if z['proof'] is not None else None),
                            proof_core=(len(z['proof'].core) if z['proof'] is not None else None)))
        print('.',end='',flush=True)
    json.dump(res,open(out,'w'),indent=1)
    print('\nwall',round(time.time()-t0,2),'rows',len(res))
    for mode in ['base','clauses','force','res','guide']:
        rs=[r for r in res if r['mode']==mode]
        hard=[r for r in rs if r['nodes']>1]
        print(mode,'n',len(rs),'vNO',sum(r['v'] is False for r in rs),'vNone',sum(r['v'] is None for r in rs),
              'vYES',sum(r['v'] is True for r in rs),'audit',sum(r['audit'] is True for r in rs),
              'nodes',sum(r['nodes'] for r in rs),'lp',sum(r['lp'] for r in rs),'t',round(sum(r['t'] for r in rs),2),
              'forces',sum(r['forces'] for r in rs),
              '| hard',len(hard),'nodes',sum(r['nodes'] for r in hard),'max',max((r['nodes'] for r in hard),default=0),
              't',round(sum(r['t'] for r in hard),2))
if __name__=='__main__':
    main(sys.argv[1],sys.argv[2])
