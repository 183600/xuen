import sys, pickle, json, time
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v14')
import po, pace

def run(inst, h, mode, **kw):
    if mode == 'sub':
        (ok,out),st = po.decide(inst,h,mode='sub',nodecap=400000)
        st = dict(st); st.setdefault('pot_prunes',0); st.setdefault('pot_calls',0)
        st.setdefault('pot_time',0.0); st.setdefault('root_wit',None)
        st.setdefault('estcut_hits',0); st.setdefault('t_run',None)
        return ok, st
    (ok,out),st = pace.decide(inst,h,mode='pot',nodecap=400000,**kw)
    return ok, st

def bench(items, tag, out):
    rows=[]
    for idx,rec in enumerate(items):
        inst=rec['inst']; opt=rec['opt']
        h=opt-1
        row={'tag':tag,'idx':idx,'n':inst['n'],'m':inst['m'],'opt':opt}
        for name,kw in (('sub',{}),('pot0',{'pot_depth':0}),
                        ('pot6',{'pot_depth':6})):
            t=time.time(); ok,st=run(inst,h,'sub' if name=='sub' else 'pot',**kw); dt=time.time()-t
            row[name]={'ok':ok,'nodes':st['nodes'],'time':round(dt,4),
                       'tables':st['tables'],'potcalls':st.get('pot_calls',0),
                       'potprunes':st.get('pot_prunes',0),
                       'esthits':st.get('estcut_hits',0),
                       'timeout':st.get('timeout',False),
                       'wit':st.get('root_wit')}
        rows.append(row)
        print(tag,idx,'n',inst['n'],'opt',opt,
              'sub',row['sub']['nodes'],'pot0',row['pot0']['nodes'],
              'pot6',row['pot6']['nodes'],flush=True)
    json.dump(rows,open(out,'w'),default=str)
    return rows

if __name__=='__main__':
    jobs=[('hard3','exp/v13/hard3.pkl','exp/v14/res_hard3.json'),
          ('large_b','exp/v14/large_b.pkl','exp/v14/res_largeb.json'),
          ('large_a','exp/v14/large_a.pkl','exp/v14/res_largea.json'),
          ('large_het','exp/v14/large_het.pkl','exp/v14/res_het.json')]
    for tag,path,out in jobs:
        d=pickle.load(open(path,'rb'))
        if isinstance(d,list) and d and isinstance(d[0],tuple):
            d=[{'inst':x[0],'opt':x[1]} for x in d]
        bench(d,tag,out)
