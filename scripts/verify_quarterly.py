"""Independent direct event selection check; does not call production asof join."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd


def verify(folder):
    folder = Path(folder)
    c = json.loads((folder/'config.json').read_text())
    manifest = json.loads((folder/'data_manifest.json').read_text())
    for name, expected in manifest.items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'artifact changed: {name}')
    requests = json.loads((folder/'requests.json').read_text())
    raw_groups = {}
    for request in requests:
        if request['params']['year'] >= 2021:
            raise ValueError('protected year request')
        if hashlib.sha256(Path(request['path']).read_bytes()).hexdigest() != request['sha256']:
            raise ValueError('raw response changed')
        key = (request['params']['code'].replace('.', '').upper(), request['method'])
        raw_groups.setdefault(key, []).append(pd.read_csv(request['path'], dtype=str, keep_default_na=False))
    members = pd.read_parquet(folder/'membership.parquet')
    fields = [f for fs in c['fields'].values() for f in fs]
    panels = {f: pd.read_parquet(folder/(f+'.parquet')) for f in fields}
    cells = 0
    for symbol in members.columns:
        for method, fs in c['fields'].items():
            events = pd.read_parquet(folder/'events'/f'{symbol}_{method}.parquet')
            raw = pd.concat(raw_groups[(symbol,method)], ignore_index=True)
            if not raw.empty:
                raw['pubDate'] = pd.to_datetime(raw.pubDate, errors='raise')
                raw['statDate'] = pd.to_datetime(raw.statDate, errors='raise')
                raw = raw.loc[raw.pubDate.le(pd.Timestamp(c['end'])), ['code','pubDate','statDate']+fs]
                raw[fs] = raw[fs].replace('',np.nan).apply(pd.to_numeric,errors='raise')
                pd.testing.assert_frame_equal(events.reset_index(drop=True),raw.reset_index(drop=True),check_dtype=False)
            expected = pd.DataFrame(np.nan,index=members.index,columns=fs)
            for day in members.index[members[symbol]]:
                # Explicit filtration and fiscal-period precedence, independent of merge_asof.
                eligible = events[events.pubDate.lt(day)]
                if eligible.empty:
                    continue
                period = eligible.statDate.max()
                latest = eligible.loc[eligible.statDate.eq(period)].sort_values('pubDate').iloc[-1]
                if ((day-latest.pubDate).days <= c['max_publication_age_days']
                        and (day-latest.statDate).days <= c['max_period_age_days']):
                    expected.loc[day,fs] = latest[fs].to_numpy(dtype=float)
            for f in fs:
                np.testing.assert_allclose(panels[f][symbol],expected[f],rtol=0,atol=0,equal_nan=True)
                cells += len(expected)
    result = {'status':'PASS','checked_panel_cells':cells,'raw_request_hashes_verified':len(requests),
              'artifact_hashes_verified':len(manifest),'method':'direct per-date eligible-event selection; production merge_asof not used',
              'checks':['strict publication lag','latest fiscal precedence','publication and fiscal staleness','date-specific membership','missing field preservation']}
    (folder/'independent_verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result),flush=True)


if __name__ == '__main__':
    verify(sys.argv[1])
