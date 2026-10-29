import sys,json,pickle
sys.path.insert(0,'exp/v13'); sys.path.insert(0,'exp/v16')
import po, order_sop as sop
j=json.load(open('exp/v16/res_sop.json'))
print('v14',sum(r['nodes'] for r in j['v14']),round(sum(r['time'] for r in j['v14']),4),sum(r['tables'] for r in j['v14']))
print('v15',sum(r['nodes'] for r in j['v15']),round(sum(r['time'] for r in j['v15']),4),sum(r['tables'] for r in j['v15']))
d=pickle.load(open('exp/v13/hard3.pkl','rb')); rec=d[2]; inst,opt=rec[0],rec[1]
v,st=sop.root_gate(inst,opt-1); c=st['cert']
print('hard3#2',v,'chain',c['chain'],'W',c['window'],'forced',c['forced'],
      'items',c['pack']['items'],'pack_nodes',st['pack_nodes'],'sop_time',round(st['sop_time'],4),
      'check',sop.check_cert(inst,opt-1,c))
json.dump({'v14_nodes':sum(r['nodes'] for r in j['v14']),'v15_nodes':sum(r['nodes'] for r in j['v15']),
           'v14_time':sum(r['time'] for r in j['v14']),'v15_time':sum(r['time'] for r in j['v15']),
           'v14_tables':sum(r['tables'] for r in j['v14']),'v15_tables':sum(r['tables'] for r in j['v15']),
           'hard3_2':{'chain':c['chain'],'window':c['window'],'forced':c['forced'],
                      'items':c['pack']['items'],'pack_nodes':st['pack_nodes'],
                      'sop_time':st['sop_time']}},
          open('exp/v16/summary.json','w'),indent=1)
