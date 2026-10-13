# Extract Data

Open **Onboard → Extract Data** to view the latest saved revision of completed extractions as a table. Dataset and Prompt template filters apply to both the table and exports. Exactly one prompt template is selected at a time; the first available template is selected automatically. All datasets includes only records the signed-in user can access. Without an available prompt, no results are fetched and export is unavailable. Both API endpoints require a non-empty prompt template ID.

Each extraction is one row, or one row per extracted record for multi-record results. Nested objects become field columns. Arrays stay in a single cell to avoid duplicating records. String arrays display as readable lists; exports preserve JSON array content. Missing values display as a dash, while zero and false retain their values. Columns are the union of the selected results' fields.

The table displays 25 records per page, with a sticky document column and scrolling contained inside the table. Excel, CSV and JSON exports include **every row matching the filters**, including extraction IDs, saved version, prompt version and review status. CSV protects against spreadsheet formulas; Excel uses inline strings. JSON preserves types. Equal column labels are disambiguated in spreadsheet exports.

Review opens the existing separate Review page. Back to Extract Data retains both filters and the current page. Saved Review edits appear after returning; the table never includes unsaved drafts.

FastAPI endpoints:

- `GET /api/extract-data?dataset_id=...&template_id=...&offset=0&limit=25`
- `GET /api/extract-data/export?dataset_id=...&template_id=...&format=xlsx` (also `csv`, `json`)

Both endpoints enforce the existing dataset grants. Result values are read from verified persisted Parquet (OCI or local, according to the recorded object location); legacy JSON revisions remain readable. An unreadable selected result blocks the report instead of silently returning a partial export. No model or vector query is needed for this screen.
