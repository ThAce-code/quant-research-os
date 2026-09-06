"""Alpha158 geometry: original formulas, pairwise ranks and unsupervised basis."""
import re
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform


def family(name):
    if name.startswith('K'): return 'candlestick'
    prefix = re.sub(r'\d+$', '', name)
    groups = {
        'trend_reversal': {'ROC','MA','BETA','RSQR','RESI','CNTP','CNTN','CNTD','SUMP','SUMN','SUMD'},
        'price_position': {'MAX','MIN','QTLU','QTLD','RANK','RSV','IMAX','IMIN','IMXD'},
        'volatility': {'STD'},
        'price_volume': {'CORR','CORD','WVMA'},
        'volume_dynamics': {'VMA','VSTD','VSUMP','VSUMN','VSUMD'},
        'intraday_price_ratio': {'OPEN','HIGH','LOW','VWAP'},
    }
    for group, prefixes in groups.items():
        if prefix in prefixes: return group
    raise ValueError(f'unmapped feature: {name}')


def check_dates(config):
    for key in ['start','end', 'protected_start']:
        pd.Timestamp(config[key])
    fit, diagnostic = [pd.to_datetime(config[k]) for k in ['basis_fit','diagnostic']]
    if not (pd.Timestamp(config['start']) <= fit[0] <= fit[1] < diagnostic[0] <= diagnostic[1]
            <= pd.Timestamp(config['end']) < pd.Timestamp(config['protected_start'])):
        raise ValueError('overlapping, unordered or protected sample dates')
    if config['protected_start'] != '2021-01-01':
        raise ValueError('protected boundary cannot move in this research entry')


def mean_rank_correlation(frame, min_pairs=30):
    """Pairwise-complete DAILY Spearman then equal-weight average across days.

    Ranking is redone for each pair by pandas; this is not pooled correlation or
    Pearson correlation of ranks computed before pairwise missing-value removal.
    """
    names = frame.columns
    total = np.zeros((len(names),len(names)))
    counts = np.zeros_like(total, dtype=int)
    for _, cross in frame.groupby(level='datetime', sort=True):
        corr = cross.corr(method='spearman', min_periods=min_pairs).to_numpy()
        valid = np.isfinite(corr)
        total += np.where(valid, corr, 0)
        counts += valid
    mean = np.divide(total, counts, out=np.full_like(total, np.nan), where=counts>0)
    return pd.DataFrame(mean,index=names,columns=names), pd.DataFrame(counts,index=names,columns=names)


def cluster_basis(corr, counts, coverage, min_days=100, min_coverage=.9, threshold=.1):
    """Complete linkage on 1-|mean daily rho|, representatives chosen without y.

    Ineligible/undefined pairs have distance 1 for clustering only and stay null
    in the published observed matrix. Deterministic alphabetical ordering and
    within-cluster medoid ranking prevent arbitrary input-order differences.
    """
    names = sorted(n for n in corr if coverage[n]>=min_coverage and counts.loc[n,n]>=min_days)
    if len(names)<2: raise ValueError('insufficient eligible features')
    c = corr.loc[names,names].where(counts.loc[names,names]>=min_days)
    dist = 1-c.abs().fillna(0).clip(0,1).to_numpy()
    np.fill_diagonal(dist,0)
    z = linkage(squareform(dist, checks=True), method='complete')
    groups = fcluster(z, t=threshold, criterion='distance')
    members = sorted([sorted(np.array(names)[groups==g]) for g in np.unique(groups)],key=lambda a:a[0])
    rows=[]
    for number, group in enumerate(members,1):
        medoid = c.loc[group,group].abs().mean().sort_values(ascending=False,kind='stable').index[0]
        for name in group:
            rows.append({'feature':name,'family':family(name),'cluster':number,
                         'representative':medoid,'is_representative':name==medoid})
    return pd.DataFrame(rows), z, names


def compress_basis(frame, fit_period, variance_target=.9, max_components=20):
    """Training-only PCA on daily standardized representatives, no return labels.

    Missing observations are not imputed; fitting and projection use complete
    rows. Component signs are fixed by the largest absolute loading for stable
    exports. This is compression of measured geometry, not independent alphas.
    """
    grouped=frame.groupby(level='datetime')
    scale=grouped.transform('std').replace(0,np.nan)
    standardized=(frame-grouped.transform('mean'))/scale
    train=standardized.loc[fit_period[0]:fit_period[1]].dropna()
    if len(train)<max(1000,len(frame.columns)*5):
        raise ValueError('insufficient complete training rows for PCA')
    center=train.mean()
    covariance=np.cov((train-center).to_numpy(),rowvar=False)
    eigenvalues,loadings=np.linalg.eigh(covariance)
    eigenvalues=eigenvalues[::-1].clip(0)
    loadings=loadings[:,::-1]
    ratios=eigenvalues/eigenvalues.sum()
    requested=int(np.searchsorted(np.cumsum(ratios),variance_target)+1)
    count=min(max_components,requested,len(frame.columns))
    loadings=loadings[:,:count]
    for col in range(count):
        if loadings[np.argmax(np.abs(loadings[:,col])),col]<0:loadings[:,col]*=-1
    components=[f'PC{i+1:02}' for i in range(count)]
    result=pd.DataFrame(np.nan,index=frame.index,columns=components)
    complete=standardized.dropna()
    result.loc[complete.index]=(complete-center).to_numpy()@loadings
    return result,pd.DataFrame(loadings,index=frame.columns,columns=components),{
        'fit_period':fit_period,'training_complete_rows':len(train),'components':count,
        'variance_target':variance_target,'variance_retained':float(ratios[:count].sum()),
        'cap_binding':requested>max_components,'center':center.to_dict(),
        'explained_variance_ratio':ratios[:count].tolist()}


def conditional_residual(candidate, basis, log_size, industry, min_ratio=2):
    """Condition candidate on frozen representatives and known-at-t exposures.

    Complete-case stocks only; matched candidate uses exactly the same rows.
    Retain intercept/size/industry in this joint regression so restricting the
    sample does not silently invalidate an earlier neutralization.
    """
    residual = candidate * np.nan
    matched = candidate * np.nan
    checks=[]
    for day in candidate.index:
        cross = basis.xs(day,level='datetime').reindex(candidate.columns)
        cross = cross.replace([np.inf,-np.inf],np.nan)
        usable = cross.notna().all(axis=1) & candidate.loc[day].notna() & log_size.loc[day].notna() & industry.loc[day].notna()
        labels = industry.loc[day,usable]
        labels = labels[labels.map(labels.value_counts()).ge(5)]
        stocks = labels.index
        if len(stocks)<30: continue
        b = cross.loc[stocks]
        std = b.std(ddof=0)
        b = (b.loc[:,std.gt(1e-12)]-b.loc[:,std.gt(1e-12)].mean())/std[std.gt(1e-12)]
        size = log_size.loc[day,stocks]
        if size.std() <= 1e-12: continue
        x = np.column_stack([np.ones(len(stocks)),b.to_numpy(),(size-size.mean())/size.std(),
                             pd.get_dummies(labels,drop_first=True,dtype=float)])
        if len(stocks) < max(60,min_ratio*x.shape[1]): continue
        y = candidate.loc[day,stocks].to_numpy()
        fitted = x @ np.linalg.lstsq(x,y,rcond=None)[0]
        r=y-fitted
        if r.std()<=1e-12: continue
        residual.loc[day,stocks]=r/r.std()
        matched.loc[day,stocks]=y
        checks.append({'date':day,'stocks':len(stocks),'columns':x.shape[1],
                       'rank':int(np.linalg.matrix_rank(x)),
                       'explained_fraction':float(1-np.var(r)/np.var(y)),
                       'orthogonality_error':float(np.max(np.abs(x.T@r))/len(stocks))})
    return matched,residual,pd.DataFrame(checks)
