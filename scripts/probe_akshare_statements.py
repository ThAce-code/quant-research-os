"""Compare source-separated historical Eastmoney statements with BaoStock cache.

Uses the dated statement endpoints in AKShare 1.18.94's stock_three_report_em;
does not invoke its all-years wrapper or request protected-period observations.
"""
from pathlib import Path
import hashlib
import json
import sys
import pandas as pd
import requests


def main(folder):
    root = Path(__file__).resolve().parents[1]
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    audit = root / 'experiments/m2/m2_history_cache_audit_v1/20260906T095714683879Z'
    cached = json.loads((audit / 'available_requests.json').read_text(encoding='utf-8'))
    comparisons = []
    log_path = folder / 'probe.json'
    requests_log = json.loads(log_path.read_text(encoding='utf-8')) if log_path.exists() else []
    for symbol, code in [('SZ000630', 'sz.000630'), ('SH600519', 'sh.600519')]:
        for kind in ['zcfzb', 'lrb']:
            initial = folder / f'{symbol}_{kind}.json'
            if not initial.exists():
                url = f'https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/{kind}AjaxNew'
                params = {'companyType': '4', 'reportDateType': '0', 'reportType': '1',
                          'dates': '2006-09-30,2007-09-30,2015-09-30,2016-09-30', 'code': symbol}
                response = requests.get(url, params=params, timeout=(10, 25))
                response.raise_for_status()
                body = response.json()
                assert len(body['data']) == 4
                initial.write_text(json.dumps(body, ensure_ascii=False), encoding='utf-8')
                requests_log.append({'symbol': symbol, 'kind': kind, 'url': url, 'params': params, 'rows': 4})
                log_path.write_text(json.dumps(requests_log, ensure_ascii=False, indent=2), encoding='utf-8')
        path = folder / f'{symbol}_opening_equity.json'
        if not path.exists():
            url = 'https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/zcfzbAjaxNew'
            params = {'companyType': '4', 'reportDateType': '0', 'reportType': '1',
                      'dates': '2006-12-31,2015-12-31', 'code': symbol}
            response = requests.get(url, params=params, timeout=(10, 25))
            response.raise_for_status()
            body = response.json()
            assert len(body['data']) == 2
            path.write_text(json.dumps(body, ensure_ascii=False), encoding='utf-8')
            requests_log.append({'symbol': symbol, 'url': url, 'params': params, 'rows': 2})
            log_path.write_text(json.dumps(requests_log, ensure_ascii=False, indent=2), encoding='utf-8')
        def rows(name):
            return {x['REPORT_DATE'][:10]: x for x in json.loads((folder / name).read_text(encoding='utf-8'))['data']}
        balance = rows(f'{symbol}_zcfzb.json')
        income = rows(f'{symbol}_lrb.json')
        opening = rows(path.name)
        for year in [2007, 2016]:
            period = f'{year}-09-30'
            b, i, start = balance[period], income[period], opening[f'{year-1}-12-31']
            assert all(x['NOTICE_DATE'][:10] <= '2020-07-31' for x in [b, i, start])
            reconstructed = {
                'roeAvg': i['PARENT_NETPROFIT'] / ((start['TOTAL_PARENT_EQUITY'] + b['TOTAL_PARENT_EQUITY']) / 2),
                'npMargin': i['NETPROFIT'] / i['OPERATE_INCOME'],
                'YOYNI': i['NETPROFIT_YOY'] / 100,
                'YOYAsset': b['TOTAL_ASSETS_YOY'] / 100,
                'YOYEquity': b['TOTAL_PARENT_EQUITY_YOY'] / 100,
            }
            for method, fields in [('query_profit_data', ['roeAvg', 'npMargin']),
                                   ('query_growth_data', ['YOYNI', 'YOYAsset', 'YOYEquity'])]:
                matches = [x for x in cached if x['method'] == method and x['params'] == {'code': code, 'year': year, 'quarter': 3}]
                bs = None
                if matches:
                    source = Path(matches[0]['path'])
                    assert hashlib.sha256(source.read_bytes()).hexdigest() == matches[0]['sha256']
                    data = pd.read_csv(source)
                    if len(data) == 1:
                        bs = data.iloc[0]
                for field in fields:
                    value = reconstructed[field]
                    original = float(bs[field]) if bs is not None else None
                    comparisons.append({'symbol': symbol, 'period': period, 'field': field,
                                        'eastmoney': value, 'baostock': original,
                                        'absolute_difference': abs(value-original) if original is not None else None,
                                        'baostock_pubDate': bs.pubDate if bs is not None else None,
                                        'balance_notice_date': b['NOTICE_DATE'], 'income_notice_date': i['NOTICE_DATE'],
                                        'income_update_date': i['UPDATE_DATE'],
                                        'balance_update_date': b['UPDATE_DATE']})
    frame = pd.DataFrame(comparisons)
    frame.to_csv(folder / 'comparison.csv', index=False)
    present = frame.baostock.notna()
    summary = {'status': 'FEASIBILITY_ONLY', 'rows_compared': int(present.sum()),
               'rows_within_1e_5': int(frame.absolute_difference.le(1e-5).sum()),
               'missing_baostock_field_observations': int((~present).sum()),
               'max_absolute_difference': float(frame.absolute_difference.max()),
               'production_data_modified': False, 'revision_history_verified': False,
               'company_type': '4, ordinary-company sample only; not a universal mapping',
               'statement_endpoint_origin': 'AKShare 1.18.94 stock_three_report_em.py',
               'requests': requests_log,
               'formulas': {'roeAvg': 'PARENT_NETPROFIT / mean(previous year-end, current TOTAL_PARENT_EQUITY)',
                            'npMargin': 'NETPROFIT / OPERATE_INCOME',
                            'YOYNI': 'NETPROFIT_YOY / 100',
                            'YOYAsset': 'TOTAL_ASSETS_YOY / 100',
                            'YOYEquity': 'TOTAL_PARENT_EQUITY_YOY / 100'}}
    (folder / 'comparison_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(frame[['symbol', 'period', 'field', 'eastmoney', 'baostock', 'absolute_difference']].to_string(index=False))
    print(json.dumps({k:v for k,v in summary.items() if k not in ['requests','formulas']}))


if __name__ == '__main__':
    main(sys.argv[1])
