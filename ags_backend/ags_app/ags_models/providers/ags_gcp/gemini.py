"""Gemini Developer API through its OpenAI-compatible endpoint."""
from ..ags_openai.adapter import generate
from ..ags_openai import adapter


def embed(connection, texts, query, dim, extra):
    # Gemini protobuf JSON omits the default zero index; other order checks stay strict.
    return adapter.embed(connection, texts, query, dim, extra, restore_zero_index=True)
