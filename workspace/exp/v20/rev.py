import sys, pickle, time, json, statistics
sys.path.insert(0,'exp/v13');sys.path.insert(0,'exp/v14');sys.path.insert(0,'exp/v15')
sys.path.insert(0,'exp/v16');sys.path.insert(0,'exp/v17');sys.path.insert(0,'exp/v18');sys.path.insert(0,'exp/v19')
import po, pace_v19

CFG=dict(mode='pot',nodecap=2_000_000,mint_on=True,mint_depth=0,
         packset_on=True,packset_depth=0,sop_on=True,sop_nodecap=200000)

def rev_inst(inst):
    n=inst['n']
    p=[0]*n; pred=[[] for _ in range(n)]; elig=[None]*n
    for i in range(n):
        ni=n-1-i
        p[ni]=inst['p'][i]; elig[ni]=list(inst['elig'][i])
        for j in inst['succ'][i]:
            pred[n-1-j].append(ni)
    return po.make_inst(p, inst['m'], pred=pred, elig=elig)

def load(path):
    d=pickle.load(open(path,'rb'))
    return [x if isinstance(x,dict) else {'inst':x[0],'opt':x[1]} for x in d]
def fe(inst): return all(len(set(inst['elig'][i]))==inst['m'] for i in range(inst['n']))

def run(inst,h,rhd=True):
    return pace_v19.decide(inst,h,odom=False,dcd=True,rhd=rhd,hpack_on=True,
                           omd=fe(inst),**CFG)

if __name__=='__main__':
    sets=[('hard3','exp/v13/hard3.pkl'),('large_b','exp/v14/large_b.pkl'),
          ('large_a','exp/v14/large_a.pkl'),('large_het','exp/v14/large_het.pkl')]
    tot_f=tot_b=0; rows=[]
    for tag,path in sets:
        for k,rec in enumerate(load(path)):
            inst,h=rec['inst'],rec['opt']-1
            (bf,_),sf=run(inst,h); (bb,_),sb=run(rev_inst(inst),h)
            assert bf is False and bb is False,(tag,k,bf,bb)
            tot_f+=sf['nodes']; tot_b+=sb['nodes']
            if sf['nodes']!=sb['nodes']:
                rows.append((tag,k,inst['n'],sf['nodes'],sb['nodes']))
    print('38 forward',tot_f,'backward',tot_b)
    for r in rows: print(r)
    D=pickle.load(open('exp/v18/deep.pkl','rb')); tf=tb=0
    print('--- deep ---')
    for idx,(inst,opt,*_) in enumerate(D):
        h=opt-1
        (bf,_),sf=run(inst,h); (bb,_),sb=run(rev_inst(inst),h)
        assert bf is False and bb is False,(idx,bf,bb)
        tf+=sf['nodes']; tb+=sb['nodes']
        print(idx,inst['n'],sf['nodes'],sb['nodes'])
    print('deep forward',tf,'backward',tb)
