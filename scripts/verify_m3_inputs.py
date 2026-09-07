"""Verify the common daily/PIT contract against the existing sealed inputs."""
import json
from pathlib import Path
import sys

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from quant_research.factors.data import load_factor_data
from quant_research.factors.engine import verify_baseline,audit_causality
from quant_research.factors.expressions import Expression,DAILY_FIELDS,PIT_FIELDS
from quant_research.m3.data_contract import freeze_binding,read_contract,attach_fields


def main():
    binding=freeze_binding(ROOT,DAILY_FIELDS|PIT_FIELDS)
    contract=read_contract(ROOT,binding,DAILY_FIELDS|PIT_FIELDS)
    baseline=json.loads((ROOT/'configs/experiments/baostock_alpha158.json').read_text())
    verify_baseline(ROOT,'BL-CN-CSI300-A158-LGBM-001')
    market=load_factor_data(ROOT,baseline)
    loaded,report=attach_fields(ROOT,market,contract,DAILY_FIELDS|PIT_FIELDS)
    for field in DAILY_FIELDS:
        pd.testing.assert_frame_equal(market.fields[field],loaded.fields[field],check_exact=True)
    checks=[]
    for field in sorted(PIT_FIELDS):
        meta=contract['fields'][field]
        original=pd.read_parquet(ROOT/meta['panel']['path'])
        actual=loaded.fields[field]
        pd.testing.assert_frame_equal(actual.loc[original.index,original.columns],original,check_exact=True)
        assert actual.loc[~actual.index.isin(original.index)].isna().all().all()
        causal=audit_causality(Expression(field),loaded.fields,loaded.membership,'2014-12-31')
        checks.append({'field':field,'source_cells':int(original.size),'reindexed_cells':int(actual.size),
                       'nonmissing':int(actual.notna().to_numpy().sum()),'causality':causal})
    out=ROOT/'experiments/m3_data_contract_v1';out.mkdir(exist_ok=True)
    result={'status':'PASS','binding':binding,'fields':checks,'daily_fields_unchanged':sorted(DAILY_FIELDS),
        'protected_accessed':False,'source_verification':'Existing independent raw/PIT source verifications are hash-pinned; this run checks exact panel transfer and cutoff invariance, not vendor revision truth.'}
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'input_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
