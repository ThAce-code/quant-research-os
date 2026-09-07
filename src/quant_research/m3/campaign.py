"""Durable research budgets, cross-batch duplicates and parent-linked proposals.

The existing FactorRegistry owns empirical decisions. This ledger owns attempts,
including failures that never became calculable factors. Reservations survive a
process restart; an uncertain remote call is never silently refunded.
"""
import ast
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import sqlite3

from .candidates import ResearchHypothesis, identity
from ..factors.expressions import Expression


def expression_signature(expression, direction):
    tree = Expression(expression).tree
    def canonical(n):
        if isinstance(n, ast.Name): return ['field', n.id]
        if isinstance(n, ast.Constant): return ['number', float(n.value)]
        if isinstance(n, ast.UnaryOp):
            return canonical(n.operand) if isinstance(n.op, ast.UAdd) else combine('Mul', [['number', -1.], canonical(n.operand)])
        if isinstance(n, ast.BinOp):
            op = {ast.Add:'Add', ast.Sub:'Sub', ast.Mult:'Mul', ast.Div:'Div'}[type(n.op)]
            return combine(op, [canonical(n.left), canonical(n.right)])
        return combine(n.func.id, [canonical(a) for a in n.args])
    def combine(op, args):
        if op in {'Add', 'Mul'}:
            args = sorted(args, key=lambda x: json.dumps(x, sort_keys=True))
        return [op, *args]
    value = canonical(tree)
    if direction == -1: value = combine('Mul', [['number', -1.], value])
    return identity(value)


@dataclass(frozen=True)
class CampaignSpec:
    campaign_id: str
    research_period: list
    max_proposals: int
    max_evaluations: int
    max_calls: int
    max_output_tokens: int
    max_rounds: int
    seed: int
    objective: str

    def __post_init__(self):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', self.campaign_id):
            raise ValueError('invalid campaign ID')
        from datetime import date
        if not isinstance(self.research_period, list) or len(self.research_period) != 2:
            raise ValueError('research period must be a date pair')
        start, end = [date.fromisoformat(d) for d in self.research_period]
        if start > end or end.year >= 2021:
            raise ValueError('research period cannot enter qualification/lockbox')
        for field in ['max_proposals','max_evaluations','max_calls','max_output_tokens','max_rounds','seed']:
            if type(getattr(self, field)) is not int or getattr(self, field) < 0:
                raise ValueError('budgets and seed must be nonnegative integers')
        if not self.max_proposals or not self.max_rounds or not self.objective.strip():
            raise ValueError('empty campaign')
        if self.max_evaluations > self.max_proposals:
            raise ValueError('evaluation budget exceeds proposal budget')


class CampaignLedger:
    def __init__(self, path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS campaigns (
                    id TEXT PRIMARY KEY, spec TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'OPEN');
                CREATE TABLE IF NOT EXISTS proposals (
                    id INTEGER PRIMARY KEY, campaign TEXT NOT NULL REFERENCES campaigns(id),
                    round INTEGER NOT NULL, payload TEXT NOT NULL, signature TEXT,
                    status TEXT NOT NULL, reason TEXT, parents TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS expressions (
                    signature TEXT PRIMARY KEY, origin TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS calls (
                    id INTEGER PRIMARY KEY, campaign TEXT NOT NULL REFERENCES campaigns(id),
                    round INTEGER NOT NULL, output_budget INTEGER NOT NULL, state TEXT NOT NULL,
                    response TEXT, used_output_tokens INTEGER, error TEXT, request TEXT);
                CREATE TABLE IF NOT EXISTS evaluations (
                    proposal INTEGER PRIMARY KEY REFERENCES proposals(id), state TEXT NOT NULL,
                    run_id TEXT, evidence TEXT);
                CREATE TABLE IF NOT EXISTS call_proposals (
                    call INTEGER NOT NULL REFERENCES calls(id), ordinal INTEGER NOT NULL,
                    proposal INTEGER NOT NULL REFERENCES proposals(id), PRIMARY KEY(call,ordinal));
                CREATE TRIGGER IF NOT EXISTS proposals_no_update BEFORE UPDATE ON proposals
                    BEGIN SELECT RAISE(ABORT, 'immutable proposal'); END;
                CREATE TRIGGER IF NOT EXISTS proposals_no_delete BEFORE DELETE ON proposals
                    BEGIN SELECT RAISE(ABORT, 'immutable proposal'); END;
            ''')
            if 'request' not in {row[1] for row in db.execute('PRAGMA table_info(calls)')}:
                db.execute('ALTER TABLE calls ADD COLUMN request TEXT')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db: yield db
        finally: db.close()

    def create(self, spec):
        payload = json.dumps(asdict(spec), sort_keys=True, allow_nan=False)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT spec FROM campaigns WHERE id=?', (spec.campaign_id,)).fetchone()
            if old is not None and old['spec'] != payload:
                raise ValueError('campaign specification is immutable')
            db.execute('INSERT OR IGNORE INTO campaigns(id,spec) VALUES (?,?)', (spec.campaign_id, payload))

    def _active(self, db, campaign, round_number):
        row = db.execute('SELECT * FROM campaigns WHERE id=?', (campaign,)).fetchone()
        if row is None or row['state'] != 'OPEN': raise ValueError('campaign is not open')
        spec = json.loads(row['spec'])
        if type(round_number) is not int or not 0 <= round_number < spec['max_rounds']:
            raise ValueError('round budget exhausted')
        return spec

    def import_expression(self, expression, direction, origin):
        signature = expression_signature(expression, direction)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO expressions VALUES (?,?)', (signature, origin))

    def propose(self, campaign, round_number, payload, parents=()):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            return self._propose(db, campaign, round_number, payload, parents)

    def _propose(self, db, campaign, round_number, payload, parents):
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
        spec = self._active(db, campaign, round_number)
        used = db.execute('SELECT COUNT(*) FROM proposals WHERE campaign=?', (campaign,)).fetchone()[0]
        if used >= spec['max_proposals']: raise ValueError('proposal budget exhausted')
        if len(parents) > 2 or len(set(parents)) != len(parents):
            raise ValueError('mutation/crossover requires up to two distinct parents')
        for parent in parents:
            row = db.execute('SELECT campaign,round,status FROM proposals WHERE id=?', (parent,)).fetchone()
            if row is None or row['campaign'] != campaign or row['round'] >= round_number or row['status'] != 'ACCEPTED':
                raise ValueError('parent must be an earlier accepted proposal in the same campaign')
        status, reason, signature = 'ACCEPTED', None, None
        try:
            h = ResearchHypothesis(**payload)
            signature = expression_signature(h.expression, h.direction)
            old = db.execute('SELECT origin FROM expressions WHERE signature=?', (signature,)).fetchone()
            if old is not None: status, reason = 'DUPLICATE', old['origin']
        except (ValueError, TypeError, KeyError) as exc:
            status, reason = 'INVALID', str(exc)
        cursor = db.execute('INSERT INTO proposals(campaign,round,payload,signature,status,reason,parents) VALUES (?,?,?,?,?,?,?)',
            (campaign, round_number, encoded, signature, status, reason, json.dumps(list(parents))))
        if status == 'ACCEPTED':
            db.execute('INSERT INTO expressions VALUES (?,?)', (signature, f'proposal:{cursor.lastrowid}'))
        return {'proposal_id': cursor.lastrowid, 'status': status, 'reason': reason}


    def reserve_call(self, campaign, round_number, output_tokens, request=None):
        if type(output_tokens) is not int or output_tokens <= 0: raise ValueError('invalid output reservation')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE'); spec = self._active(db, campaign, round_number)
            count, reserved = db.execute('SELECT COUNT(*),COALESCE(SUM(output_budget),0) FROM calls WHERE campaign=?', (campaign,)).fetchone()
            if count >= spec['max_calls'] or reserved+output_tokens > spec['max_output_tokens']:
                raise ValueError('model call/output token budget exhausted')
            return db.execute("INSERT INTO calls(campaign,round,output_budget,state,request) VALUES (?,?,?,'RESERVED',?)",
                              (campaign, round_number, output_tokens, json.dumps(request,allow_nan=False))).lastrowid

    def materialize_call(self, campaign, ticket):
        """Replay a saved response without another HTTP call or duplicate proposals."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM calls WHERE id=? AND campaign=?',(ticket,campaign)).fetchone()
            if row is None or row['state']!='COMPLETE':
                raise ValueError('only a completed model call can be materialized')
            saved=db.execute('SELECT p.id AS proposal_id,p.status,p.reason FROM call_proposals c JOIN proposals p ON c.proposal=p.id WHERE c.call=? ORDER BY c.ordinal',(ticket,)).fetchall()
            if saved:return {'ticket':ticket,'proposals':[dict(p) for p in saved]}
            response=json.loads(row['response']);request=json.loads(row['request'])
            candidates=json.loads(response['content'])['candidates']
            if not isinstance(candidates,list) or not 1<=len(candidates)<=3:
                raise ValueError('model must propose one to three candidates')
            proposals=[]
            for ordinal,item in enumerate(candidates):
                if isinstance(item,dict):
                    item={**item,'source_type':'LLM_GENERATED','source_url':f'model://{request["model"]}',
                          'source_locator':f'campaign:{campaign}/call:{ticket}'}
                result=self._propose(db,campaign,row['round'],item,request.get('parents',[]))
                db.execute('INSERT INTO call_proposals VALUES (?,?,?)',(ticket,ordinal,result['proposal_id']))
                proposals.append(result)
            return {'ticket':ticket,'proposals':proposals}

    def finish_call(self, ticket, response=None, used_output_tokens=None, error=None):
        if used_output_tokens is not None and (type(used_output_tokens) is not int or used_output_tokens < 0):
            raise ValueError('invalid token usage')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM calls WHERE id=?', (ticket,)).fetchone()
            if row is None or row['state'] != 'RESERVED': raise ValueError('call already finalized or unknown')
            overrun = used_output_tokens is not None and used_output_tokens > row['output_budget']
            state = 'OVERRUN' if overrun else ('FAILED' if error else 'COMPLETE')
            db.execute('UPDATE calls SET state=?,response=?,used_output_tokens=?,error=? WHERE id=?',
                       (state, json.dumps(response, allow_nan=False), used_output_tokens, error, ticket))
            if overrun: db.execute("UPDATE campaigns SET state='STOPPED_PROVIDER_OVERRUN' WHERE id=?", (row['campaign'],))

    def reserve_evaluation(self, proposal):
        return self.reserve_evaluations([proposal])

    def reserve_evaluations(self, proposals):
        """Reserve the whole batch atomically; a bad member cannot strand its peers."""
        if not proposals or len(set(proposals)) != len(proposals):
            raise ValueError('select distinct proposals')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            campaign = None
            for proposal in proposals:
                row = db.execute('SELECT * FROM proposals WHERE id=?', (proposal,)).fetchone()
                if row is None or row['status'] != 'ACCEPTED': raise ValueError('proposal not admitted to calculation')
                if campaign is not None and campaign != row['campaign']:
                    raise ValueError('evaluation batch cannot cross campaigns')
                campaign = row['campaign']
                spec = self._active(db, campaign, row['round'])
                used = db.execute('SELECT COUNT(*) FROM evaluations e JOIN proposals p ON e.proposal=p.id WHERE p.campaign=?', (campaign,)).fetchone()[0]
                if used >= spec['max_evaluations']: raise ValueError('evaluation budget exhausted')
                if db.execute('SELECT 1 FROM evaluations WHERE proposal=?',(proposal,)).fetchone():
                    raise ValueError('evaluation already reserved; attach evidence instead of rerunning')
                db.execute("INSERT INTO evaluations(proposal,state) VALUES (?,'RESERVED')", (proposal,))

    def finish_evaluation(self, proposal, run_id, evidence):
        from datetime import date
        if evidence.get('scope') != 'research_only' or evidence.get('protected_accessed') is not False:
            raise ValueError('only explicitly research-scoped results enter campaign memory')
        span = evidence.get('period')
        if not isinstance(span,list) or len(span)!=2:
            raise ValueError('protected or missing feedback period')
        start,end=[date.fromisoformat(d) for d in span]
        if start>end or end.year>=2021:
            raise ValueError('protected or missing feedback period')
        encoded = json.dumps(evidence, sort_keys=True, allow_nan=False)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT e.*,c.spec FROM evaluations e JOIN proposals p ON e.proposal=p.id JOIN campaigns c ON p.campaign=c.id WHERE e.proposal=?', (proposal,)).fetchone()
            if row is not None and row['state']=='COMPLETE' and row['run_id']==run_id and row['evidence']==encoded:
                return  # A crash during multi-result attachment is safely replayable.
            if row is None or row['state'] != 'RESERVED': raise ValueError('evaluation not reserved or already complete')
            period = json.loads(row['spec'])['research_period']
            if not period[0] <= evidence['period'][0] <= evidence['period'][1] <= period[1]:
                raise ValueError('feedback outside frozen campaign period')
            db.execute("UPDATE evaluations SET state='COMPLETE',run_id=?,evidence=? WHERE proposal=?", (run_id, encoded, proposal))

    def snapshot(self, campaign):
        with self.connect() as db:
            spec = db.execute('SELECT * FROM campaigns WHERE id=?', (campaign,)).fetchone()
            if spec is None: raise ValueError('unknown campaign')
            return {'campaign': dict(spec),
                'proposals': [dict(r) for r in db.execute('SELECT * FROM proposals WHERE campaign=? ORDER BY id', (campaign,))],
                'calls': [dict(r) for r in db.execute('SELECT * FROM calls WHERE campaign=? ORDER BY id', (campaign,))],
                'evaluations': [dict(r) for r in db.execute('SELECT e.* FROM evaluations e JOIN proposals p ON e.proposal=p.id WHERE p.campaign=? ORDER BY e.proposal', (campaign,))]}
