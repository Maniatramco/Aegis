# Aegis Assistant verification — 2026-10-10

Later changes and the five-resume/merged/recovery browser tests are documented in
[the current Assistant workflow verification](assistant-workflow-2026-10-10.md).
The observations below retain the earlier CPU run and startup checks.

Tested the Docker app at http://localhost:3003 using real Oracle Free, Qdrant,
Qwen3 4B and Nomic embeddings. UI actions used the computer-use browser skill;
backend inspection was read-only. No live Oracle Kubernetes deployment occurred.

## Observed browser flow

Created a separate **Resume flow QA 2026-10-10** dataset and mapped the existing
registered models. Imported the fictional pack's `resume-extraction-prompt.json`
through Assistant, confirmed its validated schema and saved it. Attached all five
fictional PDFs, sent `upload`, then confirmed the upload.

- All five attachments immediately appeared beside the sent question. Composer
  attachment count was zero while planning; the confirmed upload still received
  the original file bytes.
- Upload planning took **0.096139 s** (browser network measurement). All five PDFs
  finished indexing and became ready.
- Selected only `01-arjun-rao-backend.pdf` because this template extracts one
  candidate. Sent `pls run extract`; confirmation planning took **0.073143 s**.
  Extraction remained an explicitly confirmed action, not automatic execution.
- The first CPU attempt timed out at 300 seconds. A retry timed out at 600 seconds.
  The next CPU run completed in **370.82 s** with context 8,192, output 2,048 and
  timeout 600. This variation is not a speed guarantee.
- All extracted nested values matched `expected-results.json` for Arjun exactly.
  This verifies one extraction, not extraction accuracy for all five resumes.
- Opened the actual completed result in Extraction Review, selected the full-name
  field, viewed the original PDF and downloaded the saved JSON through its UI link.
  The saved extraction remained available after container rebuild/restart.
- No usable field evidence was returned. Review now explicitly displays:
  “No verified field evidence was returned. Check these values against the original
  document before using them.” This notice was verified on the real saved result.
- Fixed the former 600-second form/backend cap. The deployed Model Registration
  UI successfully saved 1,200 seconds and displayed its success notification.

CPU result ID: `61f29a27-37eb-4fa8-a878-c778b0818c0e`.
Screenshot: [CPU result review](../../ags_runtime/ags_archive/ags_cleanup_2026_10_14/ags_docs/ags_testing/cpu-resume-review.jpg).

## Hardware/startup verification

The initial full browser flow ran in the CPU-only Ollama container. The host has
an RTX 3050 6 GB GPU. A disposable probe using the same pinned Ollama image passed
with Docker's NVIDIA device allocation; host inventory alone was not used as proof.

Executed `local/ags_scripts/start-oracle.ps1 -Hardware Auto`: existing private credentials
were preserved, GPU was selected by the container probe, the stack became healthy,
models were present/pulled, and real JSON-generation/embedding smoke checks passed.
Ollama reported **2,874,062,929 bytes** of model GPU offload. Startup smoke timings:
generation **24.481 s**, total including embedding **38.747 s**. The earlier cold
GPU smoke took 117.707 s for generation, 162.4 s total. These tiny smoke timings
cannot be compared directly with the full CPU resume extraction.
After the diagnostic interruption and final rebuild, the bounded smoke passed
again: generation **31.825 s**, total **43.351 s**, with the same observed offload.

An additional diagnostic attempted forcing CPU inference inside the GPU-enabled
daemon. It stalled during hardware/model switching while Windows free physical
memory fell to about **13 MB** on this 16 GB laptop. It was interrupted by restarting
only Ollama; that diagnostic did **not** pass. The final smoke command follows the
container's selected hardware rather than switching it during inference. Its tiny
generation/embedding requests each have a 180-second limit. CPU inference still
requires adequate available RAM; no claim is made that a colleague's different
CPU or memory load will match this laptop's timings.

Hardware-selection regression checks passed for accessible GPU, absent GPU/Auto
CPU fallback, forced CPU without probing GPU, and explicit unavailable GPU errors.
The Auto startup path also retries CPU if GPU startup/inference smoke fails, using
the same data/model volumes. That failure branch was code-reviewed; a live device
failure after successful selection was not deliberately induced.

## Deployment and checks

- Frontend attachment unit suite and existing focused backend suites passed;
  production frontend builds/type checks passed.
- Model Registration API regression verifies 1,200 seconds is saved/pinned and
  values above 1,800 are rejected. Global settings now accept the same CPU budget.
- PowerShell scripts parsed; shell startup and Oracle account scripts passed
  `bash -n`. Base and NVIDIA Docker Compose configurations passed parsing.
- Kubernetes CPU/GPU Kustomize configurations rendered. Kubeconform strict
  validation against Kubernetes 1.34 checked **36 resources**, all valid, none skipped.
  CPU manifests contain no GPU allocation; the overlay requests one NVIDIA GPU
  only for Ollama. Rendering Auto without a configured cluster warns and uses CPU.
- The Kubernetes init module ran successfully inside the existing Docker backend:
  real Oracle application-account query, Qdrant/Ollama reachability and installed
  local models. This does not validate Kubernetes mounting, networking or startup.

Still requires OKE evidence: image registry access/architecture, Secret setup,
server-side dry-run/RBAC, storage class/PVC permissions, node memory/CPU capacity,
Oracle startup, model download egress, NetworkPolicy enforcement, GPU device-plugin
and scheduling (if enabled), ingress configuration, full browser workflow and
persistence/backups on the actual cluster. See [Kubernetes instructions](https://github.com/Maniatramco/Aegis/blob/aegis-freeze-2026-10-15/ags_docs/KUBERNETES.md).

Changes are in the working tree of `feat/aegis-assistant-oracle-docker`; no new
commit/push was requested or performed for this task.
