import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_research.m3.increment import matched_features, fit_predict, survivors, run
from quant_research.factors.registry import FactorRegistry

ROOT = Path(__file__).resolve().parents[1]


def test_common_rows_do_not_depend_on_future_label_availability():
    ix = pd.MultiIndex.from_product([pd.date_range('2010-01-01', periods=2), ['A','B']],
                                    names=['datetime','instrument'])
    alpha = pd.DataFrame(1., index=ix, columns=[f'A{i}' for i in range(158)])
    one = pd.DataFrame([[1., np.nan],[2.,3.]], index=ix.levels[0], columns=['A','B'])
    two = pd.DataFrame([[2.,4.],[np.nan,5.]], index=ix.levels[0], columns=['A','B'])
    x, y = matched_features(alpha, {'ONE':one,'TWO':two}, pd.Series(np.nan, index=ix))
    assert list(x.index) == [ix[0], ix[3]]
    assert y.isna().all() and len(x.columns) == 160


def test_real_lightgbm_fits_share_samples_and_purge_boundaries(tmp_path):
    calendar = pd.bdate_range('2008-01-01','2010-02-01')
    ix = pd.MultiIndex.from_product([calendar,['A','B','C']], names=['datetime','instrument'])
    rng = np.random.default_rng(10)
    x = pd.DataFrame(rng.normal(size=(len(ix),159)), index=ix,
                     columns=[f'A{i}' for i in range(158)]+['NEW'])
    y = pd.Series(rng.normal(size=len(ix)), index=ix)
    c = {'fold_years':[2010], 'train_start':'2008-01-01',
         'evaluation_period':['2010-01-01','2010-02-01'],
         'variants':{'BASE':[],'ADD_NEW':['NEW']}, 'seed':42,
         'min_train_rows':20,'min_valid_rows':20,'num_boost_round':3,'early_stopping_rounds':2}
    pred = fit_predict(x,y,calendar,c,{'num_threads':1,'num_leaves':4},tmp_path)
    assert pred.notna().all().all() and pred.index.is_unique
    audit = pd.read_csv(tmp_path/'folds.csv')
    assert audit.train_rows.nunique() == audit.valid_rows.nunique() == audit.prediction_rows.nunique() == 1
    assert set(audit.features) == {158,159}
    train_end = pd.Timestamp(audit.train_end.iloc[0])
    assert calendar[calendar.year==2008][-3] == train_end
    assert pred.index.get_level_values('datetime').max() < pd.Timestamp('2021-01-01')


def test_rejection_router_never_loads_market(tmp_path, monkeypatch):
    import quant_research.m3.increment as module
    monkeypatch.setattr(module, 'survivors', lambda *args: ([], {'fixed':'batch'}))
    def forbidden(*args, **kwargs):
        raise AssertionError('rejected candidates reached model or market loader')
    monkeypatch.setattr(module, '_evaluate', forbidden)
    monkeypatch.setattr(module, 'load_factor_data', forbidden)
    (tmp_path/'data').mkdir()
    for name in ['configs/m3/increment.json','scripts/run_m3_increment.py']:
        p=tmp_path/name; p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
    result = run(tmp_path, tmp_path/'screen')
    status = json.loads((result/'status.json').read_text())
    assert status['decision']=='NO_ENTRY' and status['fits']==0


def test_fabricated_screen_status_cannot_promote_reject(tmp_path):
    from quant_research.m3.candidates import admit_batch, identity
    import hashlib
    payload=json.loads((ROOT/'configs/m3/paper_pilot.json').read_text())
    c=json.loads((ROOT/'configs/factors/m2_family_screen.json').read_text())
    payload['screen_protocol_sha256']=hashlib.sha256(json.dumps(c).encode()).hexdigest()
    h=admit_batch(payload)[0]
    registry=FactorRegistry(tmp_path/'r.sqlite')
    from dataclasses import asdict
    registry.register(h.factor().factor_id,asdict(h.factor()))
    registry.record(tmp_path.name,h.factor().factor_id,{'status':'REJECT','batch_sha256':identity(payload)})
    files={'batch.json':payload,'screen_protocol.json':c,'results.json':{h.name:{'status':'FORWARD'}}}
    for name,value in files.items():(tmp_path/name).write_text(json.dumps(value))
    (tmp_path/'status.json').write_text('{"status":"PASS"}')
    (tmp_path/'artifact_hashes.json').write_text(json.dumps({n:hashlib.sha256((tmp_path/n).read_bytes()).hexdigest() for n in files}))
    with pytest.raises(ValueError,match='registry lineage'):
        survivors(tmp_path,registry)
