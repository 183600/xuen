import sys,pickle,json,time
sys.path[:0]=['exp/v84','exp/v71','exp/v61','exp/v60','exp/v13']
from qnc import QNC
from qrc import QRC

D=pickle.load(open('exp/v81/h5h47_branch.pkl','rb'))
rows=[]; tot={'qnc':[0,0,0,0],'qrc':[0,0,0,0]}
for n,r in enumerate(D):
    inst,h=r['inst'],r['h']
    t0=time.time(); q=QNC(inst,h); vq,sq=q.decide(); tq=time.time()-t0; aq=q.audit()
    t0=time.time(); z=QRC(inst,h); vr,sr=z.decide(); tr=time.time()-t0; ar=z.audit()
    rows.append(dict(n=n,src=r['src'],idx=r['idx'],base=r['q_lp'],
        q_v=vq,q_lp=sq['lp_solves'],q_nodes=sq['nodes'],q_t=tq,q_audit=aq,
        r_v=vr,r_lp=sr['lp_solves'],r_nodes=sr['nodes'],r_t=tr,r_audit=ar,
        r_steps=sr.get('res_steps'),r_units=sr.get('res_units'),
        r_db=sr.get('clause_db'),r_empty=sr.get('res_empty'),
        q_force=len(sq.get('force',{})),r_force=len(sr.get('force',{}))))
    for k,v,s,a in [('qnc',vq,sq,aq),('qrc',vr,sr,ar)]:
        tot[k][0]+=int(v is False); tot[k][1]+=s['lp_solves']; tot[k][2]+=s['nodes']; tot[k][3]+=int(bool(a))
    if sq['lp_solves']!=sr['lp_solves'] or sq['nodes']!=sr['nodes']:
        print('DIFF',n,r['src'],r['idx'],'QNC',vq,sq['lp_solves'],sq['nodes'],'QRC',vr,sr['lp_solves'],sr['nodes'],'steps',sr.get('res_steps'),'units',sr.get('res_units'),'db',sr.get('clause_db'),'empty',sr.get('res_empty'),flush=True)
print('TOTAL',tot)
json.dump(dict(rows=rows,tot=tot),open('exp/v84/branch51.json','w'),indent=1)
