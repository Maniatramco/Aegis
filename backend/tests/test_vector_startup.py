"""Fresh-process SDK initialization before concurrent first-use operations."""
import os
from pathlib import Path
import subprocess
import sys

def test_provider_startup_finishes_qdrant_initialization_before_background_reads(tmp_path):
    script='''
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from app import providers
assert 'qdrant_client.http' in sys.modules
assert hasattr(sys.modules['qdrant_client.http'], 'AsyncApiClient')
barrier=Barrier(8)
def first_use(index):
    barrier.wait()
    if index%2:
        from qdrant_client.models import Filter, FilterSelector
        return FilterSelector(filter=Filter())
    from qdrant_client import QdrantClient
    from qdrant_client.http import AsyncApiClient
    return QdrantClient, AsyncApiClient
with ThreadPoolExecutor(max_workers=8) as pool:
    assert len(list(pool.map(first_use,range(8))))==8
'''
    env=os.environ|{'PYTHONPATH':str(Path(__file__).resolve().parents[1]),
        'AEGIS_STORAGE_ROOT':str(tmp_path),'DATABASE_URL':'sqlite:///'+str(tmp_path/'startup.db')}
    completed=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,timeout=30)
    assert completed.returncode==0,completed.stderr
