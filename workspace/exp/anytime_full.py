import sys, json, pickle
sys.path.insert(0,'.')
from proto_full import run_full

def gap_at(anytime, final, opt, b, steps):
    if steps <= b:
        return max(0, final-opt)
    vals=[v for k,v in anytime.items() if int(k)<=b]
    u=min(vals) if vals else final
    return max(0,u-opt)

def main():
    pool=pickle.load(open('pool30.pkl','rb'))
    hard=[6,11,13,14,19,27,29]
    budgets=(5,10,20,40,80,160)
    rows=[]
    for k in hard:
        inst,opt,nd=pool[k]
        out={}
        for tag,rb,d in (('L0','L0',0),('TENT','TENT',0),('TENTd1','TENT',1)):
            r=run_full(inst,budget=400,delta=d,root_bound=rb)
            out[tag]=r
        row={'k':k,'opt':opt}
        for tag in out:
            row[tag]={b:gap_at(out[tag]['anytime'],out[tag]['U'],opt,b,out[tag]['steps']) for b in budgets}
            row[tag]['nodes']=out[tag]['steps']
        rows.append(row)
        print(k,opt,{tag:(out[tag]['steps'],row[tag]) for tag in out},flush=True)
    print('\navg gaps on hard-7')
    for b in budgets:
        print(b,{tag:round(sum(r[tag][b] for r in rows)/len(rows),3) for tag in ('L0','TENT','TENTd1')})
    json.dump(rows,open('anytime_full.json','w'),indent=1)

if __name__=='__main__': main()
