import json
from pathlib import Path
import pandas as pd
from quant_research.m2.rolling import folds,gate


def config():return json.loads((Path(__file__).resolve().parents[1]/'configs/factors/m2_rolling.json').read_text())


def test_fold_label_reach_stays_before_next_segment():
    c=config();calendar=pd.bdate_range('2008-01-01','2020-08-05')
    parts=list(folds(calendar,c));assert len(parts)==6
    for f in parts:
        assert calendar[calendar.get_loc(f['train'][1])+2]<f['valid'][0]
        assert calendar[calendar.get_loc(f['valid'][1])+2]<f['test'][0]
    assert parts[-1]['test'][1]==pd.Timestamp('2020-07-31')


def test_gate_requires_joint_cost_and_signal_evidence():
    c=config();r={'mean':.003};n={'mean':.03/238,'low':.00001};years={str(y):.02 for y in range(2015,2020)}
    assert gate(r,.05,n,years,c)['decision']=='GO'
    assert gate(r,.11,n,years,c)['decision']=='NO_GO'
    assert gate(r,.05,{**n,'low':0},years,c)['decision']=='NO_GO'
    assert gate(r,.05,n,{'2015':1,'2016':1,'2020':1},c)['decision']=='NO_GO'
