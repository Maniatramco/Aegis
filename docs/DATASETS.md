# Dataset-first workflows

A dataset is the boundary for document onboarding, retrieval, and model eligibility. Existing knowledge-base IDs remain stable; the API retains compatibility routes, while the interface uses the clearer dataset terminology.

## Home and dataset activity

Home is the default after sign-in. It shows only the signed-in owner's registered datasets as responsive cards, each with an explicit **Active** or **Inactive** label. Open a card to reach that dataset's documents and model settings; its URL and browser Back/Forward retain the selected dataset. Operational metrics remain in Dashboard.

Dataset activity is a persisted configuration flag, independent of document indexing or model readiness. New and legacy datasets default to Active. Use **Deactivate dataset** or **Activate dataset** in the dataset details to change it. Inactive datasets remain visible, and their originals, model configuration, and historical results remain available. New processing, questions, extractions, and job retries are blocked; already accepted work may finish. Reactivation does not invalidate a compatible index.

The API exposes `active` on `/api/datasets` and dataset detail responses; `PATCH /api/datasets/{id}/status` accepts `{ "active": false }` (or true). Status changes use the existing versioned storage configuration and preserve model mappings, index generation, and ownership. No new database configuration column is needed.

## The intended journey

1. **Connect providers.** Configure a connection in Connections and save a named connection profile. Provider credentials stay encrypted on the server. A profile is a versioned configuration and credential reference, not a browser API key.
2. **Register models.** Give each model a recognizable name, choose its connection profile and model identifier, and enable the capabilities it supports. Multiple models can share a connection. Capability declarations do not prove the remote account has access to that model.
3. **Onboard a dataset.** Name the dataset, describe its contents, and configure its model mappings. Choose chat and extraction defaults, plus the single indexing/embedding configuration used by this dataset's index generation.
4. **Upload documents.** Original PDF, DOCX, and TXT files are retained in configured content storage. Wait for indexing to complete before using those documents.
5. **Ask or extract.** Select a dataset first. Each screen offers only the enabled models mapped for that operation. With several eligible models, choose one from the model dropdown. With none, follow the configuration guidance rather than silently using a workspace model.

Physical storage and job transport remain deployment-level settings. A dataset does not silently move objects to another bucket or database. Use the documented migration procedure for a storage cutover.

## Configuration and provenance

Dataset metadata, mapping configuration, model definitions, and run artifacts are stored through the storage abstraction; the database retains identity, ownership, reference, and status records. Mappings reference shared connection profiles rather than copying secrets into dataset metadata.

Every request is checked on the server: dataset ownership, document membership, model capability, mapping eligibility, and enabled state. Choosing an identifier manually in a browser request cannot expand the source scope or model permissions.

An accepted run records the selected model and a configuration snapshot. Later edits to the model catalog or connection settings must not silently change a queued extraction or an in-flight answer. Recorded history identifies the model used for each run; changing the current dropdown does not rewrite earlier responses.

Index embeddings are a separate choice from chat and extraction models. A dataset has one compatible embedding/index configuration per generation. Changing it requires rebuilding the affected document indexes before retrieval can use them. Never mix vectors from different embedding spaces.

## Existing workspaces

Existing documents and conversation/extraction artifacts are retained. Review and explicitly migrate legacy dataset settings before starting new runs. This makes the previously workspace-wide configuration visible as a dataset mapping instead of guessing a new model selection. Previously completed responses retain their recorded content; old artifacts may lack model provenance because it was not recorded at the time.

## Limits and safety

- PDF/DOCX/TXT parsing and existing OCR limitations are unchanged.
- Dataset model mappings do not grant remote provider credentials, quota, or model access.
- External-processing consent applies to the selected provider configuration and the source/query content it will receive.
- Mock models remain explicitly marked as test output. Multiple mock catalog entries demonstrate routing and UI behavior, not real model quality.
- Live OpenAI and OCI verification requires the operator's own credentials and provisioned resources.

### Upgrade checklist

1. Open each existing dataset and use **Import current settings** when it is marked as needing migration. This creates explicit shared catalog entries and a saved profile for the old workspace configuration.
2. Review defaults and the embedding mapping. Reindex existing documents so their index records carry the dataset generation and compatible model fingerprint.
3. Assign any legacy documents without a dataset to a dataset, then reindex. Assignment retains the original files; cross-dataset moves are intentionally not implicit.
4. Submit new jobs for any legacy queued work that has no immutable execution snapshot. Such work fails with an actionable message instead of guessing which current provider should receive it.

The compatibility API keeps `/api/knowledge-bases` as an alias. New integrations should use `/api/datasets`, `/api/models`, and `/api/datasets/{id}/models`; generation requests send `dataset_id` and an eligible `model_id` (or use the dataset's validated default).
