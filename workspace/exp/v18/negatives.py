"""Reproduce the two unsound reductions (and the sound-but-vacuous one)."""
import sys,pickle,json
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v15'); sys.path.insert(0,'exp/v16')
sys.path.insert(0,'exp/v17'); sys.path.insert(0,'exp/v18')
import po, pace_neg
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000,omd=True)
res={}
# --- naive start-commutation POR: n=5 counterexample
inst=po.make_inst([2,7,2,9,6],2,[[],[0],[0],[0],[2]])
(b,bo),sb=pace_neg.decide(inst,15,por=False,**CFG)
(q,qo),sq=pace_neg.decide(inst,15,por=True,**CFG)
res['por_n5']=dict(base=b,base_nodes=sb['nodes'],base_out=bo,
                   por=q,por_nodes=sq['nodes'],
                   p=inst['p'],pred=inst['pred'],h=15)
# --- naive POR on hard3#5: the 1.44x illusion
d=pickle.load(open('exp/v13/hard3.pkl','rb')); h35=d[5][0]
(b,bo),sb=pace_neg.decide(h35,38,por=False,**CFG)
(q,qo),sq=pace_neg.decide(h35,38,por=True,**CFG)
res['por_hard3']=dict(base=b,base_nodes=sb['nodes'],por=q,por_nodes=sq['nodes'])
# --- sibling state dominance: 5.4x illusion, false NO at OPT
(b,bo),sb=pace_neg.decide(h35,38,sdom=False,**CFG)
(q,qo),sq=pace_neg.decide(h35,38,sdom=True,**CFG)
(b39,bo39),sb39=pace_neg.decide(h35,39,sdom=False,**CFG)
(q39,qo39),sq39=pace_neg.decide(h35,39,sdom=True,**CFG)
res['sdom_hard3']=dict(h38=dict(base=b,base_nodes=sb['nodes'],sdom=q,sdom_nodes=sq['nodes']),
                       h39=dict(base=b39,base_nodes=sb39['nodes'],sdom=q39,sdom_nodes=sq39['nodes']))
# --- task symmetry alone: sound but vacuous here
(b,bo),sb=pace_neg.decide(h35,38,tsym=False,**CFG)
(q,qo),sq=pace_neg.decide(h35,38,tsym=True,**CFG)
res['tsym_hard3']=dict(base_nodes=sb['nodes'],tsym_nodes=sq['nodes'])
json.dump(res,open('exp/v18/res_negatives.json','w'),indent=1)
print(json.dumps(res,indent=1))
