import pytest
from quant_research.m2.history_completion import industry_key,financial_key


def test_legacy_categories_remain_distinct_without_future_crosswalk():
    assert industry_key('J66货币金融服务')=='J66'
    old=industry_key('金融保险业-银行业')
    assert old=='LEGACY:金融保险业-银行业' and financial_key(old)
    assert financial_key('J69') and not financial_key('C36')
    assert industry_key('制造业-交通运输设备制造业')!='C36'
    assert industry_key('') is None
    with pytest.raises(ValueError):industry_key('\ufffd坏数据')


def test_explicit_provider_denial_stops_before_network(tmp_path,monkeypatch):
    from quant_research.m2 import history_completion
    (tmp_path/'data').mkdir()
    (tmp_path/'data/baostock_access_restriction.json').write_text('{"active":true}')
    monkeypatch.setattr(history_completion,'_run',lambda _:pytest.fail('network collection must not start'))
    with pytest.raises(RuntimeError,match='explicitly denied'):history_completion.run(tmp_path)
