import sys,pickle,time
sys.path.insert(0,'exp/v13');sys.path.insert(0,'exp/v14');sys.path.insert(0,'exp/v15')
sys.path.insert(0,'exp/v16');sys.path.insert(0,'exp/v17');sys.path.insert(0,'exp/v18');sys.path.insert(0,'exp/v19');sys.path.insert(0,'exp/v20')
import po,pace_v19,pace_v20
CFG=dict(mode='pot',nodecap=3_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)
def fe(inst): return all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n']))
def load(path):
    d=pickle.load(open(path,'rb'))
    return [x if isinstance(x,dict) else {'inst':x[0],'opt':x[1]} for x in d]
def run(mod,inst,h,**kw):
    return mod.decide(inst,h,odom=False,dcd=True,hpack_on=True,omd=fe(inst),**CFG,**kw)
for tag,path in [('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
                 ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]:
    for k,rec in enumerate(load(path)):
        inst,h=rec['inst'],rec['opt']-1
        (b1,_),s1=run(pace_v19,inst,h,rhd=True)
        (b2,_),s2=run(pace_v20,inst,h,dhd=True)
        assert b1 is False and b2 is False
        if s1['nodes']!=s2['nodes']:
            print(tag,k,inst['n'],'rhd',s1['nodes'],'dhd',s2['nodes'])
D=pickle.load(open('exp/v18/deep.pkl','rb'))
print('--- deep ---')
for idx,(inst,opt,*_) in enumerate(D):
    h=opt-1
    (b1,_),s1=run(pace_v19,inst,h,rhd=True)
    (b2,_),s2=run(pace_v20,inst,h,dhd=True)
    assert b1 is False and b2 is False
    print(idx,inst['n'],'rhd',s1['nodes'],'dhd',s2['nodes'])
