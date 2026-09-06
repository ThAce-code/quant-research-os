"""Direct event eligibility selection, independent of production merge_asof."""
import sys
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd


def direct_cash(events,dates,member):
    out=np.full(len(dates),np.nan)
    if events.empty:return out
    e=events.sort_values(['statDate','pubDate'])
    publication=pd.to_datetime(e.pubDate).to_numpy(dtype='datetime64[ns]')
    fiscal=pd.to_datetime(e.statDate).to_numpy(dtype='datetime64[ns]')
    days=dates.to_numpy(dtype='datetime64[ns]')
    # Latest fiscal period, then its latest published event, among strictly earlier events.
    selected=np.where(publication[None,:]<days[:,None],np.arange(len(e))[None,:],-1).max(axis=1)
    index=np.maximum(selected,0)
    good=(selected>=0)&member
    good &= ((days-publication[index])/np.timedelta64(1,'D')<=400)
    good &= ((days-fiscal[index])/np.timedelta64(1,'D')<=550)
    out[good]=e.CFOToOR.to_numpy(dtype=float)[index[good]]
    return out


def main(folder):
    manifest=json.loads((folder/'artifact_hashes.json').read_text())
    for n,h in manifest.items():
        if hashlib.sha256((folder/n).read_bytes()).hexdigest()!=h:raise ValueError(f'artifact changed: {n}')
    requests=json.loads((folder/'requests.json').read_text())
    for r in requests:
        p=r['params']
        if p.get('year',0)>2020 or any(str(p.get(k,''))[:4]>'2020' for k in ['end_date','date'] if p.get(k)):
            raise ValueError('protected period request')
        if hashlib.sha256(Path(r['path']).read_bytes()).hexdigest()!=r['sha256']:raise ValueError('raw hash mismatch')
    m=pd.read_parquet(folder/'membership.parquet');cash=pd.read_parquet(folder/'CFOToOR.parquet')
    cells=0
    for i,symbol in enumerate(m.columns):
        e=pd.read_parquet(folder/'events'/(symbol+'.parquet'))
        want=direct_cash(e,m.index,m[symbol].to_numpy())
        np.testing.assert_allclose(cash[symbol],want,rtol=0,atol=0,equal_nan=True)
        cells+=len(want)
        if i%100==0:print(f'VERIFY {i+1}/{len(m.columns)}',flush=True)
    result={'status':'PASS','cashflow_cells_checked':cells,'raw_request_hashes_checked':len(requests),
            'artifact_hashes_checked':len(manifest),'method':'direct fiscal-priority eligibility selection, not merge_asof',
            'checks':['publication strictly earlier','latest fiscal-period priority','400/550-day age limits','membership','missing values']}
    (folder/'independent_verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result),flush=True)


if __name__=='__main__':main(Path(sys.argv[1]))
