import sys, pickle, time, json
sys.path.insert(0,'exp/v14')
import sp
d=pickle.load(open('exp/v13/hard3.pkl','rb'))
configs=[('v12',dict()),('time',dict(child='time')),('idle',dict(child='idle')),('lexA',dict(child='lexA'))]
rows=[]
tot={k:[0,0.0,0] for k,_ in configs}
for idx,(inst,opt,n0) in enumerate(d):
    row={'idx':idx,'n':inst['n'],'opt':opt}
    print('inst',idx,'n',inst['n'],flush=True)
    for name,pol in configs:
        t=time.time(); (ok,s),st=sp.decide(inst,opt-1,mode='sub',nodecap=3_000_000,policy=pol); dt=time.time()-t
        row[name]=dict(nodes=st['nodes'],t=round(dt,4),tables=st['tables'],subh=st['sub_front_hits'],ok=ok)
        tot[name][0]+=st['nodes']; tot[name][1]+=dt; tot[name][2]+=st['tables']
        print('  ',name,st['nodes'],round(dt,3),flush=True)
    rows.append(row)
    json.dump(rows,open('exp/v14/all12.json','w'),indent=1)
print(tot)
for k,v in tot.items():
    print(k,'nodes',v[0],'ratio',round(v[0]/tot['v12'][0],3),'time',round(v[1],3),'tratio',round(v[1]/tot['v12'][1],3))
