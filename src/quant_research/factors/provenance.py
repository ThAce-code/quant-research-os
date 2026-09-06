"""Anchor research inputs and executing source to the frozen baseline."""
import hashlib
from pathlib import Path
import shutil


def verify_data_identity(root, baseline_config, frozen):
    manifest = Path(root)/'data/canonical'/baseline_config['name']/'manifest.json'
    actual = hashlib.sha256(manifest.read_bytes()).hexdigest()
    if actual != frozen['original_provenance']['source_manifest_sha256']:
        raise ValueError('canonical manifest differs from frozen M0 data identity')
    return actual


def source_hashes(root):
    root=Path(root)
    sources=list((root/'src/quant_research/factors').glob('*.py')) + [root/'scripts/run_factors.py',root/'run-factors.ps1']
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}


def freeze_sources(root, output):
    root,output=Path(root),Path(output)
    hashes=source_hashes(root)
    for name,want in hashes.items():
        target=output/'source'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(root/name,target)
        if hashlib.sha256(target.read_bytes()).hexdigest()!=want:
            raise ValueError('source changed while freezing snapshot')
    return hashes


def verify_sources(root, expected):
    if source_hashes(root)!=expected:
        raise ValueError('factor source changed during evaluation')
