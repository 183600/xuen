import sys, pickle
sys.path.insert(0,'.')
import exp_da as E
pool=pickle.load(open('pool30.pkl','rb'))
for variant in ('AG','AGt'):
    tot=0; us=[]
    for k,(inst,opt,nd) in enumerate(pool):
        r=E.run(inst,variant=variant,budget=900)
        tot+=r['steps']; us.append(r['U']-opt)
    print(variant,'nodes',tot,'maxgap',max(us),'sumgap',sum(us))
