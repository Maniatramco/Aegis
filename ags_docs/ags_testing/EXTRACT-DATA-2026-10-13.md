# Extract Data verification — 13 October 2026

Implemented a separate **Onboard → Extract Data** screen with dataset and prompt filters, saved result fields as columns, pagination, and all-filtered-row Excel/CSV/JSON exports. Review remains separate, with Back retaining the filters.

Validation:

- `pytest ags_backend/ags_tests/test_extract_data.py ags_backend/ags_tests/test_review_workflow.py -q`: **13 passed**. Covers latest saved Review revisions, dataset/prompt filtering, unauthorized access, merged records, nested fields, arrays, zero/null values, pagination, exporting beyond the visible page, spreadsheet formula protection, corrupt Parquet and invalid request parameters.
- Focused table tests repeated after column-label collision repair: **5 passed** (included in the above 13).
- Final Docker production build, including TypeScript validation: passed. API and web deployed locally with the existing OCI configuration.
- Chrome browser: all-results table showed three existing saved extractions. Resume Agent Verification + resume-reextract-v2.json returned exactly one row with Maya Rao and B.Tech in Computer Science. Each export action returned from Exporting without an application error. Review opened the matching extraction; Back to Extract Data preserved both filters and the single row. Table scroll stays inside its own container, with no page width overflow.
- Read-only live OCI route verification (`verify_extract_data.py`) validated the table and all three export response bodies. JSON retains typed values; CSV contains the expected qualification; Excel has one header and one data row containing that qualification. No live fixture was edited or re-extracted.

Live result: dataset `36fe2487-eaa3-5132-a9bd-12fdb48bcc52`, prompt `4250d382-62c3-4f0e-a6bd-4036938bbd87`, extraction `220d33d7-b58c-43eb-a22c-35de309acde8`, revision 1.

Verified saved Parquet: `extraction/220d33d7-b58c-43eb-a22c-35de309acde8/results/v1-221adb10f1d868f0.parquet` (recorded OCI object location).

Export response sizes: JSON 2,431 bytes, CSV 552 bytes, XLSX 2,021 bytes. Browser download-event capture timed out; response contents were therefore checked independently through the live configured FastAPI routes. The internal test authentication override runs only in the isolated verification process; the serving API keeps its authentication and dataset grants.

Screenshot: `results/extract-data-2026-10-13/extract-data.png`.

## Single-prompt follow-up

Removed All prompt templates. The first available prompt is selected automatically and the table never requests results without a selected prompt. Listing and export APIs reject missing or empty template IDs. Tests updated to require a single prompt and prove that a second prompt's results are excluded: **6 focused tests passed**.

Browser verified automatic selection, switching to the original prompt (one row with its original columns), switching back to the re-extraction prompt (one row with highest qualification), and the dataset-scoped dropdown containing only the two actual prompts. A cold workspace metadata request timed out after restart; refreshing subsequently returned dataset metadata successfully. Final screenshot: `results/extract-data-2026-10-13/single-prompt.png`. Production build/type validation passed.
