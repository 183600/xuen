"""Final experiment for X-DUB/TQ* on the 30-instance pool."""
import sys, time, json, pickle
sys.path.insert(0,'.')
import exp_da as E
from proto_full import run_full
from proto_periodic import run_periodic

def main():
    pool=pickle.load(open('pool30.pkl','rb'))
    rows=[]
    for k,(inst,opt,nd) in enumerate(pool):
        out={}
        for tag,fn,kw in (
            ('baseQ', run_full, dict(root_bound='L0',delta=0)),
            ('cdom', None, None),
            ('rootT', run_full, dict(root_bound='TENT',delta=0)),
            ('rootT_d1', run_full, dict(root_bound='TENT',delta=1)),
            ('perT', run_periodic, dict(delta=0)),
            ('perT_d1', run_periodic, dict(delta=1)),
        ):
            if fn is None: continue
            r=fn(inst,budget=900,**kw)
            assert r['U']==opt,(k,tag,r['U'],opt)
            out[tag]=r
        # c-dominance baseline: patch run_full? use proto_dom.run_q
        import proto_dom
        rc=proto_dom.run_q(inst,budget=900,dom_mode='c')
        assert rc['U']==opt
        out['cdom']={'steps':rc['steps'],'U':rc['U'],'time':rc['time'],'anytime':rc['anytime']}
        row={'k':k,'n':inst['n'],'opt':opt,'L0':out['baseQ']['Lg'],
             'cdom':out['cdom']['steps'],'q':out['baseQ']['steps'],
             'rt':out['rootT']['steps'],'rt1':out['rootT_d1']['steps'],
             'pt':out['perT']['steps'],'pt1':out['perT_d1']['steps'],
             't_rt':round(out['rootT']['time'],4),'t_pt':round(out['perT']['time'],4),
             't_pt1':round(out['perT_d1']['time'],4),
             'any_pt':out['perT'].get('anytime',{})}
        rows.append(row)
        print(k,'opt',opt,'cdom',row['cdom'],'q',row['q'],'rt',row['rt'],'rt1',row['rt1'],'pt',row['pt'],'pt1',row['pt1'],flush=True)
    print('TOTALS cdom',sum(r['cdom'] for r in rows),'q',sum(r['q'] for r in rows),
          'rt',sum(r['rt'] for r in rows),'rt1',sum(r['rt1'] for r in rows),
          'pt',sum(r['pt'] for r in rows),'pt1',sum(r['pt1'] for r in rows))
    print('wall rt',round(sum(r['t_rt'] for r in rows),3),'pt',round(sum(r['t_pt'] for r in rows),3),
          'pt1',round(sum(r['t_pt1'] for r in rows),3))
    json.dump(rows,open('run_tq.json','w'),indent=1)

if __name__=='__main__': main()
