"""Kubernetes init: wait for DB/vector/model services and install local models."""
import os
import time
from pathlib import Path
from sqlalchemy import create_engine, text
from .database import database_url, engine_options
from .container_smoke import call


def run():
    url = database_url(Path('/data'))
    engine = create_engine(url, **engine_options(url))
    model_url = os.environ['AEGIS_OLLAMA_URL'].rstrip('/')
    vector_url = os.environ['QDRANT_URL'].rstrip('/')
    for attempt in range(120):
        try:
            with engine.connect() as connection:
                connection.execute(text('SELECT 1 FROM DUAL'))
            call(vector_url, '/collections', timeout=5)
            call(model_url, '/api/tags', timeout=5)
            break
        except Exception:
            # Never log connection exceptions: they may contain credentials.
            if attempt == 119:
                raise RuntimeError('Database, Qdrant or Ollama did not become ready.') from None
            time.sleep(10)
    engine.dispose()
    names=[os.environ['AEGIS_MODEL'], os.environ['EMBEDDING_MODEL']]
    if os.getenv('AEGIS_OCR_ENABLED','true').lower()=='true':names.append(os.getenv('AEGIS_OCR_MODEL','qwen2.5vl:3b'))
    for name in dict.fromkeys(names):
        response = call(model_url, '/api/pull', {'model': name, 'stream': False}, timeout=1800)
        if response.get('status') != 'success':
            raise RuntimeError('Local model provisioning failed: ' + name)
    print('Database and vector store ready; required local models installed.')


if __name__ == '__main__':
    run()
