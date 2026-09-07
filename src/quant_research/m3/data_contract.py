"""One explicit input boundary for daily formulas and existing PIT panels.

No data acquisition or financial restatement reconstruction occurs here. Panels
must match their frozen hashes and retain their source-specific limitations.
"""
from dataclasses import replace
from datetime import date
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..factors.expressions import DAILY_FIELDS, PIT_FIELDS

CONTRACT_PATH='configs/m3/data_contract_v1.json'


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inside(root,name):
    if not isinstance(name,str) or not name:raise ValueError('missing contract asset path')
    root=Path(root).resolve();path=(root/name).resolve()
    if not path.is_relative_to(root):raise ValueError('contract asset outside project')
    return path


def required_fields(hypotheses):return set().union(*(set(h.input_fields) for h in hypotheses))


def validate_contract(contract):
    if contract.get('schema_version')!=1 or contract.get('protected_accessed') is not False:
        raise ValueError('unsupported or unsealed input contract')
    fields=contract.get('fields',{})
    if not isinstance(fields,dict) or set(fields)!=DAILY_FIELDS|PIT_FIELDS:
        raise ValueError('input contract must enumerate the supported daily and PIT fields')
    for name,field in fields.items():
        if any(not isinstance(field.get(k),str) or not field[k].strip()
               for k in ['unit','availability','missing_policy','revision_policy']):
            raise ValueError('field semantics must be explicit')
        if name in DAILY_FIELDS:
            if field.get('kind')!='daily':raise ValueError('daily field identity mismatch')
        else:
            if field.get('kind')!='pit_panel':raise ValueError('PIT field identity mismatch')
            span=field.get('period',[])
            if len(span)!=2:raise ValueError('PIT source period required')
            start,end=map(date.fromisoformat,span)
            if start>end or end>=date(2021,1,1):raise ValueError('protected PIT source period')
            if field.get('publication_age_days')!=400 or field.get('fiscal_age_days')!=550:
                raise ValueError('PIT age policy changed')
            for item in ['panel','manifest','verification']:
                entry=field.get(item,{})
                if not isinstance(entry.get('path'),str) or not isinstance(entry.get('sha256'),str) or len(entry['sha256'])!=64:
                    raise ValueError('PIT identity and verification required')
    return contract


def read_contract(root,binding,required):
    if not set(required)<=DAILY_FIELDS|PIT_FIELDS:raise ValueError('unsupported input field')
    if binding is None:
        if set(required)&PIT_FIELDS:raise ValueError('PIT inputs require a frozen data contract')
        return None  # Original daily-only batches preserve their identities.
    if not isinstance(binding,dict) or binding.get('path')!=CONTRACT_PATH:
        raise ValueError('unknown data contract binding')
    path=inside(root,binding['path'])
    if digest(path)!=binding.get('sha256'):raise ValueError('data contract changed after freeze')
    return validate_contract(json.loads(path.read_text(encoding='utf-8')))


def freeze_binding(root,required):
    path=Path(root)/CONTRACT_PATH
    binding={'path':CONTRACT_PATH,'sha256':digest(path)} if path.exists() else None
    read_contract(root,binding,required)
    return binding


def verify_input_identity(root,contract,required):
    """Check again before recording an outcome from a long-running experiment."""
    if contract is None:return
    entries=[contract['canonical_manifest']]
    for name in set(required)&PIT_FIELDS:
        meta=contract['fields'][name]
        entries.extend(meta[k] for k in ['panel','manifest','verification'])
        entries.extend(meta.get('additional_evidence',[]))
    for entry in entries:
        if digest(inside(root,entry['path']))!=entry['sha256']:
            raise ValueError('input identity changed during experiment')


def attach_fields(root,market,contract,required):
    """Reindex only; never forward-fill, scale, or restate imported values."""
    if contract is None:
        if set(required)&PIT_FIELDS:raise ValueError('missing frozen PIT contract')
        return market,{'kind':'legacy_daily','protected_accessed':False}
    validate_contract(contract)
    if market.membership.index.max()>=pd.Timestamp('2021-01-01'):
        raise ValueError('protected market observations')
    canonical=contract['canonical_manifest']
    if digest(inside(root,canonical['path']))!=canonical['sha256']:
        raise ValueError('canonical data identity differs from input contract')
    fields=dict(market.fields);report={'schema_version':1,'protected_accessed':False,'fields':{}}
    for name in sorted(required):
        meta=contract['fields'][name]
        if name in PIT_FIELDS:
            paths={}
            for key in ['panel','manifest','verification']:
                entry=meta[key];path=inside(root,entry['path'])
                if digest(path)!=entry['sha256']:raise ValueError(f'{name} {key} identity mismatch')
                paths[key]=path
            manifest=json.loads(paths['manifest'].read_text())
            panel_key=paths['panel'].relative_to(paths['manifest'].parent)
            # Existing Windows manifests use either slash spelling.
            if manifest.get(str(panel_key),manifest.get(panel_key.as_posix()))!=meta['panel']['sha256']:
                raise ValueError('PIT panel is not part of its declared source run')
            if json.loads(paths['verification'].read_text()).get('status')!='PASS':
                raise ValueError('PIT source did not pass independent verification')
            for entry in meta.get('additional_evidence',[]):
                if digest(inside(root,entry['path']))!=entry['sha256']:
                    raise ValueError('PIT source-assignment identity mismatch')
            panel=pd.read_parquet(paths['panel'])
            if (not isinstance(panel.index,pd.DatetimeIndex) or panel.index.has_duplicates
                    or not panel.index.is_monotonic_increasing or panel.columns.has_duplicates
                    or not set(panel.columns)<=set(market.membership.columns)):
                raise ValueError('PIT axes are incompatible with canonical data')
            if (panel.empty or panel.index.min()!=pd.Timestamp(meta['period'][0])
                    or panel.index.max()!=pd.Timestamp(meta['period'][1])):
                raise ValueError('PIT observations differ from declared period')
            if np.isinf(panel.to_numpy(dtype=float)).any():raise ValueError('infinite PIT values')
            fields[name]=panel.reindex_like(market.membership)
        if name not in fields:raise ValueError('declared field not loaded')
        panel=fields[name]
        count=int(panel.where(market.membership).notna().to_numpy().sum())
        report['fields'][name]={'semantics':meta,'eligible_finite_cells':count,
                               'operation':'identity/reindex; no fill or unit conversion'}
    report['cross_field_fiscal_alignment']='Not guaranteed; each field is latest independently available. Mixed-field hypotheses must account for mismatched reporting periods.'
    return replace(market,fields=fields),report
