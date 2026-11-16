import numpy as np, json
rng = np.random.default_rng(7)

def slip_sim(rate=0.01, mu_true=0.6, mu_est=0.5, f0=10.0, fmax=20.0,
             reflex=True, gain=0.05, dt=1e-3, T=3.0):
    fn=float(f0); ft=0.0; slip_imp=0.0; slip_dist=0.0; v=0.0; t_detect=None
    for k in range(int(T/dt)):
        ft += rate*dt*1e3*dt*0 + rate   # rate N/ms, one ms tick
        m_true = 1.0 - ft/(mu_true*fn)
        m_hat  = 1.0 - ft/(mu_est*fn)
        if reflex:
            if t_detect is None and m_hat <= 0.0:
                t_detect = k*dt
            if t_detect is not None:
                fn = min(fmax, fn + gain)
        if m_true < 0:
            excess = ft - mu_true*fn
            slip_imp += excess*dt
            v += (excess/0.2)*dt
            slip_dist += v*dt
        else:
            v = max(0.0, v-5.0*dt)
        if fn >= fmax and ft >= mu_true*fmax:
            break
    return {'t_detect_s':t_detect,'slip_impulse_Ns':max(0.0,slip_imp),
            'slip_dist_m':max(0.0,slip_dist),'final_fn_N':fn,
            'force_over':fn-f0}

out={'slip':{}}
for rate in [0.005,0.01,0.02]:
    row={}
    row['fixed']=slip_sim(rate=rate,reflex=False)
    for mu in [0.4,0.5,0.6,0.8]:
        row[f'reflex_mu_est_{mu}']=slip_sim(rate=rate,reflex=True,mu_est=mu)
    out['slip'][f'rate_{rate}']=row

def corr_test(win=200):
    p=rng.normal(size=win); o=p+rng.normal(scale=0.8,size=win)
    return float(np.corrcoef(p,o)[0,1])
def false_alarm(tau=0.3,H=3,trials=2000):
    fa=0
    for _ in range(trials):
        c=0
        for _ in range(20):
            c = c+1 if corr_test()<tau else 0
            if c>=H: fa+=1; break
    return fa/trials
def detect_delay(tau=0.3,H=3,eps=0.5,trials=500,maxw=200):
    delays=[]
    for _ in range(trials):
        c=0; det=False
        for w in range(maxw):
            p=rng.normal(size=200)
            alpha=min(1.0,eps*(w+1))
            o=(1-alpha)*p+alpha*rng.normal(size=200)+rng.normal(scale=0.8,size=200)
            r=float(np.corrcoef(p,o)[0,1])
            c=c+1 if r<tau else 0
            if c>=H: delays.append(w); det=True; break
        if not det: delays.append(maxw)
    return float(np.mean(delays)),float(np.percentile(delays,95))

out['meta']={
  'false_alarm':{f'tau_{t}':false_alarm(tau=t) for t in [0.2,0.3,0.4]},
  'detect_delay':[]}
for eps in [0.1,0.2,0.5]:
    m,p95=detect_delay(eps=eps)
    out['meta']['detect_delay'].append({'eps':eps,'mean_win':m,'p95_win':p95,
        'mean_s':m*4.0,'p95_s':p95*4.0})   # window=200 samples @50Hz=4s
print(json.dumps(out,indent=2,ensure_ascii=False))
