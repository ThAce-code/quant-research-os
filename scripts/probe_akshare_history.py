"""Bounded AKShare/Eastmoney feasibility probe; never writes BaoStock caches."""
from datetime import datetime, timezone
import hashlib
import inspect
import json
from pathlib import Path
from unittest.mock import patch

import akshare as ak
import pandas as pd
import requests


def main():
    root = Path(__file__).resolve().parents[1]
    out = root / 'experiments/m2/akshare_source_probe' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True)
    endpoint = 'https://datacenter.eastmoney.com/securities/api/data/get'
    original_get = requests.get
    records = []

    def historical_get(url, **kwargs):
        if url != endpoint:
            raise ValueError('Unregistered endpoint')
        params = dict(kwargs['params'])
        params['filter'] += "(REPORT_DATE>='2007-01-01')(REPORT_DATE<='2020-06-30')(NOTICE_DATE<='2020-07-31')"
        records.append({'url': url, 'params': params})
        response = original_get(url, params=params, timeout=(10, 25))
        response.raise_for_status()
        body = response.json()
        (out / f'response_{len(records)}.json').write_text(json.dumps(body, ensure_ascii=False), encoding='utf-8')
        if body.get('result') and body['result'].get('pages', 1) > 1:
            raise ValueError('Unexpected pagination; cannot claim complete response')
        return response

    results = []
    for symbol in ['000630.SZ', '600519.SH']:
        try:
            with patch('requests.get', historical_get):
                frame = ak.stock_financial_analysis_indicator_em(symbol=symbol, indicator='按报告期')
            dates = pd.to_datetime(frame['REPORT_DATE'])
            notice = pd.to_datetime(frame['NOTICE_DATE'])
            assert dates.between('2007-01-01', '2020-06-30').all()
            assert notice.le(pd.Timestamp('2020-07-31')).all()
            frame.to_csv(out / f'{symbol}.csv', index=False)
            results.append({'symbol': symbol, 'status': 'FETCHED', 'rows': len(frame),
                            'first_period': str(dates.min()), 'last_period': str(dates.max()),
                            'columns': list(frame.columns)})
        except Exception as exc:
            results.append({'symbol': symbol, 'status': 'FAILED', 'error': str(exc), 'exception': type(exc).__name__})
            break  # No automatic retries after a failed probe.
    report = {'akshare_version': ak.__version__, 'requests': records, 'results': results,
              'source_sha256': hashlib.sha256(inspect.getsource(ak.stock_financial_analysis_indicator_em).encode()).hexdigest(),
              'historical_filter': 'Added at HTTP boundary because AKShare public function has no date argument',
              'baostock_requests': 0, 'production_data_modified': False, 'substitution_approved': False}
    (out / 'probe.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(out, flush=True)
    print(json.dumps(report, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
