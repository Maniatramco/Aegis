"""Browser fixture entry points must fail closed outside disposable mock runs."""
import os
from pathlib import Path
import subprocess
import sys
import pytest

@pytest.mark.parametrize('allow,provider',[('false','mock'),('true','openai'),('','mock')])
def test_browser_model_fixture_cannot_start_against_real_providers(allow,provider):
    result=subprocess.run([sys.executable,str(Path(__file__).with_name('browser_app.py'))],
        env=os.environ|{'AEGIS_ALLOW_MOCK':allow,'MODEL_PROVIDER':provider},capture_output=True,text=True,timeout=10)
    assert result.returncode!=0
    assert 'explicitly disposable mock deployment' in result.stderr
