import sys, pickle, json, time
sys.path[:0]=['exp/v84','exp/v71','exp/v61','exp/v60','exp/v13']
from qnc import QNC
from qrc import QRC

FILES = {
 'holdout50': 'exp/v20/holdout_cases50.pkl', 'synth45': 'exp/v28/synth2_45.pkl',
 'large_a': 'exp/v14/large_a.pkl', 'large_b': 'exp/v14/large_b.pkl',
 'large_het': 'exp/v14/large_het.pkl', 'hard3': 'exp/v13/hard3.pkl',
 'deep8': 'exp/v18/deep.pkl'}

def load(f):
    d=pickle.load(open(f,'rb'))
    return [(x[0],x[1]) if isinstance(x,tuple) else (x['inst'],x['opt']) for x in d]

def run(inst,h):
    t0=time.time(); q=QNC(inst,h); vq,sq=q.decide(); tq=time.time()-t0
    t0=time.time(); r=QRC(inst,h); vr,sr=r.decide(); tr=time.time()-t0
    return (vq,sq,tq,q.audit()),(vr,sr,tr,r.audit())

def main():
    rows=[]
    tot={'qnc':[0,0,0],'qrc':[0,0,0]}
    for name,f in FILES.items():
        for idx,(inst,opt) in enumerate(load(f)):
            (vq,sq,tq,aq),(vr,sr,tr,ar)=run(inst,opt-1)
            rows.append(dict(name=name,idx=idx,opt=opt,
                q_v=vq,q_lp=sq['lp_solves'],q_nodes=sq['nodes'],q_t=tq,q_audit=aq,
                r_v=vr,r_lp=sr['lp_solves'],r_nodes=sr['nodes'],r_t=tr,r_audit=ar,
                r_steps=sr.get('res_steps'),r_units=sr.get('res_units'),
                r_clauses=sr.get('clause_db'),r_empty=sr.get('res_empty')))
            for k,s in [('qnc',sq),('qrc',sr)]:
                tot[k][0]+= (vq is False) if k=='qnc' else (vr is False)
                tot[k][1]+=s['lp_solves']; tot[k][2]+=s['nodes']
            if sq['nodes']>1 or sr['nodes']>1:
                print('BR',name,idx,'QNC',vq,sq['lp_solves'],sq['nodes'],'QRC',vr,sr['lp_solves'],sr['nodes'],'steps',sr.get('res_steps'),'units',sr.get('res_units'),'db',sr.get('clause_db'),flush=True)
    print('TOTAL',tot)
    pert=pickle.load(open('exp/v71/perturb60.pkl','rb'))
    prows=[]; ptot={'qnc':[0,0,0],'qrc':[0,0,0]}
    for (name,k,inst,opt,an,al) in pert:
        (vq,sq,tq,aq),(vr,sr,tr,ar)=run(inst,opt-1)
        prows.append(dict(name=name,k=k,opt=opt,
            q_v=vq,q_lp=sq['lp_solves'],q_nodes=sq['nodes'],q_audit=aq,
            r_v=vr,r_lp=sr['lp_solves'],r_nodes=sr['nodes'],r_audit=ar,
            r_steps=sr.get('res_steps'),r_units=sr.get('res_units'),
            r_clauses=sr.get('clause_db'),r_empty=sr.get('res_empty')))
        for kk,s in [('qnc',sq),('qrc',sr)]:
            ptot[kk][0]+= (vq is False) if kk=='qnc' else (vr is False)
            ptot[kk][1]+=s['lp_solves']; ptot[kk][2]+=s['nodes']
        if sq['nodes']>1 or sr['nodes']>1:
            print('PERT',name,k,'QNC',vq,sq['lp_solves'],sq['nodes'],'QRC',vr,sr['lp_solves'],sr['nodes'],'steps',sr.get('res_steps'),'units',sr.get('res_units'),'db',sr.get('clause_db'),flush=True)
    print('PERT TOTAL',ptot)
    json.dump(dict(rows=rows,pert=prows,tot=tot,ptot=ptot),open('exp/v84/qrc_bench.json','w'),indent=1)

if __name__=='__main__': main()
