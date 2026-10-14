"""Local Ollama execution uses ollama.py, not the cloud connection facade."""
from ...validation import ConnectionError

def generate(connection, *args):
    raise ConnectionError("This model protocol does not support cloud generation.")

def embed(connection, *args):
    raise ConnectionError("This model protocol does not support cloud embeddings.")
