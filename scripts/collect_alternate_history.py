"""Collect bounded Eastmoney statements using AKShare's documented source tables."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import pandas as pd
import requests
from filelock import FileLock

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def body_hash(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def unpack(body):
    if body.get('code') == 9201 and '空' in body.get('message', ''):
        return [], 0, 0
    if body.get('code') != 0 or not isinstance(body.get('result'), dict):
        raise ValueError(f"Source rejected request: {body.get('code')} {body.get('message')}")
    result = body['result']
    return result['data'], int(result['pages']), int(result['count'])


def run(output=None):
    c = json.loads((ROOT/'configs/factors/m2_alternate_history.json').read_text(encoding='utf-8'))
    plan = ROOT/c['plan_run']; audit = ROOT/c['cache_audit_run']
    for name, sha in c['input_hashes'].items():
        assert digest((plan if name == 'request_plan.csv' else audit)/name) == sha
    complete = pd.read_csv(audit/'stock_method_completeness.csv')
    incomplete = sorted(complete.loc[~complete.complete_request_history, 'symbol'].unique())
    controls = sorted(set(complete.symbol)-set(incomplete))
    controls = [controls[round(i*(len(controls)-1)/9)] for i in range(10)]
    symbols = sorted(set(incomplete+controls))
    output = Path(output) if output else ROOT/'experiments/m2'/c['name']/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True, exist_ok=True)
    if (output/'config.json').exists():
        assert json.loads((output/'config.json').read_text(encoding='utf-8')) == c
    write(output/'config.json', c)
    write(output/'selection.json', {'incomplete_symbols': incomplete, 'controls': controls, 'symbols': symbols})
    for name in ['configs/factors/m2_alternate_history.json', 'scripts/collect_alternate_history.py']:
        target = output/'source'/name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT/name,target)
    state = {'status': 'RUNNING', 'run_id': output.name, 'network_calls': 0, 'cached_pages': 0}
    write(output/'status.json',state)
    print('ALTERNATE_RUN '+str(output), flush=True)
    manifest = []
    cache = ROOT/'data/raw/eastmoney_m2'; cache.mkdir(parents=True,exist_ok=True)
    last_request = 0
    try:
        with requests.Session() as session:
            for offset in range(0,len(symbols),c['network']['batch_symbols']):
                group = symbols[offset:offset+c['network']['batch_symbols']]
                codes = [s[2:]+'.'+s[:2] for s in group]
                code_filter = ','.join('"'+s+'"' for s in codes)
                for table in c['tables']:
                    page = 1; pages = 1; accumulated = []; expected = None
                    while page <= pages:
                        params = {'type': 'RPT_F10_FINANCE_'+table, 'sty': 'APP_F10_GINCOME' if table=='GINCOME' else 'ALL',
                                  'filter': f"(SECUCODE in ({code_filter}))(REPORT_DATE>='{c['source_period'][0]}')(REPORT_DATE<='{c['source_period'][1]}')(NOTICE_DATE<='{c['data_period'][1]}')",
                                  'p': str(page), 'ps': str(c['network']['page_size']), 'sr': '-1,-1',
                                  'st': 'REPORT_DATE,SECUCODE', 'source': 'HSF10', 'client': 'PC'}
                        key = hashlib.sha256(json.dumps(params,sort_keys=True).encode()).hexdigest()
                        path = cache/(key+'.json')
                        if path.exists():
                            saved = json.loads(path.read_text(encoding='utf-8'))
                            assert saved['params']==params and saved['body_sha256']==body_hash(saved['body'])
                            body = saved['body']; state['cached_pages'] += 1
                        else:
                            time.sleep(max(0, c['network']['minimum_interval_seconds']-(time.monotonic()-last_request)))
                            last_request = time.monotonic()
                            response = session.get(c['network']['endpoint'], params=params, timeout=tuple(c['network']['timeout_seconds']))
                            state['network_calls'] += 1
                            response.raise_for_status()
                            body = response.json()
                            unpack(body)  # Do not cache source errors as missing financial data.
                            saved = {'endpoint': c['network']['endpoint'], 'params': params, 'body': body,
                                     'body_sha256': body_hash(body), 'retrieved_at': datetime.now(timezone.utc).isoformat()}
                            write(path,saved)
                        rows, page_count, total = unpack(body)
                        if expected is None:
                            expected=total; pages=max(1,page_count)
                        assert total==expected and max(1,page_count)==pages, 'Pagination drift'
                        for row in rows:
                            assert row['SECUCODE'] in codes
                            assert c['source_period'][0] <= row['REPORT_DATE'][:10] <= c['source_period'][1]
                            assert row['REPORT_DATE'][:10] <= row['NOTICE_DATE'][:10] <= c['data_period'][1]
                        accumulated.extend(rows)
                        manifest.append({'path':str(path.relative_to(ROOT)), 'sha256':digest(path), 'table':table,
                                         'symbols':group, 'page':page, 'pages':pages, 'rows':len(rows), 'total':total})
                        page += 1
                    assert len(accumulated)==expected
                    assert len({(r['SECUCODE'],r['REPORT_DATE']) for r in accumulated})==len(accumulated), 'Ambiguous report versions'
                state.update(symbols_completed=min(offset+len(group),len(symbols)), symbols_total=len(symbols), pages_completed=len(manifest))
                write(output/'requests.json',manifest);write(output/'status.json',state)
                print(f"COLLECT {state['symbols_completed']}/{len(symbols)} symbols; {len(manifest)} pages",flush=True)
        write(output/'requests.json',manifest)
        state.update(status='COLLECTED',source_rows=sum(x['rows'] for x in manifest))
        write(output/'status.json',state)
        print('COLLECTED '+str(output),flush=True)
    except BaseException as exc:
        write(output/'requests.json',manifest)
        state.update(status='FAIL',error=str(exc));write(output/'status.json',state)
        raise


if __name__=='__main__':
    with FileLock(str(ROOT/'data/m2_alternate_history.lock'),timeout=0):
        run(sys.argv[1] if len(sys.argv)>1 else None)
