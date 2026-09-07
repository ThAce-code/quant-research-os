import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('extract_r2',ROOT/'scripts/extract_r2_announcements.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def template(year,amount='102,994.98至109,861.31',growth='50.00%至60.00%'):
    prefix=f'{year}年1-3月归属于上市公司股东的净利润'
    return prefix+'变动幅度'+growth+prefix+'区间（万元）'+amount


def test_explicit_current_period_and_currency_unit():
    value=module.annual_q1_fields(template(2015),2015)
    assert abs(value['parent_profit_lower_yuan']-1029949800)<1e-5
    assert value['yoy_lower_percent']==50
    assert module.annual_q1_fields(template(2014),2015) is None


def test_no_inferred_or_ambiguous_financial_values():
    assert module.annual_q1_fields('预计净利润同比增长50%，详情见原文',2015) is None
    assert module.annual_q1_fields(template(2015)+template(2015,amount='1至2'),2015) is None
    result=module.annual_q1_fields(template(2015,amount='-300至-200',growth='-70%至-50%'),2015)
    assert result['parent_profit_lower_yuan']==-3000000 and result['yoy_lower_percent']==-70


def test_next_row_year_must_not_join_upper_amount():
    for amount,expected in [('10,000至15,000',150000000),
                            ('102,994.98至109,861.31',1098613100),
                            ('-300至-200',-2000000)]:
        text=template(2015,amount=amount)+' \n2014 年1-3月归属于上市公司股东的净利润（万元） 1,000'
        assert module.annual_q1_fields(text,2015)['parent_profit_upper_yuan']==expected
