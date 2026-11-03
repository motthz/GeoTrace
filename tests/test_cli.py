import sys
import pytest
from geotrace.cli import main

@pytest.mark.parametrize('extra',[
    ['--query','missing.json'],
    ['--sources',''],
    ['--query','missing.json','--resume','id'],
])
def test_invalid_cli_input_is_actionable_without_traceback(tmp_path,monkeypatch,capsys,extra):
    monkeypatch.setattr(sys,'argv',['geotrace-cli','--archive',str(tmp_path/'db'),*extra])
    with pytest.raises(SystemExit) as exc:main()
    assert exc.value.code==2
    stderr=capsys.readouterr().err
    assert 'error:' in stderr and 'Traceback' not in stderr
