import sys, pickle
sys.path.insert(0,'exp/v14')
import lls
d=pickle.load(open('exp/v13/hard3.pkl','rb'))
for idx,(inst,opt,n0) in enumerate(d):
    base=None; sigs=[]
    for sh in [0,1,2,3]:
        (ok,_),st=lls.decide_lls(inst,opt-1,shuffle=sh)
        sig=(st['labels'],tuple(st['front_total']),tuple(t[1] for t in st['levels']))
        sigs.append(sig)
    same=all(s==sigs[0] for s in sigs)
    print(idx,'invariant',same,'labels',sigs[0][0],'fronts',sigs[0][1][:6],flush=True)
