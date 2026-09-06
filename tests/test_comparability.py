import pandas as pd
from quant_research.m2.comparability import sector_codes, modal_period_mask


def test_sector_codes_do_not_depend_on_corrupted_display_names():
    f=pd.DataFrame([['J66乱码','J68Insurance','C15Beverage',None,'unknown']])
    codes=sector_codes(f)
    assert codes.iloc[0,:3].tolist()==['J66','J68','C15']
    assert codes.iloc[0,3:].isna().all()


def test_modal_period_uses_only_eligible_rows_and_newest_tie_break():
    periods=pd.DataFrame([pd.to_datetime(['2014-12-31','2015-03-31','2014-12-31'])])
    eligible=pd.DataFrame([[True,True,False]])
    mask,chosen=modal_period_mask(periods,eligible)
    assert chosen.iloc[0]==pd.Timestamp('2015-03-31')
    assert mask.iloc[0].tolist()==[False,True,False]


def test_modal_period_has_no_future_dependency():
    periods=pd.DataFrame([pd.to_datetime(['2014-12-31','2015-03-31']),pd.to_datetime(['2015-03-31','2015-03-31'])])
    eligible=periods.notna()
    mask,_=modal_period_mask(periods,eligible)
    prefix,_=modal_period_mask(periods.iloc[:1],eligible.iloc[:1])
    pd.testing.assert_frame_equal(mask.iloc[:1],prefix)
