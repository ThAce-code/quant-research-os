"""Pinned AlphaForge/AlphaSAGE exports -> the common hypothesis contract.

Incoming expressions and CSV/JSON are data. Never import their Python modules,
unpickle exports or evaluate source strings. Operators without verified matching
semantics fail explicitly and are retained as invalid proposal attempts.
"""
import ast
import csv
from datetime import date
import io
import json
from pathlib import Path
import re

from .pipeline import sha
from ..factors.expressions import Expression


UPSTREAMS={
    'alphaforge':{'repository':'https://github.com/dulyHao/AlphaForge',
                  'revision':'d0cfc27df23c60f271bc885fd43027b86b787746',
                  'rolling':{'ts_mean':'Mean','ts_std':'Std','ts_max':'Max','ts_min':'Min','ts_delta':'Delta'}},
    'alphasage':{'repository':'https://github.com/BerkinChen/AlphaSAGE',
                 'revision':'517467a34909512a92d6e3139df54891957560de',
                 'rolling':{'TsMean':'Mean','TsStd':'Std','TsMax':'Max','TsMin':'Min','TsDelta':'Delta'}}}
FIELDS={'open','close','high','low','volume','vwap'}


def translate(source,text):
    if source not in UPSTREAMS:raise ValueError('unsupported external generator')
    if not isinstance(text,str) or not 1<=len(text)<=4000:raise ValueError('invalid exported expression')
    # Only $field spelling is substituted, never other source-language syntax.
    normalized=re.sub(r'\$([A-Za-z_][A-Za-z_0-9]*)',r'\1',text)
    try:tree=ast.parse(normalized,mode='eval').body
    except SyntaxError as exc:raise ValueError('invalid upstream expression syntax') from exc
    if len(list(ast.walk(tree)))>128:raise ValueError('upstream expression too complex')
    operators=[]
    def walk(node):
        if isinstance(node,ast.Name) and node.id in FIELDS:return node.id
        if isinstance(node,ast.Constant) and type(node.value) in {int,float}:return repr(node.value)
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            return ('+' if isinstance(node.op,ast.UAdd) else '-')+'('+walk(node.operand)+')'
        if isinstance(node,ast.BinOp) and type(node.op) in {ast.Add,ast.Sub,ast.Mult,ast.Div}:
            name={ast.Add:'Add',ast.Sub:'Sub',ast.Mult:'Mul',ast.Div:'Div'}[type(node.op)]
            operators.append((name,name))
            return name+'('+walk(node.left)+', '+walk(node.right)+')'
        if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Name) or node.keywords:
            raise ValueError('unsupported upstream field or expression node')
        name=node.func.id
        # Log(0) is -inf upstream but NaN locally; nested operations can turn
        # -inf into finite values, so Log cannot be translated by renaming it.
        arity={'Abs':1,'Inv':1,'Add':2,'Sub':2,'Mul':2,'Div':2,'Ref':2}
        mapped=UPSTREAMS[source]['rolling'].get(name,name)
        if name in UPSTREAMS[source]['rolling']:arity[name]=2
        if name not in arity or len(node.args)!=arity[name]:
            raise ValueError(f'unsupported or semantically unaligned upstream operator: {name}')
        if mapped=='Delta' and isinstance(node.args[1],ast.Constant) and node.args[1].value==0:
            raise ValueError('upstream zero Delta has incompatible slice semantics')
        if name=='Inv':
            operators.append((name,'Div(1, operand)'))
            return 'Div(1, '+walk(node.args[0])+')'
        if name=='Abs' or name=='Ref' or name in UPSTREAMS[source]['rolling']:
            if not any(isinstance(n,ast.Name) and n.id in FIELDS for n in ast.walk(node.args[0])):
                raise ValueError('local panel operator cannot broadcast a constant operand')
        operators.append((name,mapped))
        return mapped+'('+', '.join(walk(a) for a in node.args)+')'
    result=walk(tree)
    expression=Expression(result)  # Also enforces historical literal lags and finite constants.
    fields={n.id for n in ast.walk(expression.tree) if isinstance(n,ast.Name) and n.id in FIELDS}
    semantics={up:f'{local}; mapped from pinned upstream implementation; full-window historical semantics'
               for up,local in operators}
    if not semantics:semantics={'identity':'Direct upstream feature identity'}
    return result,fields,semantics


def read_export(source,path,manifest):
    if source not in UPSTREAMS:raise ValueError('unsupported external generator')
    if manifest.get('source')!=source or manifest.get('revision')!=UPSTREAMS[source]['revision']:
        raise ValueError('unverified generator revision')
    path=Path(path)
    if path.stat().st_size>2_000_000 or sha(path)!=manifest.get('asset_sha256'):
        raise ValueError('export size or identity mismatch')
    periods=manifest.get('periods')
    if not isinstance(periods,dict) or 'train' not in periods or not periods:
        raise ValueError('declare every generation and feedback period')
    for name,span in periods.items():
        if not isinstance(span,list) or len(span)!=2:raise ValueError('invalid upstream period')
        start,end=[date.fromisoformat(d) for d in span]
        if start>end or end.year>=2021:raise ValueError('protected upstream generation or feedback period')
    if manifest.get('protected_accessed') is not False:
        raise ValueError('upstream protected access must be explicitly false')
    text=path.read_text(encoding='utf-8-sig')
    if source=='alphasage':
        data=json.loads(text);expressions=data.get('exprs')
        if not isinstance(expressions,list):raise ValueError('AlphaSAGE export requires exprs array')
    else:
        reader=csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None or 'exprs' not in reader.fieldnames:raise ValueError('AlphaForge export requires exprs column')
        expressions=[row['exprs'] for row in reader]
    if not expressions or len(expressions)>10000 or any(not isinstance(e,str) for e in expressions):
        raise ValueError('invalid expression asset')
    return expressions


def import_export(ledger,campaign,round_number,source,asset,manifest,annotations):
    """Annotations fix economic rationale and sign before the local screen.

    Manifest periods are declared upstream provenance, not independent proof of
    the producer's data access. Local runner evidence is required for acceptance.
    Row indices are zero-based, frozen choices; import never hunts for a winner
    or changes a direction based on exported scores/weights.
    """
    expressions=read_export(source,asset,manifest)
    if not isinstance(annotations,list) or not 1<=len(annotations)<=3:
        raise ValueError('provide one to three preselected, annotated export rows')
    indices=[a['row'] for a in annotations]
    if len(set(indices))!=len(indices) or any(type(i) is not int or not 0<=i<len(expressions) for i in indices):
        raise ValueError('invalid or duplicate selected export row')
    proposals=[]
    for annotation in annotations:
        raw=expressions[annotation['row']]
        base={k:v for k,v in annotation.items() if k!='row'}
        base.update(source_type='SEARCH_GENERATED',
                    source_url=UPSTREAMS[source]['repository']+'/tree/'+manifest['revision'],
                    source_locator=f'asset_sha256:{manifest["asset_sha256"]}/row:{annotation["row"]}',
                    original_expression=raw,signal_timing='after_close_t_execute_close_t_plus_1')
        try:
            expression,fields,operators=translate(source,raw)
            base.update(expression=expression,
                        input_fields={name:'Canonical daily '+name+'; generator data units must be compared with local units' for name in sorted(fields)},
                        operator_semantics=operators)
            base['deviations']=[*base.get('deviations',[]),
                'Generated export is transferred to the local historical CSI300 protocol; upstream reward is not local alpha evidence.',
                'Declared upstream periods: '+json.dumps(manifest['periods'],sort_keys=True),
                'Float32 upstream and local floating-point arithmetic can differ; missing values remain explicit.']
        except ValueError as exc:
            # Malformed candidate is deliberately sent through the shared ledger,
            # preserving its attempt and reason rather than silently skipping it.
            base.update(expression='UNSUPPORTED_UPSTREAM_EXPRESSION',input_fields={},operator_semantics={},
                        deviations=[str(exc)])
        proposals.append(ledger.propose(campaign,round_number,base))
    return {'source':source,'revision':manifest['revision'],'asset_sha256':manifest['asset_sha256'],
            'exported_expression_count':len(expressions),'selected_rows':indices,
            'scope_evidence':'DECLARED_UPSTREAM_PROVENANCE','proposals':proposals}
