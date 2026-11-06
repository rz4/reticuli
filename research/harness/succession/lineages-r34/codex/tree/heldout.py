import itertools

def agreement(a,b):
    keys=set(a)&set(b);n=len(keys)
    if not n:return {'cases':0,'agreement':None,'expected':None,'excess':None}
    p=sum(bool(a[k]) for k in keys)/n;q=sum(bool(b[k]) for k in keys)/n
    observed=sum(bool(a[k])==bool(b[k]) for k in keys)/n;expected=p*q+(1-p)*(1-q)
    return {'cases':n,'agreement':observed,'expected':expected,'excess':observed-expected}

def stratified_excess(population):
    if len(population)<4:return {'stratified':None,'why':'at least four producers are required'}
    vals=[];names=list(population)
    for a,b in itertools.combinations(names,2):
        for c in set(population[a])&set(population[b]):
            rest=[bool(population[n][c]) for n in names if n not in (a,b) and c in population[n]]
            if len(rest)<2:continue
            n=len(rest);k=sum(rest);expected=(k*(k-1)+(n-k)*(n-k-1))/(n*(n-1))
            vals.append(float(bool(population[a][c])==bool(population[b][c]))-expected)
    return {'stratified':sum(vals)/len(vals) if vals else None,'why':None if vals else 'insufficient shared cases'}
