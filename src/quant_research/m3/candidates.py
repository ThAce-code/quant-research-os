"""RD-Agent-inspired hypothesis/task boundary, using the existing factor DSL."""
import ast
from dataclasses import asdict, dataclass
import hashlib
import json

from ..factors.expressions import Expression, FactorDefinition, FIELDS

SOURCE_TYPES = {'PAPER_EXACT', 'PAPER_RECONSTRUCTED', 'PAPER_INSPIRED',
                'LLM_GENERATED', 'HUMAN_GENERATED'}


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class ResearchHypothesis:
    name: str
    family: str
    hypothesis: str
    economic_rationale: str
    expression: str
    direction: int
    source_type: str
    source_url: str
    source_locator: str
    original_expression: str
    input_fields: dict
    operator_semantics: dict
    signal_timing: str
    direction_evidence: str
    deviations: list
    version: int = 1

    def __post_init__(self):
        for key, value in asdict(self).items():
            if key not in {'direction', 'version', 'deviations', 'input_fields', 'operator_semantics'}:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f'missing hypothesis evidence: {key}')
        if self.source_type not in SOURCE_TYPES:
            raise ValueError('unknown source type')
        if type(self.direction) is not int or self.direction not in {-1, 1}:
            raise ValueError('direction must be fixed before evaluation')
        if not isinstance(self.deviations, list) or any(not isinstance(v, str) or not v for v in self.deviations):
            raise ValueError('deviations must be explicit strings')
        if self.source_type == 'PAPER_EXACT' and self.deviations:
            raise ValueError('deviations require reconstructed or inspired attribution')
        if self.source_type == 'PAPER_RECONSTRUCTED' and not self.deviations:
            raise ValueError('reconstruction requires declared deviations')
        if self.signal_timing != 'after_close_t_execute_close_t_plus_1':
            raise ValueError('unsupported signal/execution timing')
        expression = Expression(self.expression)
        fields = {n.id for n in ast.walk(expression.tree) if isinstance(n, ast.Name) and n.id in FIELDS}
        if not isinstance(self.input_fields, dict) or set(self.input_fields) != fields:
            raise ValueError('input field mapping does not match DSL')
        if not self.operator_semantics or any(not isinstance(v, str) or not v.strip()
                                             for v in [*self.input_fields.values(), *self.operator_semantics.values()]):
            raise ValueError('operator and field semantics must be documented')
        self.factor()

    @property
    def hypothesis_id(self):
        return 'H_' + identity(asdict(self))[:20]

    @property
    def expression_key(self):
        # Whitespace/parentheses only. This is not algebraic or economic equivalence.
        return identity({'ast': ast.dump(Expression(self.expression).tree), 'direction': self.direction})

    def factor(self):
        return FactorDefinition(self.name, self.family, self.expression, self.hypothesis,
                                self.direction, self.source_type, self.source_url,
                                'm3_deterministic_adapter', self.version)


def admit_batch(payload):
    if payload['schema_version'] != 1 or not 1 <= len(payload['candidates']) <= 3:
        raise ValueError('M3.0 requires one to three frozen candidates')
    if payload['feedback_scope'] != 'research_only' or payload['automatic_refinement'] is not False:
        raise ValueError('M3.0 forbids automatic refinement and protected feedback')
    hypotheses = [ResearchHypothesis(**c) for c in payload['candidates']]
    if len({h.name for h in hypotheses}) != len(hypotheses):
        raise ValueError('duplicate candidate name')
    if len({h.expression_key for h in hypotheses}) != len(hypotheses):
        raise ValueError('duplicate normalized expression')
    return hypotheses
