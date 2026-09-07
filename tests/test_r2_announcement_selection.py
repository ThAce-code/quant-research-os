import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_yearless_correction_is_kept_for_body_verification():
    choose=load('backfill_r2_announcements').candidate_title
    assert choose('第一季度业绩预告修正公告',2016)
    assert choose('2014年度业绩快报暨2015年第一季度业绩预告',2015)
    assert not choose('2014年第一季度业绩预告',2015)
    assert not choose('2015年第一季度报告',2015)


def test_embedded_reports_not_audits_or_investor_meetings():
    choose=load('supplement_r2_announcements').relevant_report
    assert choose('2014年年度报告摘要',2015)
    assert choose('2015年一季度业绩预告',2015)
    assert not choose('2014年年度审计报告',2015)
    assert not choose('关于举行2014年度业绩网上说明会的通知',2015)
    assert not choose('2014年年度报告（英文版）',2015)
