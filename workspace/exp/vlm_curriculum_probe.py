import json, itertools, math
import numpy as np
from scipy import stats

DATA='exp/r16_leaderboard_data.json'
STATS='exp/r16_leaderboard_stats.json'

d=json.load(open(DATA)); st=json.load(open(STATS))
tasks=d['tasks']; models=[m['model_name'] for m in d['models']]
S=np.zeros((len(models),len(tasks)))
dur=np.zeros_like(S)
for i,m in enumerate(d['models']):
    tm={t['task']:t for t in m['task_metrics']}
    for j,t in enumerate(tasks):
        S[i,j]=tm[t]['success_rate']
        dur[i,j]=tm[t]['avg_duration_sec']

pt={p['task']:p for p in st['per_task']}
rubric=np.array([pt[t]['rubric_steps'] for t in tasks],float)
wcnt=np.array([len(t.split()) for t in tasks],float)
mean_s=S.mean(0); max_s=S.max(0); min_s=S.min(0)
diff=1-mean_s/100.0
headroom=max_s-mean_s
durmean=dur.mean(0)

def spearman(a,b):
    return float(stats.spearmanr(a,b).statistic)
def kendall_w(mat):
    m,n=mat.shape
    R=np.apply_along_axis(stats.rankdata,0,mat)  # rank within each model across tasks
    Rsum=R.sum(1)  # sum ranks per task across models
    Ssum=((Rsum-Rsum.mean())**2).sum()
    return float(12*Ssum/(m**2*(n**3-n)))

# 1. difficulty consistency across models
pair=[spearman(S[i],S[k]) for i,k in itertools.combinations(range(len(models)),2)]
kw=kendall_w(S)

# 2. cheap metadata predictors (leave-one-task-out)
def loo_linear(X,y):
    n=len(y); pred=np.zeros(n)
    X1=np.column_stack([np.ones(n),X])
    for i in range(n):
        mask=np.arange(n)!=i
        beta,*_=np.linalg.lstsq(X1[mask],y[mask],rcond=None)
        pred[i]=X1[i]@beta
    ss_res=((y-pred)**2).sum(); ss_tot=((y-y.mean())**2).sum()
    return pred, 1-ss_res/ss_tot
pred_meta,r2_meta=loo_linear(np.column_stack([rubric,wcnt]),mean_s)
pred_full,r2_full=loo_linear(np.column_stack([rubric,wcnt,durmean]),mean_s)

# 3. learnability gating: does headroom shrink as difficulty rises?
rho_head=spearman(diff,headroom)
# hardest quartile vs easiest quartile headroom
order=np.argsort(-diff); q=len(tasks)//4
hard=order[:q]; easy=order[-q:]
# 4. oracle gain concentration
oracle_gain=headroom  # max - mean per task
hard_share=oracle_gain[hard].sum()/oracle_gain.sum()
# 5. per-task "reachability": max success
rho_diff_max=spearman(diff,max_s)

res={
 'n_models':len(models),'n_tasks':len(tasks),
 'difficulty_consistency':{
   'kendall_w':kw,
   'mean_pairwise_spearman':float(np.mean(pair)),
   'min_pairwise_spearman':float(np.min(pair)),
   'max_pairwise_spearman':float(np.max(pair)),
 },
 'cheap_metadata_predictor':{
   'features':['rubric_steps','name_word_count'],
   'loo_r2':float(r2_meta),
   'spearman_pred_vs_true':spearman(pred_meta,mean_s),
   'with_duration_loo_r2':float(r2_full),
   'with_duration_spearman':spearman(pred_full,mean_s),
 },
 'learnability_gating':{
   'spearman_difficulty_vs_headroom':rho_head,
   'spearman_difficulty_vs_max_success':rho_diff_max,
   'hard_quartile_mean_headroom':float(headroom[hard].mean()),
   'easy_quartile_mean_headroom':float(headroom[easy].mean()),
   'oracle_gain_share_in_hard_quartile':float(hard_share),
 },
 'variance_decomposition_from_prev':{
   'task_effect_frac':0.1644,'model_effect_frac':0.2332,'interaction_frac':0.6024
 },
 'hard_tasks':[tasks[i] for i in order[:8]],
 'easy_tasks':[tasks[i] for i in order[-8:]],
}
json.dump(res,open('exp/vlm_curriculum_probe_results.json','w'),ensure_ascii=False,indent=2)
print(json.dumps(res,ensure_ascii=False,indent=2))
