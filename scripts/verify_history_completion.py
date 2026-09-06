"""Independently select eligible fiscal events for all five completed fields."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
import pandas as pd


def expected(events,dates,member,fields):
    result=np.full((len(dates),len(fields)),np.nan)
    if events.empty:return result
    e=events.sort_values(['statDate','pubDate'])
    pub=pd.to_datetime(e.pubDate).to_numpy(dtype='datetime64[ns]')
    stat=pd.to_datetime(e.statDate).to_numpy(dtype='datetime64[ns]')
    days=dates.to_numpy(dtype='datetime64[ns]')
    chosen=np.where(pub[None,:]<days[:,None],np.arange(len(e))[None,:],-1).max(axis=1)
    safe=np.maximum(chosen,0)
    good=(chosen>=0)&member&((days-pub[safe])/np.timedelta64(1,'D')<=400)&((days-stat[safe])/np.timedelta64(1,'D')<=550)
    result[good]=e[fields].to_numpy(float)[safe[good]]
    return result


def main(folder):
    assert json.loads((folder/'status.json').read_text())['status']=='PASS'
    config=json.loads((folder/'config.json').read_text());manifest=json.loads((folder/'artifact_hashes.json').read_text())
    for n,h in manifest.items():assert hashlib.sha256((folder/n).read_bytes()).hexdigest()==h,n
    requests=json.loads((folder/'requests.json').read_text())
    for i,r in enumerate(requests):
        assert r['params']['year']<=2020 and r['method'] in config['fields']
        assert hashlib.sha256(Path(r['path']).read_bytes()).hexdigest()==r['sha256']
        if i%5000==0:print(f'RAW {i}/{len(requests)}',flush=True)
    member=pd.read_parquet(folder/'membership.parquet');cells=0
    for method,fields in config['fields'].items():
        panels={f:pd.read_parquet(folder/f'{f}.parquet') for f in fields}
        for i,symbol in enumerate(member):
            events=pd.read_parquet(folder/'events'/f'{symbol}_{method}.parquet')
            want=expected(events,member.index,member[symbol].to_numpy(),fields)
            got=np.column_stack([panels[f][symbol] for f in fields])
            np.testing.assert_allclose(got,want,rtol=0,atol=0,equal_nan=True);cells+=got.size
            if i%100==0:print(f'PANELS {method} {i}/{len(member.columns)}',flush=True)
    result={'status':'PASS','cells_checked':cells,'raw_requests_checked':len(requests),'artifact_hashes_checked':len(manifest),
            'no_2021_plus_requests':True,'method':'independent fiscal-priority NumPy event eligibility; exact NaN-preserving comparison'}
    (folder/'independent_verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result),flush=True)


if __name__=='__main__':main(Path(sys.argv[1]))
