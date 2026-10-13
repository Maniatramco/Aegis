# Single merged extraction with all source records

The earlier three-resume result used the supplied ONE-resume template on all
three documents at once. Its scalar full_name field could represent only one
candidate. Saved historical results are retained; rerun through Assistant to
create a corrected result.

Assistant now asks Single extraction (merge files) or Independent extraction.
Single defaults to different profiles/items: apply the selected original schema
to each source separately, then assemble one schema-validated records array under
one extraction ID. For fragments of the same item, choose Parts of the same
profile or item to retain combined-context extraction with one object. Each
source follows the template, including its field/list limits; this is not a
guarantee of model accuracy or arbitrary entity discovery within one source.

New merged uploads concatenate all PDF pages into one PDF, create/index one
dataset document, and retain unchanged original bytes and source boundaries.
Mixed-format merges produce UTF-8 text with named source sections. Metadata
records every filename, byte size, source count and page/section mapping.
Downloads provide both the merged file and individual originals. Existing
indexed selections also get a named downloadable merged extraction asset,
without replacing the existing catalog originals.

Assistant, extraction history and Review show extraction IDs. Review retains
the merged filename when switching originals, lists included files, displays
all profile names and fields, and associates each record with its original.
JSON exports retain merge metadata. Saved result validation prevents dropping
source records or changing their recorded source keys/filenames. Verified
quotes retain original and merged page information; unverified export provenance
is restricted to the record's actual source rather than every merged source.
Interrupted record generation retains completed source work for worker job
retry; a workflow failure is not reported as complete. Explicit re-extraction
clears cached source results so it actually calls the model again.

## Actual local Docker/browser verification

- Dataset: Resume flow QA 2026-10-10 (fictional data).
- Attached Arjun, Meera and Nikhil PDFs in Assistant; typed extract.
- Confirmation was disabled until the template and mode were selected.
- Selected Single extraction, Different profiles/items (default), and the
  existing resume-extraction-prompt.json. One confirmation ran the workflow.
- Composer cleared; original filenames remained alongside the sent question.
- One catalog document: 6b7bebf9-182d-45f6-9193-8b3584adec37.
- Merged filename: merged-01-arjun-rao-backend-3-files-07b2544e.pdf.
- Downloaded merged PDF through the UI: three pages, with the corresponding
  Arjun Rao, Meera Iyer and Nikhil Shah names present on their original pages.
- Extraction ID: 6efc597a-01e6-445a-9372-aa7e2578f686.
- All three complete field objects exactly matched manually specified expected
  sample results. Extraction submission to saved result: 133.90 seconds.
- Runtime observed: qwen3:4b, 100% GPU, context 8192. This is this laptop's
  measured time, not a CPU or universal performance claim.
- Assistant displayed 3/3 source records, completed status and Review button.
- Opened Review; all three full_name inputs and source filenames were present.
- Selecting Nikhil's and Meera's fields selected the corresponding retained
  original PDF; the review title continued to show the merged filename.
- Downloaded Nikhil's original through Review and verified its SHA-256 matches
  the input file exactly.
- Rebuilt/restarted application containers, reloaded the browser, and reopened
  the persisted result from history by its merged name/ID. All three profiles
  and retained source options remained available.
- No verified field quotes returned (0). Review correctly warns that the values
  must be checked against originals; source membership is not field evidence.

## Checks and deployment boundaries

- Backend agent/multi-file/review checks: 36 passed before the additional
  provenance check. Final merged-document suite: 6 passed; other review checks
  passed. Covered independent failures, exact upload scope, ownership, original
  byte retention, actual PDF pages, per-source isolation, immutable provenance,
  complete record count, partial job recovery and local schema references.
- Frontend unit suite: 94 passed; final Review/progress subset: 22 passed.
- TypeScript and final Docker production build passed; Compose startup healthy.
- Same application containers/shared data storage are used. No new GPU or
  laptop dependency was added. CPU/GPU selection configuration is preserved.
- This new three-profile browser run used GPU. Earlier CPU evidence remains
  in assistant-resume-2026-10-10.md; the new merged run was not timed on CPU.
- No live OCI/OKE deployment was performed. Cluster validation remains required
  as described in ../KUBERNETES.md. Latest code is uncommitted/unpushed.

Proof: merged-three-assistant.jpg and merged-three-review.jpg.
