import itertools

def agreement(a,b):
    keys=set(a)&set(b); n=len(keys)
    if not n: return {'cases':0,'agreement':None,'expected':None,'excess':None}
    p=sum(bool(a[k]) for k in keys)/n; q=sum(bool(b[k]) for k in keys)/n
    observed=sum(a[k]==b[k] for k in keys)/n; expected=p*q+(1-p)*(1-q)
    return {'cases':n,'agreement':observed,'expected':expected,'excess':observed-expected}
def stratified_excess(outcomes):
    if len(outcomes)<4: return {'stratified':None,'why':'requires four producers'}
    vals=[]
    for a,b in itertools.combinations(outcomes,2):
        others=[v for k,v in outcomes.items() if k not in (a,b)]
        for case in set(outcomes[a])&set(outcomes[b]):
            x=[bool(v[case]) for v in others if case in v]; n=len(x)
            if n>=2:
                s=sum(x); null=(s*(s-1)+(n-s)*(n-s-1))/(n*(n-1)); vals.append(float(outcomes[a][case]==outcomes[b][case])-null)
    return {'stratified':sum(vals)/len(vals) if vals else None,'why':None}
