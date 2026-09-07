"""Replay translated exports with pinned native operators and canonical panels.

This is numerical adapter evidence, not evidence of profitable factors. Run each
source in its own process because their upstream Python module names overlap.
"""
import argparse
import ast
import importlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from quant_research.m3.external import translate,read_export,UPSTREAMS
from quant_research.factors.expressions import Expression
from run_m3_searcher import input_tensors,sha,write


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('run',type=Path)
    args=parser.parse_args();run=args.run.resolve()
    manifest=json.loads((run/'export_manifest.json').read_text());source=manifest['source']
    vendor=ROOT/'vendor'/source
    sys.path[:0]=[str(vendor/'src'),str(vendor)] if source=='alphasage' else [str(vendor)]
    native=importlib.import_module('alphagen.data.expression')
    from alphagen_qlib.stock_data import StockData,FeatureType
    import numpy as np
    import pandas as pd
    import torch
    torch.set_num_threads(4)
    config=json.loads((run/'config.json').read_text())
    evidence=run/'verification';evidence.mkdir(exist_ok=True)
    expected=json.loads((run/'source_hashes.json').read_text())
    assert all(sha(vendor/name)==value for name,value in expected.items()),'upstream source changed'
    sets,_=input_tensors(config,evidence)
    raw=read_export(source,run/manifest['asset'],manifest)

    def construct(text):
        # translate performs the restrictive grammar/field/operator validation.
        translate(source,text)
        tree=ast.parse(re.sub(r'\$([A-Za-z_][A-Za-z_0-9]*)',r'\1',text),mode='eval').body
        def build(node):
            if isinstance(node,ast.Name):return native.Feature(FeatureType[node.id.upper()])
            if isinstance(node,ast.Constant):return node.value
            if isinstance(node,ast.UnaryOp):
                value=build(node.operand)
                return -value if isinstance(node.op,ast.USub) else value
            if isinstance(node,ast.BinOp):
                name={ast.Add:'Add',ast.Sub:'Sub',ast.Mult:'Mul',ast.Div:'Div'}[type(node.op)]
                return getattr(native,name)(build(node.left),build(node.right))
            return getattr(native,node.func.id)(*[build(a) for a in node.args])
        result=build(tree)
        return result if isinstance(result,native.Expression) else native.Constant(result)

    def compare(text,data):
        local,_,_=translate(source,text)
        values=data.data.numpy()
        fields={feature.name.lower():pd.DataFrame(values[:,int(feature),:]) for feature in FeatureType}
        start=data.max_backtrack_days;end=start+data.n_days
        actual=Expression(local).evaluate(fields).iloc[start:end].to_numpy()
        upstream=construct(text).evaluate(data).numpy()
        upstream=np.where(np.isfinite(upstream),upstream,np.nan)
        mask=np.isfinite(actual)&np.isfinite(upstream)
        assert actual.shape==upstream.shape
        assert np.array_equal(np.isnan(actual),np.isnan(upstream)),f'missingness differs: {text}'
        assert mask.any(),f'no finite observations: {text}'
        np.testing.assert_allclose(actual,upstream,rtol=2e-5,atol=2e-5,equal_nan=True,err_msg=text)
        return {'expression':text,'translated':local,'finite_cells':int(mask.sum()),
                'missing_cells':int((~mask).sum()),'max_abs_error':float(np.abs(actual[mask]-upstream[mask]).max())}

    # Float64 panels isolate mathematical semantics from float32 cancellation.
    # Ties, zeros, negatives and missing observations are deliberately present.
    rng=np.random.default_rng(42);values=rng.normal(10,2,(50,6,8));values[10:13,:,0]=4
    values[20,:,1]=np.nan;values[22,:,2]=0;values[24,:,3]=-1
    fixture=StockData.__new__(StockData);fixture.data=torch.tensor(values,dtype=torch.float64)
    fixture.max_backtrack_days=15;fixture.max_future_days=0
    cases=['$close','Abs($close)','Inv($close)','Add($close,$open)','Sub($close,2)',
           'Mul($close,$open)','Div($close,$open)','Ref($close,2)']
    cases += [name+'($close,3)' for name in UPSTREAMS[source]['rolling']]
    fixture_results=[compare(text,fixture) for text in cases]
    rows=[]
    for i,text in enumerate(raw):
        try:translate(source,text)
        except ValueError as error:
            rows.append({'row':i,'status':'UNSUPPORTED','reason':str(error),'expression':text});continue
        rows.append({'row':i,'status':'PASS','train':compare(text,sets[0]),'diagnostic':compare(text,sets[1])})
    write(evidence/'result.json',{'status':'PASS','source':source,'revision':manifest['revision'],
          'asset_sha256':manifest['asset_sha256'],'source_files_checked':len(expected),
          'fixture_cases':fixture_results,'export_rows':rows,'rtol':2e-5,'atol':2e-5,
          'scope':'Supported formulas replayed on actual generation and diagnostic tensors; unsupported rows rejected. Not an alpha verdict.',
          'verifier_sha256':sha(__file__),'protected_accessed':False})
    print(json.dumps({'source':source,'fixture_cases':len(fixture_results),
                      'rows':[{k:r[k] for k in ['row','status']} for r in rows]}))


if __name__=='__main__':main()
