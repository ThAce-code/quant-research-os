"""Authoritative calculation metadata for newly generated hypotheses.

Models propose formulas and mechanisms. Field/operator units come from the
implementation, not a model's possibly incomplete description. The exact catalog
is frozen in the call request so response recovery cannot silently reinterpret it.
"""
import ast
from copy import deepcopy

from ..factors.expressions import Expression,FIELDS


FIELD_CATALOG={
    'open':'Canonical adjusted open price: raw open * adjustment factor; after close t.',
    'high':'Canonical adjusted daily high: raw high * adjustment factor; after close t.',
    'low':'Canonical adjusted daily low: raw low * adjustment factor; after close t.',
    'close':'Canonical adjusted close: raw close * adjustment factor; after close t.',
    'vwap':'Canonical CNY amount / raw shares * adjustment factor; after close t; zero volume or missing amount stays missing.',
    'volume':'Canonical raw shares / adjustment factor; after close t; suspended observations missing.',
    'turnover':'Canonical vendor percent turnover / 100; dimensionless, after close t.',
    'returns':'Canonical adjusted close / previous trading-day adjusted close - 1; NOT close/open - 1; after close t.',
    'pit_roe':'Unscaled vendor roeAvg reporting-period ratio; frozen source-specific publication/revision contract, missing/stale values retained.',
    'pit_net_margin':'Unscaled vendor npMargin reporting-period ratio; frozen source-specific publication/revision contract, missing/stale values retained.',
    'pit_earnings_growth':'Unscaled vendor YOYNI ratio; frozen source-specific publication/revision contract, missing/stale values retained.',
    'pit_asset_growth':'Unscaled vendor YOYAsset ratio; frozen source-specific publication/revision contract, missing/stale values retained.',
    'pit_equity_growth':'Unscaled vendor YOYEquity ratio; frozen source-specific publication/revision contract, missing/stale values retained.',
    'pit_cashflow_margin':'Unscaled vendor CFOToOR reporting-period ratio; frozen source-specific publication/revision contract, missing/stale values retained.'}
OPERATOR_CATALOG={
    'arithmetic':'Elementwise arithmetic; nonfinite final outputs become missing. No formula or direction change.',
    'Abs':'Elementwise absolute value.',
    'Log':'Natural logarithm; nonpositive operands become missing.',
    'Rank':'Cross-sectional percentile rank among historical members; average ties.',
    'Ref':'Positive integer lag in trading days means historical panel shift.',
    'Delta':'Current panel minus its historical panel shifted by the literal trading-day lag.',
    'Mean':'Trailing full-window arithmetic mean; incomplete windows missing.',
    'Std':'Trailing full-window sample standard deviation, ddof=1; incomplete windows missing.',
    'Min':'Trailing full-window minimum; incomplete windows missing.',
    'Max':'Trailing full-window maximum; incomplete windows missing.',
    'TsRank':'Trailing full-window percentile rank of the current observation; average ties.',
    'Add':'Elementwise addition.','Sub':'Elementwise subtraction.',
    'Mul':'Elementwise multiplication.','Div':'Elementwise division; nonfinite final outputs missing.'}


def catalog():return {'fields':deepcopy(FIELD_CATALOG),'operators':deepcopy(OPERATOR_CATALOG)}


def enrich(item,frozen_catalog):
    expression=Expression(item['expression'])
    names={n.id for n in ast.walk(expression.tree) if isinstance(n,ast.Name) and n.id in FIELDS}
    operators={n.func.id for n in ast.walk(expression.tree) if isinstance(n,ast.Call)}
    if any(isinstance(n,(ast.BinOp,ast.UnaryOp)) for n in ast.walk(expression.tree)):operators.add('arithmetic')
    if not names:raise ValueError('generated factor must reference observed fields')
    fields={n:frozen_catalog['fields'][n] for n in sorted(names)}
    semantics={n:frozen_catalog['operators'][n] for n in sorted(operators)} or {'identity':'Direct observed input panel.'}
    result={**item,'input_fields':fields,'operator_semantics':semantics}
    result['deviations']=[*item.get('deviations',[]),
        'Calculation metadata is derived from the exact DSL and frozen canonical catalog, not model-supplied field descriptions. Raw model declarations remain in the saved call response.',
        'Economic rationale is an unverified model hypothesis; evaluate the exact expression under canonical field definitions. The adapter does not establish that the rationale matches every formula term.']
    return result
