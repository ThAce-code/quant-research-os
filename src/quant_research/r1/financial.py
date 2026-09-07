"""Same-fiscal-period financial hypotheses, publication-aligned before use."""
import numpy as np
import pandas as pd

from ..m2.quarterly import daily_panel


FINANCIAL=['R1_CASH_SURPLUS','R1_CASH_IMPROVEMENT','R1_GROSS_MARGIN_CHANGE','R1_NET_MARGIN_CHANGE']


def number(row,key):
    if row is None:return np.nan
    value=row.get(key,np.nan)
    return float(value) if pd.notna(value) and np.isfinite(value) else np.nan


def surplus(profit,cash):
    # Fixed consistency tolerances are data checks, not return-based filters.
    m=number(profit,'npMargin')
    cf,cp=[number(cash,k) for k in ['CFOToOR','CFOToNP']]
    if not all(np.isfinite(x) for x in [m,cf,cp]):return np.nan
    if not np.isclose(cp*m,cf,rtol=2e-5,atol=2e-5):return np.nan
    return cf-m


def events_for_symbol(profit,cash,code,end):
    p={pd.Timestamp(r['statDate']):r for r in profit.to_dict('records')}
    c={pd.Timestamp(r['statDate']):r for r in cash.to_dict('records')}
    events={name:[] for name in FINANCIAL}
    for period in sorted(set(p)|set(c)):
        p0,c0=p.get(period),c.get(period)
        prior=period-pd.DateOffset(years=1)
        p1,c1=p.get(prior),c.get(prior)
        values={
            FINANCIAL[0]:(surplus(p0,c0),[p0,c0],[p0,c0]),
            FINANCIAL[1]:(surplus(p0,c0)-surplus(p1,c1),[p0,c0],[p0,c0,p1,c1]),
            FINANCIAL[2]:(number(p0,'gpMargin')-number(p1,'gpMargin'),[p0],[p0,p1]),
            FINANCIAL[3]:(number(p0,'npMargin')-number(p1,'npMargin'),[p0],[p0,p1])}
        for name,(value,current,needed) in values.items():
            # Any observed current-quarter release invalidates stale previous
            # quarter values even if this candidate's other inputs are missing.
            current_dates=[pd.Timestamp(r['pubDate']) for r in [p0,c0] if r is not None]
            if not current_dates:continue
            first=min(current_dates)
            complete=all(r is not None for r in needed)
            available=max(pd.Timestamp(r['pubDate']) for r in needed) if complete else first
            available=max(first,available)
            if not complete or not np.isfinite(value):value=np.nan
            base={'code':code,'statDate':period,'dependency_count':len(needed),
                  'dependencies_present':complete,'revision_unknown':True}
            if first<=pd.Timestamp(end):
                events[name].append({**base,'pubDate':first,'value':value if available==first else np.nan,
                                     'value_available':available})
            if complete and available>first and available<=pd.Timestamp(end):
                events[name].append({**base,'pubDate':available,'value':value,'value_available':available})
    columns=['code','statDate','dependency_count','dependencies_present','revision_unknown','pubDate','value','value_available']
    return {name:pd.DataFrame(rows,columns=columns) for name,rows in events.items()}


def transfer(events,dates):
    result=daily_panel(events,dates,['value','value_available'],400,550)
    values=pd.to_numeric(result.value,errors='coerce')
    # This redundant assertion makes the dependency-time invariant explicit.
    if (values.notna() & pd.to_datetime(result.value_available).ge(pd.Series(dates,index=dates))).any():
        raise ValueError('financial dependency not strictly available before signal')
    return values,result
