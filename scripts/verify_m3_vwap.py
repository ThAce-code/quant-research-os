"""Check VWAP from sealed raw bars and preserve every pre-existing field."""
import json
from pathlib import Path
import subprocess
import sys
import types

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import numpy as np
import pandas as pd
from quant_research.factors.data import load_factor_data
from quant_research.factors.engine import verify_baseline
from quant_research.m3.pipeline import sha


def main():
    revision='af1f16d2795c748369707608c93fb7d212f31f5a'
    original=subprocess.check_output(['git','-C',str(ROOT),'show',revision+':src/quant_research/factors/data.py'])
    legacy=types.ModuleType('quant_research.factors._before_vwap')
    sys.modules[legacy.__name__]=legacy
    exec(compile(original,'frozen_pre_vwap_data.py','exec'),legacy.__dict__)
    config=json.loads((ROOT/'configs/experiments/baostock_alpha158.json').read_text())
    verify_baseline(ROOT,'BL-CN-CSI300-A158-LGBM-001')
    old=legacy.load_factor_data(ROOT,config);current=load_factor_data(ROOT,config)
    for name,field in old.fields.items():pd.testing.assert_frame_equal(field,current.fields[name],check_exact=True)
    for name in ['membership','tradable','execution_eligible']:
        pd.testing.assert_frame_equal(getattr(old,name),getattr(current,name),check_exact=True)
    pd.testing.assert_series_equal(old.benchmark,current.benchmark,check_exact=True)
    canonical=ROOT/'data/canonical'/config['name'];checked=0;finite=0
    for symbol in current.membership.columns:
        raw=pd.read_parquet(canonical/f'{symbol}.parquet').set_index('datetime')
        expected=(raw['amount']*raw['factor']/raw['volume']).where(
            (raw['volume']>0)&(raw['close']>0)&~raw['is_suspended']).reindex(current.membership.index)
        actual=current.fields['vwap'][symbol]
        np.testing.assert_allclose(actual,expected,rtol=1e-14,equal_nan=True)
        checked+=len(actual);finite+=int(actual.notna().sum())
    output=ROOT/'experiments/m3_searchers/vwap_verification.json'
    output.write_text(json.dumps({'status':'PASS','previous_revision':revision,
        'unchanged_fields':list(old.fields),'unchanged_universe_execution_benchmark':True,
        'vwap_cells_checked':checked,'vwap_finite_cells':finite,
        'canonical_manifest_sha256':sha(canonical/'manifest.json'),'verifier_sha256':sha(__file__),
        'protected_accessed':False},indent=2)+'\n')
    print(output.read_text())


if __name__=='__main__':main()
