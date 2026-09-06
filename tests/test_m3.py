import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_research.m3.candidates import admit_batch, ResearchHypothesis
from quant_research.m3.pipeline import research_firewall
from quant_research.factors.expressions import Expression

ROOT = Path(__file__).resolve().parents[1]


def batch():
    return json.loads((ROOT/'configs/m3/paper_pilot.json').read_text())


def test_exact_formula_mapping_against_hand_values():
    candidates = admit_batch(batch())
    fields = {name: pd.DataFrame([values]) for name, values in {
        'open': [10., 20., 5.], 'close': [11., 18., 5.],
        'high': [12., 21., 5.], 'low': [9., 17., 5.]}.items()}
    np.testing.assert_allclose(Expression(candidates[0].expression).evaluate(fields),
                               [np.log([1.1, .9, 1.])])
    np.testing.assert_allclose(Expression(candidates[1].expression).evaluate(fields),
                               [[1/3.001, -2/4.001, 0.]])


@pytest.mark.parametrize('change', [
    {'expression': 'Ref(close,-1)'}, {'direction': True}, {'direction': 0},
    {'source_type': 'PAPER_EXACT'}, {'source_type': 'UNKNOWN'},
    {'direction_evidence': ''}, {'input_fields': {'close': 'price'}},
    {'signal_timing': 'same_day_close'}, {'source_locator': ''}])
def test_invalid_hypothesis_rejected(change):
    item = batch()['candidates'][0]
    with pytest.raises(ValueError):
        ResearchHypothesis(**{**item, **change})


def test_duplicate_expression_and_refinement_rejected():
    b = batch()
    duplicate = copy.deepcopy(b['candidates'][0]); duplicate['name'] = 'DIFFERENT_NAME'
    duplicate['expression'] = '(Log(close / open))'
    b['candidates'][1] = duplicate
    with pytest.raises(ValueError, match='duplicate normalized'):
        admit_batch(b)
    b = batch(); b['automatic_refinement'] = True
    with pytest.raises(ValueError): admit_batch(b)


def test_protected_data_rejected_before_evaluation():
    baseline = json.loads((ROOT/'configs/experiments/baostock_alpha158.json').read_text())
    screen = json.loads((ROOT/'configs/factors/m2_family_screen.json').read_text())
    research_firewall(baseline, screen)
    baseline['data_end'] = '2021-01-01'
    with pytest.raises(ValueError, match='protected'):
        research_firewall(baseline, screen)


def test_lineage_changes_when_evidence_changes():
    h = batch()['candidates'][0]
    first = ResearchHypothesis(**h)
    second = ResearchHypothesis(**{**h, 'source_locator': 'different location'})
    assert first.hypothesis_id != second.hypothesis_id
    assert first.expression_key == second.expression_key
