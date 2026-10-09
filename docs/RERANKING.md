# Local semantic reranking

The optional reranker retrieves up to 25 permitted candidates, scores each question/passage pair with `cross-encoder/ms-marco-MiniLM-L6-v2`, then returns the configured `top_k` (normally 5). It runs offline on CPU through ONNX Runtime, with no inference API or credentials. Existing dataset embeddings, indexes and owner/document scope are retained. Changing the reranker does not require reindexing.

Install the extra runtime and explicitly download the fixed model once:

```powershell
.venv/Scripts/python.exe -m pip install -r backend/requirements-reranker.lock
.venv/Scripts/python.exe scripts/setup-reranker.py --directory local-models/ms-marco-MiniLM-L6-v2
$env:AEGIS_RERANKER='local'
$env:AEGIS_RERANK_CANDIDATES='25'
$env:AEGIS_RERANK_MODEL_DIR=(Resolve-Path local-models/ms-marco-MiniLM-L6-v2).Path
```

Set these variables in the API service environment (or `.env` used by the local launcher), then restart it. Defaults to `AEGIS_RERANKER=none`; candidate limit must be 1–100 and is increased if `top_k` is larger. The model directory is operator configuration, not a user-submitted URL. For a container, install the extra requirements and mount the downloaded model directory read-only; the native Windows verification does not validate a container deployment.

The official model revision is pinned to `233902d25c440f23af6f7d6e94d2946bac0bee0a`. Model and tokenizer hashes are verified before loading. Runtime never downloads anything. Enabled reranking fails explicitly if assets or inference are unavailable; it does not silently claim to rerank while returning vector-only results. `/ready` checks the configured model, `/api/settings` reports its state, and `/api/index/search` reports candidate count, rerank time, original vector scores, rerank logits and retrieval ranks. Rerank logits are relevance scores, not probabilities.

The model supports English passage ranking with a 512-token pair limit. Questions are limited to 128 tokens for ranking, and long passages are truncated to leave room for the question. The answer model still receives the canonical full selected chunks. Measure ranking quality and latency on representative questions; reranking cannot recover evidence outside its candidate pool or guarantee answer correctness.

Run the real model check:

```powershell
$env:AEGIS_TEST_RERANKER='true'
.venv/Scripts/python.exe -m pytest backend/tests/test_reranker.py
```

Sources: [official model and license](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2), [retrieve and rerank](https://sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html).
