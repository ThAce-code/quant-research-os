from quant_research.m2.supplementary_run import decision


def test_partial_year_is_not_a_full_year_vote_and_weak_ic_does_not_block_model_queue():
    c={'min_year_coverage':.7,'min_rank_ic':.01,'max_q':.1,'full_years':[2015,2016,2017,2018,2019],'positive_full_years_required':4}
    years={str(y):{'rank_ic':.02 if y!=2019 else -.01} for y in [2015,2016,2017,2018,2019,2020]}
    r=decision({'2015':.8,'2020':.8},{'rank_ic':.02},years,.05,c)
    assert r['screen_status']=='IC_SCREEN_PASS' and r['positive_full_years']==4
    r=decision({'2015':.8,'2020':.8},{'rank_ic':-.02},years,.5,c)
    assert r['screen_status']=='IC_SCREEN_REJECT' and r['model_queue']=='DATA_READY_FOR_BOUNDED_MODEL_PROTOCOL'
    assert decision({'2015':.69},{'rank_ic':.02},years,.05,c)['model_queue']=='DATA_COVERAGE_BLOCKED'
