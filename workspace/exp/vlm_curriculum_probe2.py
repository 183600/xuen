import json, itertools
import numpy as np
from scipy import stats
d=json.load(open('exp/r16_leaderboard_data.json'))
tasks=d['tasks']; models=[m['model_name'] for m in d['models']]
S=np.zeros((len(models),len(tasks)))
for i,m in enumerate(d['models']):
    tm={t['task']:t for t in m['task_metrics']}
    for j,t in enumerate(tasks): S[i,j]=tm[t]['success_rate']
def sp(a,b): return float(stats.spearmanr(a,b).statistic)
def kw(M):
    m,n=M.shape
    R=np.apply_along_axis(stats.rankdata,0,M)
    rs=R.sum(1); return float(12*((rs-rs.mean())**2).sum()/(m**2*(n**3-n)))
def report(name,idx):
    M=S[idx]
    pair=[sp(M[i],M[k]) for i,k in itertools.combinations(range(len(idx)),2)]
    print(name,'n=',len(idx),'W=%.4f'%kw(M),'meanSpearman=%.4f'%np.mean(pair),'range=[%.3f,%.3f]'%(min(pair),max(pair)))
# top-k by avg
avg=S.mean(1); order=np.argsort(-avg)
for k in [2,3,4,5,6,8]: report('top%d'%k,order[:k])
# leader vs global difficulty ordering
lead=order[0]; print('\nleader',models[lead])
diff=1-S.mean(0)/100
print('leader-difficulty (1-success) vs global difficulty Spearman',round(sp(1-S[lead]/100,diff),3))
# tasks where leader is worst/best
o=np.argsort(S[lead]); print('leader hardest:',[(tasks[j],round(S[lead,j],1)) for j in o[:6]])
print('leader easiest:',[(tasks[j],round(S[lead,j],1)) for j in o[-6:]])
# global hardest
og=np.argsort(S.mean(0)); print('global hardest:',[(tasks[j],round(S.mean(0)[j],1)) for j in og[:6]])
# within-task std vs mean
print('mean within-task std',round(S.std(0).mean(),3))
