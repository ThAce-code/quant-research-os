"""Small, causal expression language. Positive Ref lags always mean the past."""
import ast
from dataclasses import asdict, dataclass
import hashlib
import json
import re

import numpy as np
import pandas as pd


FIELDS = {'open', 'high', 'low', 'close', 'volume', 'turnover', 'returns', 'vwap'}
WINDOW = {'Ref', 'Mean', 'Std', 'Min', 'Max', 'TsRank', 'Delta'}
BINARY = {'Add', 'Sub', 'Mul', 'Div'}
UNARY = {'Abs', 'Log', 'Rank'}


class Expression:
    def __init__(self, text):
        try:
            self.tree = ast.parse(text, mode='eval').body
        except (SyntaxError, TypeError) as error:
            raise ValueError('invalid factor expression') from error
        if len(list(ast.walk(self.tree))) > 128:
            raise ValueError('expression too large')
        self.lookback = self._check(self.tree)
        if self.lookback > 512:
            raise ValueError('lookback exceeds 512 trading days')
        self.text = text

    def _check(self, node):
        if isinstance(node, ast.Name) and node.id in FIELDS:
            return 1 if node.id == 'returns' else 0
        if isinstance(node, ast.Constant) and type(node.value) in (int, float) and np.isfinite(node.value):
            return 0
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return self._check(node.operand)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            return max(self._check(node.left), self._check(node.right))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            name, args = node.func.id, node.args
            if name in WINDOW and len(args) == 2:
                lag = args[1]
                if not isinstance(lag, ast.Constant) or type(lag.value) is not int:
                    raise ValueError('window must be a literal integer; future lags are forbidden')
                if not (0 if name in {'Ref', 'Delta'} else 1) <= lag.value <= 252:
                    raise ValueError('invalid historical window')
                return self._check(args[0]) + (lag.value if name in {'Ref', 'Delta'} else lag.value - 1)
            if (name in BINARY and len(args) == 2) or (name in UNARY and len(args) == 1):
                return max(self._check(a) for a in args)
        raise ValueError('unsupported expression node, field or operation')

    def evaluate(self, fields, membership=None):
        def binary(op, a, b):
            if op == 'Add': return a + b
            if op == 'Sub': return a - b
            if op == 'Mul': return a * b
            with np.errstate(divide='ignore', invalid='ignore'):
                return a / b

        def run(node):
            if isinstance(node, ast.Name): return fields[node.id]
            if isinstance(node, ast.Constant): return node.value
            if isinstance(node, ast.UnaryOp):
                return -run(node.operand) if isinstance(node.op, ast.USub) else run(node.operand)
            if isinstance(node, ast.BinOp):
                name = {ast.Add: 'Add', ast.Sub: 'Sub', ast.Mult: 'Mul', ast.Div: 'Div'}[type(node.op)]
                return binary(name, run(node.left), run(node.right))
            name = node.func.id
            args = [run(a) for a in node.args]
            if name in BINARY: return binary(name, *args)
            x = args[0]
            if not isinstance(x, pd.DataFrame):
                raise ValueError(f'{name} requires a panel')
            if name == 'Abs': return x.abs()
            if name == 'Log': return np.log(x.where(x > 0))
            if name == 'Rank':
                return (x.where(membership) if membership is not None else x).rank(axis=1, pct=True)
            w = args[1]
            if name == 'Ref': return x.shift(w)
            if name == 'Delta': return x - x.shift(w)
            rolling = x.rolling(w, min_periods=w)
            if name == 'Mean': return rolling.mean()
            if name == 'Std': return rolling.std(ddof=1)
            if name == 'Min': return rolling.min()
            if name == 'Max': return rolling.max()
            return rolling.rank(pct=True)

        try:
            result = run(self.tree)
        except (KeyError, ZeroDivisionError) as error:
            raise ValueError(f'expression cannot be evaluated: {error}') from error
        if not isinstance(result, pd.DataFrame):
            raise ValueError('factor must produce a date-by-instrument panel')
        return result.replace([np.inf, -np.inf], np.nan)


@dataclass(frozen=True)
class FactorDefinition:
    name: str
    family: str
    expression: str
    hypothesis: str
    direction: int = 1
    source: str = 'human_baseline'
    paper: str | None = None
    generator: str = 'human'
    version: int = 1

    def __post_init__(self):
        if not re.fullmatch('[A-Z][A-Z0-9_]{0,63}', self.name) or self.direction not in (-1, 1):
            raise ValueError('invalid factor name or fixed direction')
        if not self.family or not self.hypothesis or type(self.version) is not int or self.version < 1:
            raise ValueError('factor metadata is incomplete')
        Expression(self.expression)

    @property
    def factor_id(self):
        payload = json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)
        return 'F_' + hashlib.sha256(payload.encode()).hexdigest()[:16]
