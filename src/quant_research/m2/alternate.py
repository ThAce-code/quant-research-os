"""Source-labelled financial reconstruction; no return-based research decisions."""
import numpy as np
import pandas as pd

FIELDS = ['roeAvg', 'npMargin', 'YOYNI', 'YOYAsset', 'YOYEquity']


def numeric(row, field):
    value = pd.to_numeric(row.get(field) if row is not None else None, errors='coerce')
    return float(value) if pd.notna(value) and np.isfinite(value) else np.nan


def divide(numerator, denominator):
    if not np.isfinite(numerator) or not np.isfinite(denominator) or denominator == 0:
        return np.nan
    return numerator / denominator


def field_events(code, periods, balance, income, conservative=True):
    """Emit missing current reports before delayed dependencies become available."""
    records = []
    for period in periods:
        b, i = balance.get(period), income.get(period)
        opening = balance.get(f'{int(period[:4])-1}-12-31')
        for field in FIELDS:
            if field == 'roeAvg':
                current, needed = [b, i], [b, i, opening]
                value = divide(numeric(i, 'PARENT_NETPROFIT'),
                               (numeric(b, 'TOTAL_PARENT_EQUITY')+numeric(opening, 'TOTAL_PARENT_EQUITY'))/2)
            elif field == 'npMargin':
                current = needed = [i]
                denominator = 'TOTAL_OPERATE_INCOME' if i is not None and i.get('ORG_TYPE') in {'银行','证券','保险'} else 'OPERATE_INCOME'
                value = divide(numeric(i, 'NETPROFIT'), numeric(i, denominator))
            else:
                row, key = {'YOYNI': (i, 'NETPROFIT_YOY'), 'YOYAsset': (b, 'TOTAL_ASSETS_YOY'),
                            'YOYEquity': (b, 'TOTAL_PARENT_EQUITY_YOY')}[field]
                current = needed = [row]
                value = numeric(row, key)/100
            notices = [pd.Timestamp(row['NOTICE_DATE']).normalize() for row in current if row is not None]
            if not notices:
                continue  # Explicitly accounted source absence; never invent a date.
            first = min(notices)
            complete = all(row is not None for row in needed)
            available = max(pd.Timestamp(row['NOTICE_DATE']).normalize() for row in needed) if complete else first
            if complete and conservative:
                updates=[pd.to_datetime(row.get('UPDATE_DATE'),errors='coerce') for row in needed]
                if any(pd.isna(date) for date in updates):
                    value=np.nan  # No trusted version timestamp; retain missing.
                else:
                    available=max([available]+[date.normalize() for date in updates])
            revision = any(pd.notna(row.get('UPDATE_DATE')) and pd.Timestamp(row['UPDATE_DATE']).normalize() > pd.Timestamp(row['NOTICE_DATE']).normalize()
                           for row in needed if row is not None)
            base = {'code':code, 'statDate':pd.Timestamp(period), 'field':field,
                    'source':'eastmoney_reconstructed', 'revision_unknown':True,
                    'updated_after_notice':revision, 'dependencies_present':complete}
            records.append({**base, 'pubDate':first, 'value':np.nan if available>first or not complete else value})
            if complete and available>first:
                records.append({**base, 'pubDate':available, 'value':value})
    return pd.DataFrame(records,columns=['code','statDate','field','source','revision_unknown',
                                        'updated_after_notice','dependencies_present','pubDate','value'])
