import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('protected_gate',Path(__file__).resolve().parents[1]/'scripts/close_protected_gates.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_no_entry_record_cannot_hide_a_qualified_winner():
    with pytest.raises(ValueError):module.validate_no_go({'decision':'GO','winner':'BP'},{'BP':{'decision':'GO'}})
    with pytest.raises(ValueError):module.validate_no_go({'decision':'NO_GO','winner':None},{'BP':{'decision':'GO'}})
    module.validate_no_go({'decision':'NO_GO','winner':None},{'BP':{'decision':'NO_GO'}})
