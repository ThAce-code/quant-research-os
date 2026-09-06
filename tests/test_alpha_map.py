import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from scipy.stats import spearmanr
from quant_research.m2.alpha_map import check_dates,mean_rank_correlation,cluster_basis,compress_basis,conditional_residual


def test_date_protection_and_nonoverlap():
    c=json.loads((Path(__file__).resolve().parents[1]/'configs/factors/m2_alpha_map.json').read_text())
    check_dates(c)
    for changes in [{'end':'2021-01-01'},{'basis_fit':['2015-01-01','2016-01-01']},{'protected_start':'2027-01-01'}]:
        with pytest.raises(ValueError):check_dates(c|changes)


def test_daily_pairwise_rank_with_different_missing_patterns():
    rng=np.random.default_rng(42)
    frame=pd.DataFrame(rng.normal(size=(80,3)),columns=['ROC5','MA5','STD5'],
                       index=pd.MultiIndex.from_product([pd.date_range('2015-01-01',periods=2),range(40)],names=['datetime','instrument']))
    frame.iloc[::5,0]=np.nan;frame.iloc[::7,1]=np.nan
    corr,n=mean_rank_correlation(frame,min_pairs=10)
    expected=[]
    for _,day in frame.groupby(level=0):
        pair=day.iloc[:,:2].dropna();expected.append(spearmanr(pair.iloc[:,0],pair.iloc[:,1]).statistic)
    assert abs(corr.loc['ROC5','MA5']-np.mean(expected))<1e-12
    assert n.loc['ROC5','MA5']==2


def test_clustering_opposite_duplicates_and_order_invariance():
    names=['ROC5','MA5','STD5']
    c=pd.DataFrame([[1,-.99,.1],[-.99,1,-.1],[.1,-.1,1]],index=names,columns=names)
    n=pd.DataFrame(200,index=names,columns=names);coverage=pd.Series(1.,index=names)
    a,_,_=cluster_basis(c,n,coverage)
    b,_,_=cluster_basis(c.iloc[::-1,::-1],n,coverage)
    pd.testing.assert_frame_equal(a,b)
    assert a.set_index('feature').loc['ROC5','cluster']==a.set_index('feature').loc['MA5','cluster']
    assert a.is_representative.sum()==2


def test_projection_uses_same_rows_and_removes_known_technical_component():
    rng=np.random.default_rng(3);dates=pd.date_range('2016-01-01',periods=2);stocks=list(range(120))
    b=pd.DataFrame(rng.normal(size=(240,2)),index=pd.MultiIndex.from_product([dates,stocks],names=['datetime','instrument']),columns=['x','z'])
    size=pd.DataFrame(rng.normal(size=(2,120)),index=dates,columns=stocks)
    industries=pd.DataFrame([['A']*60+['B']*60]*2,index=dates,columns=stocks)
    candidate=4*b.x.unstack('instrument')+size+rng.normal(size=(2,120))
    b.iloc[0,0]=np.nan
    matched,residual,checks=conditional_residual(candidate,b,size,industries)
    assert matched.notna().equals(residual.notna())
    assert pd.isna(residual.iloc[0,0])
    assert checks.orthogonality_error.max()<1e-10
    assert checks.explained_fraction.mean()>.8


def test_pca_future_changes_do_not_change_loadings_or_past_projection():
    rng=np.random.default_rng(5)
    index=pd.MultiIndex.from_product([pd.date_range('2015-01-01',periods=15),range(100)],names=['datetime','instrument'])
    frame=pd.DataFrame(rng.normal(size=(1500,5)),index=index,columns=list('abcde'))
    period=['2015-01-01','2015-01-11']
    a,weights,info=compress_basis(frame,period,max_components=3)
    changed=frame.copy();changed.loc['2015-01-12':]*=1000
    b,weights2,info2=compress_basis(changed,period,max_components=3)
    pd.testing.assert_frame_equal(weights,weights2)
    pd.testing.assert_frame_equal(a.loc[:'2015-01-11'],b.loc[:'2015-01-11'])
    assert info==info2 and info['components']==3
