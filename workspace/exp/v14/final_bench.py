import sys, pickle, time, json
sys.path.insert(0,'exp/v14')
import sp, lls, hybrid
d=pickle.load(open('exp/v13/hard3.pkl','rb'))
rows=[]
for idx,(inst,opt,n0) in enumerate(d):
    t=time.time(); (ok,s),st=sp.decide(inst,opt-1,mode='sub'); td=time.time()-t
    t=time.time(); (ok2,_),st2=lls.decide_lls(inst,opt-1); tl=time.time()-t
    hy=hybrid.solve(inst,opt-1,dfs_budget=256)
    row=dict(idx=idx,n=inst['n'],opt=opt,
             dfs_nodes=st['nodes'],dfs_memo=st['memo_hits'],dfs_exp=st['nodes']-st['memo_hits'],
             dfs_tables=st['tables'],dfs_t=td,
             lls_labels=st2['labels'],lls_exp=st2['expanded'],lls_dead=st2['dead'],
             lls_packs=st2['packs'],lls_exact=st2['exact'],lls_fmax=st2['front_max'],lls_t=tl,
             hyb_t=hy['t'],hyb_engine=hy['engine'],hyb_dfs=hy['dfs_nodes'])
    rows.append(row)
    print(idx,row,flush=True)
json.dump(rows,open('exp/v14/final.json','w'),indent=1)
print('TOT dfs_nodes',sum(r['dfs_nodes'] for r in rows),'dfs_exp',sum(r['dfs_exp'] for r in rows),
      'dfs_t',round(sum(r['dfs_t'] for r in rows),3),
      'lls_labels',sum(r['lls_labels'] for r in rows),'lls_exp',sum(r['lls_exp'] for r in rows),
      'lls_t',round(sum(r['lls_t'] for r in rows),3),
      'hyb_t',round(sum(r['hyb_t'] for r in rows),3))
