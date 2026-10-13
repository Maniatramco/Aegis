# Local Qwen OCR

Aegis uses `qwen2.5vl:3b` through the existing Ollama container for scanned PDF
pages and embedded raster images in DOCX. This is separate from dataset chat,
extraction and embedding model mappings. JSON prompts are validated as schemas
and saved without OCR. TXT and JSON documents use their original text.

## Processing

1. Save unchanged originals and queue a durable indexing job.
2. Read selectable PDF text. Pages with images, sparse text, or replacement
   characters are rendered and transcribed individually. Existing selectable
   text is retained; visual transcription adds content rather than replacing it.
3. Preserve page and merged-source references. Save complete OCR pages, parsed
   text, chunks, model digest and processing details in file/object storage.
4. Embed the resulting text and index it in Qdrant. Only then mark the document
   ready. Oracle stores application metadata and statuses, not OCR payloads.
5. Run the confirmed extraction with the selected template. Combined records
   preserve one source record per original; independent mode has separate IDs.
6. Review saved results by dataset and extraction ID, with an OCR notice and
   unchanged original PDF. JSON/CSV/Excel exports distinguish OCR quote matching
   from verification of the original image.

Combined upload preparation makes no OCR calls in the HTTP request. The worker
reads retained originals, including scans in mixed-format merges. Failed pages
stop indexing. Complete page caches survive retry, keyed by original bytes,
page, model digest and OCR settings. Cancellation/lease checks run before OCR
and before committing/indexing; an in-flight inference may finish before stopping.

## Configuration

| Environment variable | Default | Purpose |
|---|---|---|
| `AEGIS_OCR_ENABLED` | `true` | Explicitly enable/disable visual reading |
| `AEGIS_OCR_MODEL` | `qwen2.5vl:3b` | Installed local vision model |
| `AEGIS_OCR_URL` | `AEGIS_OLLAMA_URL` | Approved local/container endpoint |
| `AEGIS_OCR_TIMEOUT` | `1200` | Per-page request timeout in seconds |
| `AEGIS_OCR_CONTEXT` | `8192` | Input/output context, including visual budget |
| `AEGIS_OCR_MAX_TOKENS` | `3000` | Maximum generated transcription per page |
| `AEGIS_OCR_DPI` | `180` | PDF rendering resolution; 100–300 supported |
| `AEGIS_OCR_BATCH` | `128` | Bounded processing batch to reduce memory pressure; 32-1024 supported |
| `AEGIS_OCR_FORCE_CPU` | `false` | Diagnostic CPU-only inference override |

Defaults are configured in Oracle Compose and the Kubernetes ConfigMap. Model
provisioning installs the OCR model alongside chat/embedding models. The ordinary
CPU Kubernetes manifest requests no GPU. The optional GPU overlay requests a
compatible NVIDIA GPU; the local launcher retains its container GPU probe and
CPU fallback. Ollama controls actual offload; host GPU presence is insufficient.

The CPU path requires enough RAM for vision weights, visual processing, context,
and other services. The current Kubernetes Ollama memory limit is 8 GiB; measure
the workload and adjust it for larger models, context or concurrency. CPU and GPU
have different performance. No cluster runtime has been certified by local tests.

Run the actual inference check inside the app container:

```sh
python -m ags_app.ocr_smoke
python -m ags_app.container_smoke
```

The first renders known fictional text and verifies exact invoice/reference values
using the actual vision model; it reports observed model VRAM and elapsed time.
The second also checks chat, embedding, dependencies, and OCR. The launcher runs
the combined smoke check. To measure CPU, set `AEGIS_OCR_FORCE_CPU=true` only for
the diagnostic command/container. No external API, GPU library in the application
image, or OCR database table is required.

## Failures and accuracy

Missing/nonvision models, service failures, invalid JSON, unreadable text,
truncated output, visual budget overflow, encrypted/invalid PDFs and rendering
limits produce actionable job errors. Retry failed indexing after correcting the
model/settings/scan, explicitly continue with ready documents when appropriate,
choose independent extraction, or end the request. A failed original remains
available. Do not silently treat incomplete files as ready.

Qwen transcription is generated text, not guaranteed faithful OCR. Schema
validation checks structure, not factual truth. No calibrated confidence or
verified field coordinates are fabricated. Review names, dates, amounts, tables,
and handwriting against the originals. Scans of unsupported DOCX vector image
formats should be exported to PDF. DOCX embedded images have image references
but no inferred page numbers. Standalone PNG/JPEG uploads remain outside the
existing PDF/DOCX/TXT/JSON upload contract.

Very dense or large pages fail explicit bounds rather than lose text. Reduce
resolution only if small text stays legible; otherwise split the page or increase
the model budget with adequate memory. Native-only documents do not need the
vision model. Blank white pages need no model inference; wholly blank files fail.

## Validation

`ags_backend/ags_tests/test_ocr.py` checks page selection, blank pages, strict response
validation, disabled/nonvision models, merged scan handling, page caches,
source retention, mixed PDFs and DOCX raster images. `ags_frontend/ags_tests/ocr-live.js`
exercises actual Oracle/Qdrant/Ollama upload, extraction and review in a dedicated
test schema. Its report includes timings and resume field differences; a passing
fixture does not establish universal OCR accuracy.
