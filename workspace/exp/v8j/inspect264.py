import sys, json, time
sys.path[:0]=['exp/v8i','exp/v8h','exp/v8f','exp/v8e','exp/v8g','exp/v8c','exp/v9d','exp/v9c','exp/v9b','exp/v8a','exp/v76','exp/v72','exp/v71','exp/v61','exp/v60','exp/v13']
from search_hard import make_inst, opt_milp
from sage import lp_branch_decide
inst=make_inst(18,3,264,edgep=0.15,hetero=0.5)
print('inst',inst)
opt,ub=opt_milp(inst,tl=20); print('opt',opt,'ub',ub)
for cap,depth in [(2000,60),(10000,100),(50000,200)]:
    t0=time.time(); r=lp_branch_decide(inst,opt-1,nodecap=cap,depthcap=depth)
    print('cap',cap,'depth',depth,'verdict',r['verdict'],'nodes',r['nodes'],'leaves',r['leaves'],'depth',r['depth'],'lp',r['lp_solves'],'cert',r['cert_lp'],'unknown',r['unknown'],'t',r['t'],'wall',round(time.time()-t0,2))
    print('  branch_jobs',r['branch_jobs'][:30])
