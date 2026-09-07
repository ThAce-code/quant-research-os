from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from quant_research.r1.models import folds,schedule,variants
from quant_research.r1.workflow import protocol,select_representatives,reserve

ROOT=Path(__file__).resolve().parents[1]


def test_twenty_day_fold_purge_and_schedule():
    c,_=protocol(ROOT);calendar=pd.bdate_range('2007-09-01','2020-08-05')
    for fold in folds(calendar,c):
        for part in ['train','valid']:
            endpoint=calendar.get_loc(fold[part][1])
            assert calendar[endpoint+21]==fold[part+'_label_exit']
        assert fold['train_label_exit']<fold['valid'][0]
        assert fold['valid_label_exit']<fold['test'][0]
    dates,trades,signals=schedule(calendar,c)
    assert trades.equals(dates[::5])
    np.testing.assert_array_equal(calendar.get_indexer(trades)-calendar.get_indexer(signals),1)


def test_fixed_order_weak_positive_selection_and_all_subsets():
    c,items=protocol(ROOT)
    rows={i['name']:{'coverage':{'2015':.8,'2016':.8},'years':{'2015':{'rank_ic':.001},'2016':{'rank_ic':.001}},'q':1.} for i in items}
    rows[items[1]['name']]['years']['2015']['rank_ic']=.5
    selected=select_representatives(rows,c,items)
    assert selected==[items[i]['name'] for i in [0,2,4]]
    assert len(variants(selected))==8
    rows[items[0]['name']]['coverage']['2016']=.69
    assert select_representatives(rows,c,items)[0]==items[1]['name']


def test_campaign_ticket_cannot_be_reused(tmp_path):
    c,_=protocol(ROOT)
    reserve(tmp_path,c,'screen',tmp_path/'first')
    with pytest.raises(FileExistsError):reserve(tmp_path,c,'screen',tmp_path/'second')
