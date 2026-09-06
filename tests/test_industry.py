from quant_research.m2.industry import industry_key,financial_key


def test_transition_text_financials_are_excluded_without_mapping_other_categories():
    for value in ['金融保险业-银行业','金融业-货币金融服务','金融业','J66货币金融服务','J68资本市场服务']:
        assert financial_key(industry_key(value)),value
    for value in ['制造业-交通运输设备制造业','信息技术业-金融软件','C36汽车制造业','']:
        assert not financial_key(industry_key(value)),value
