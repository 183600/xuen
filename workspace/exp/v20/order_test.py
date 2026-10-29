import sys,pickle,time
sys.path.insert(0,'exp/v13');sys.path.insert(0,'exp/v14');sys.path.insert(0,'exp/v15')
sys.path.insert(0,'exp/v16');sys.path.insert(0,'exp/v17');sys.path.insert(0,'exp/v18');sys.path.insert(0,'exp/v19');sys.path.insert(0,'exp/v20')
import po,pace_v19,pace_v20
CFG=dict(mode='pot',nodecap=2_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
def fe(inst): return all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n']))
def load(path):
    d=pickle.load(open(path,'rb'))
    return [x if isinstance(x,dict) else {'inst':x[0],'opt':x[1]} for x in d]
D=pickle.load(open('exp/v18/deep.pkl','rb'))
insts=[]
for tag,path in [('hard3','exp/v13/hard3.pkl'),('large_het','exp/v14/large_het.pkl')]:
    for k,rec in enumerate(load(path)): insts.append((tag+str(k),rec['inst'],rec['opt']-1))
for idx,(inst,opt,*_) in enumerate(D): insts.append(('deep%d'%idx,inst,opt-1))
for tag,inst,h in insts:
    row=[]
    for order in ('slack','late','loss','astar'):
        (b,_),st=pace_v19.decide(inst,h,odom=False,dcd=True,rhd=True,hpack_on=True,omd=fe(inst),order=order,**CFG)
        assert b is False
        row.append((order,st['nodes']))
    if len(set(x[1] for x in row))>1:
        print(tag,inst['n'],row)
