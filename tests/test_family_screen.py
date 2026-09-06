from quant_research.m2.family_screen import screen_pass, checked_artifact
import pytest


def test_screen_requires_each_year_coverage_and_direction():
    c={'min_coverage':.7,'min_rank_ic':.01,'max_q':.1}
    stats={'rank_ic':.03}; yearly={'2015':{'rank_ic':.02},'2016':{'rank_ic':.04}}
    assert screen_pass({'2015':.8,'2016':.8},stats,yearly,.05,c)
    assert not screen_pass({'2015':.69,'2016':.9},stats,yearly,.05,c)
    yearly['2015']['rank_ic']=-.01
    assert not screen_pass({'2015':.8,'2016':.8},stats,yearly,.05,c)


def test_input_drift_is_rejected(tmp_path):
    (tmp_path/'x').write_text('changed')
    with pytest.raises(ValueError,match='input artifact changed'):
        checked_artifact(tmp_path,'x',{'x':'wrong'})
