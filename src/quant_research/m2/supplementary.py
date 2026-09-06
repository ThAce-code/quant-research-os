"""Exact request bounds for the next fixed two-hypothesis batch."""
import pandas as pd


def request_plan(intervals,c):
    if c['data_period']!=['2008-01-01','2020-07-31'] or c['financial_quarter_bounds']!=['2007Q1','2020Q2']:
        raise ValueError('supplementary history bounds require a new protocol')
    e=intervals.copy();e['start']=pd.to_datetime(e.start);e['end']=pd.to_datetime(e.end)
    start,end=map(pd.Timestamp,c['data_period'])
    e=e[e.start.le(end)&e.end.ge(start)]
    rows=[]
    for symbol,g in e.groupby('instrument'):
        first=max(start,g.start.min());last=min(end,g.end.max())
        earliest=max(pd.Timestamp('2007-03-31'),first-pd.Timedelta(days=550))
        for q in pd.period_range(earliest,last,freq='Q'):
            fiscal=q.end_time.normalize()
            if fiscal<earliest or fiscal>last:continue
            rows.append({'symbol':symbol,'code':symbol[:2].lower()+'.'+symbol[2:],
                         'method':'query_cash_flow_data','year':q.year,'quarter':q.quarter,
                         'first_signal':str(first.date()),'last_signal':str(last.date())})
    return pd.DataFrame(rows)
