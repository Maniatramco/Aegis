# Documents to answers

Home lists the signed-in owner's accessible datasets, document counts and actual processing/index compatibility. Active/inactive is a separate dataset setting. Search the directory and use Open chat to select that exact dataset. Dataset settings retain model mappings and access checks. Use **Use installed local models** to explicitly map installed Qwen3, SmolLM2 and Nomic models; existing embedding selections are preserved.

Chat includes dataset and model selection, ready-document scope, attachments, conversation and composer. Uploads use the existing durable backend. The horizontal popup shows stored Upload → Extract → Index → Ready transitions; Extract here means original text parsing, while structured extraction uses a selected JSON Schema separately. No UI percentage predicts completion. Hide/reopen does not cancel processing. Retry uses the failed job ID and its pinned configuration, and skips completed parsing when the index operation failed. Re-extract reparses the unchanged original and rebuilds its dependent index, retaining earlier parsed/index versions. Reviewed structured results are preserved; rerunning a structured result explicitly confirms replacement and preserves the earlier saved version.

## Review and export

Review shows extracted fields on the left and the original PDF on the right, with the recorded source page. TXT/DOCX have an extracted-text fallback and original download. Current extraction records have real page/quote/chunk provenance but no region boxes: the UI states this and does not invent highlights. A field without verified evidence is unverified, even if a source document is available.

Save validates against the recorded schema and creates a new immutable saved version. Requests must include `version`; stale versions return 409 and the browser retains its draft. Cancel restores the last loaded saved values. Reload or navigation asks before discarding unsaved edits. Saved edits never mutate originals. Edited fields lose their verified evidence, while original quotes and provenance remain available. Versions are accessible through `/api/extractions/{id}/versions`.

Download results exports the latest saved values, never browser drafts. JSON contains result, version, identifiers and evidence/source provenance. CSV and XLSX use rows with JSON Pointer field identifiers and provenance. CSV is UTF-8 with BOM, standard quoted/escaped records and formula-prefix protection, including leading whitespace. XLSX is an actual OOXML workbook with inline string cells and no formulas. Excel-incompatible control characters produce an explicit error instead of corrupting a workbook; JSON/CSV remain alternatives.

## Local inference and compatibility

Verified installed tags in the Windows test daemon on 2026-10-07:

| Role | Identifier | Installed licence |
| --- | --- | --- |
| Chat/extraction | `qwen3:4b` | Apache 2.0 |
| Optional chat | `smollm2:1.7b-instruct-q4_K_M` | Apache 2.0 |
| Embeddings | `nomic-embed-text:latest` (configured alias `nomic-embed-text` also resolves locally) | Apache 2.0 |

Licence text was read from the installed daemon's `/api/show` responses. Official listings: [Qwen3](https://ollama.com/library/qwen3:4b), [SmolLM2](https://ollama.com/library/smollm2:1.7b-instruct-q4_K_M), [Nomic](https://ollama.com/library/nomic-embed-text). No Gemini/Gemma model or paid/cloud fallback is configured. Local-only deployment rejects remote models, storage, search and queues. Model discovery is read-only; setup does not download a model.

Index fingerprints bind provider, exact embedding identifier, dataset/index generation and installed Ollama weights digest. Embedding calls reject digest changes before/after inference. Chat model switching does not change this embedding space. Older indexes without a verified digest require explicit reindexing; originals remain stored. This deliberately prevents an updated mutable model tag from silently mixing incompatible embeddings. Do not silently relabel an old index as verified.

Optional offline CPU reranking follows semantic retrieval and retains canonical document ownership, index checks, chunks and citations. See [RERANKING.md](RERANKING.md). Retrieval scores/logits are not probabilities; small local models can still produce incorrect answers. Check cited originals. Focused synthetic checks are not a general accuracy benchmark.

## Temporary retention

Temporary conversation turns exist only in browser memory and the active server inference request. No conversation/message/history/execution record is written by the temporary answer endpoint. Reload/leave clears the browser conversation; local Ollama can retain a loaded model in RAM, but Aegis does not persist its temporary prompts as conversation history. Application infrastructure/access logs can still retain request metadata; this is not an anonymous mode.

Temporary-only uploads are tagged to an authorized file session with one-hour expiry. Session metadata contains no messages. Worker cleanup checks every minute, skips active processing and retries failed cleanup. Stop the worker and cleanup waits until it resumes. Explicit cleanup is available in chat. A lifecycle lock fences cleanup against permanent promotion. Existing permanent documents never receive the session tag. Keeping an upload or using it in saved chat/extraction removes its temporary tag, and cleanup also checks persistent references before deletion. It removes temporary-only originals, parsed text, chunks, vectors/indexes and derived versions. Jobs retain operational metadata without document text. Permanent dataset documents referenced by temporary chat remain untouched.

## Validation

Automated backend checks cover actual worker transitions, controlled outages/same-job retry, versions/conflicts/schema validation, failed writes, unchanged originals, Unicode/formula-safe exports, authorization, model digest swaps and scoped retention/expiry. Browser CI uses explicitly mock-labelled generation against real storage/worker APIs, so it proves controls/routing rather than real model quality. The separate Windows live test exercises actual Ollama + Nomic + offline reranker, extraction/save/reload/downloads and cited answers with both installed chat models. CI must be inspected for the exact pushed SHA; no PR merge or issue closure is implied.

Scanned/encrypted PDFs and DOCX page/region coordinates remain unsupported. The app reports these limits; it does not simulate OCR or source highlights.
