import numpy as np
import pandas as pd
import pytest
from quant_research.m2.supplementary_data import illiquidity,cash_events


def test_illiquidity_requires_complete_window_and_has_no_future_dependency():
    b=pd.DataFrame({'close':np.arange(1,51,dtype=float),'factor':1.,'amount':1e6,'is_suspended':False})
    x=illiquidity(b)
    assert x.iloc[:20].isna().all() and np.isfinite(x.iloc[20])
    pd.testing.assert_series_equal(x.iloc[:30],illiquidity(b.iloc[:30]))
    b.loc[25,'is_suspended']=True
    assert illiquidity(b).iloc[25:46].isna().all()


def test_late_publication_excluded_but_invalid_in_window_fails():
    f=pd.DataFrame({'code':['sh.600000']*2,'pubDate':['2020-04-01','2020-08-01'],
                    'statDate':['2020-03-31','2020-06-30'],'CFOToOR':['-0.2','999']})
    clean,n=cash_events(f,'sh.600000','2020-07-31')
    assert clean.CFOToOR.tolist()==[-.2] and n==1
    f.loc[0,'CFOToOR']='bad'
    with pytest.raises(ValueError):cash_events(f,'sh.600000','2020-07-31')
