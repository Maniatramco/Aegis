# Aegis

Aegis turns documents into searchable knowledge and structured, reviewable results. It uses a Next.js/React interface, FastAPI, LangGraph agents and a durable Python worker.

**Handover branch: `ags_sprint1`. Current working version: `v26.1.12.16` (base: `v26.1.0.0`).** The original source freeze remains tagged `aegis-freeze-2026-10-15`; use the handover branch for subsequent updates.

v26.1.12.16 turns Jobs & activity into a monitoring view showing who started each job (usernames for administrators only), its dataset, timing and progress, with activity by person and filters. Publication is recorded separately.

v26.1.12.15 redesigns the workspace screens: Aegis Agent opens as a workspace with / commands and a live activity icon; every screen has a brand page band and summary counts; Need attention counts open a pop-up with the failure and its fixes; buttons follow one compact standard; About shows the golden-copy workflow. v26.1.12.14 adds the Dashboard overview and Add knowledge from cloud storage. Publication is recorded separately.

v26.1.12.12 completes the administrator Files & processing screen with source storage, indexing, OCR and extraction status, current-model recovery, and confirmed end-to-end document cleanup. Listing compares saved index/model mapping metadata without contacting model services; timed refreshes wait for an existing read to finish. Processing submissions still validate current models. Cleanup removes related results and affected chats/workflows while preserving other originals and shared prompts/models. Partial failures remain quarantined and can resume. Content-free terminal queue audit rows remain for delayed notification acknowledgement. Includes visible Save and New extraction buttons. Publication is recorded separately.

v26.1.12.9 uses the dataset's current mapped models for new Re-extract, prompt Resume and Reindex submissions. Changed OCR selections make scanned source indexes stale so Review re-extraction rebuilds them with the current embedding/OCR selections before extracting. Accepted jobs keep their submission snapshot. Historical retries cannot replay outdated mappings or overwrite a successful index/result; use a fresh Reindex/Re-extract instead. Earlier results and originals are preserved.

v26.1.12.8 completes cloud-only OCR with OpenAI-specific image tile estimates and the registered cloud model's context limit. Landscape pages no longer inherit the smaller local OCR context cap. Original inference pixels, rendering limits and pre-inference budget rejection are retained. Publication and live recovery are recorded separately.

v26.1.12.7 makes dataset OCR cloud-only. Model Mapping offers compatible OpenAI/Gemini registrations and Automatic cloud extraction routing, removes the local option, and rejects local OCR saves. New dataset jobs never contact local Ollama for OCR; scanned content without an eligible cloud selection receives an actionable mapping message. Native text and existing embeddings remain available. Publication and live recovery are recorded separately.

v26.1.12.6 adds an independent OCR selector to each dataset's Model Mapping screen. Choose an eligible OpenAI/Gemini extraction registration, Automatic or the configured local OCR service. The selected model is enabled and pinned for subsequent indexing jobs without changing embedding selection or index generation; reindex a document to read its images again. Existing datasets keep Automatic and older mapping clients preserve a saved explicit OCR choice. Prepared locally; publication and live acceptance are pending.

v26.1.12.5 uses a dataset's saved GPT-4o or GPT-4o Mini extraction connection for OCR of scanned PDFs and embedded Word images. OpenAI OCR is explicitly disclosed before processing, jobs pin the model and credential-profile version, and cloud failures do not fall back to laptop Ollama. Embeddings remain a separate text-only step; no dataset embedding mappings are changed by this release. Prepared locally; publication and live acceptance are pending.

v26.1.12.4 routes broad knowledge-base summaries to read-only chat over the selected dataset/document scope. Short requests such as “summary” use model routing rather than assuming a prior extraction answer. Original-only and saved-result summaries remain distinct; all grounded answers retain hybrid retrieval, reranking and citation validation. Published and verified as described below.

**Verified live application: v26.1.12.13, published 26 October 2026 (Asia/Calcutta).** Release `release-20261026-171250-d8fe09` deployed commit `bc4c5ccc501f3f7db6646f0c3b17fb1324190555` (frontend only) to the existing Mumbai application. The web rollout, configuration checks, HTTPS and the served v26.1.12.13 version passed; backend images, database (DB_Object=N), settings and data are unchanged. The live sign-in page was checked at 1440 and 390px: animated banner, frosted form card with live identity, form-first order and no horizontal overflow. No sign-in, inference or data writes were run. See CHANGELOG.md for the image digest.

**Previously verified: v26.1.12.4, published 24 October 2026 (Asia/Calcutta).** Release `release-20261024-161248-210e60` deployed commit `c6a33d0f238563d1c951dd76c317ed78a7577c1d` (tag `v26.1.12.4`) to the existing Mumbai application. Both rollouts, exact-receipt/configuration/schema verification, HTTPS, all five public assets and the live version passed. The exact reported summary question passed in fresh Balance Sheet Agent conversations with GPT-4o and GPT-4o Mini, with completed hybrid retrieval, reranking, generation, citation validation and working source evidence. Existing settings, mappings and stored data were preserved; DB_Object=N and no scripts or infrastructure changes. See CHANGELOG.md for exact images, receipt and test limits.

v26.1.12.3 lets administrators enable multiple Chat and Extraction models per dataset while keeping one default per role. Changing a default preserves alternatives, and selected defaults cannot be disabled. Both GPT-4o and GPT-4o Mini are now enabled for Chat and Extraction on all five existing datasets. Save/reload and both workflow selectors were verified for every dataset; existing defaults, other role choices, embeddings and index generations were preserved. Validation passed 246 frontend tests, both TypeScript checks, the exact pinned ARM64 image build and synthetic desktop/mobile browser checks. No new full-document inference or extraction-quality guarantee is claimed. See CHANGELOG.md for exact images, receipt and test limits.

v26.1.12.2 fixes OpenAI/Azure routing arguments and original/semantic evidence selection. Three live GPT-4o Mini questions in the deployed Agent screen passed against the existing synthetic SWIFT Alliance Demo dataset: broad, named-file and explicit semantic search. Each answer correctly stated that the network ACK does not confirm settlement or beneficiary credit, with a working citation to the original indexed ACK passage. Hybrid retrieval, reranking, model generation and answer validation completed. Earlier local validation passed 216 focused backend tests, 239 frontend tests, both TypeScript checks and three real-model isolated Agent tests. This is targeted acceptance, not a full-suite or every-provider quality guarantee. See CHANGELOG.md for image digests and the exact receipt.

Version v26.1.12.0 adds direct Anthropic Claude Chat registration and native Messages API function calling. This change was deployed to the existing Mumbai application on 23 October 2026. Real-key acceptance is pending.

Version v26.1.11.0 rearranges the Dashboard into authorized datasets on the left, a larger Dataset Knowledge Chat in the centre and Sources on the right. Selecting knowledge keeps the panels visible; chat expansion is explicit. Smaller screens use panel view buttons while keeping chat mounted. This layout was deployed to the existing Mumbai application on 23 October 2026.

## Platform branding

Version v26.1.10.0 adds the supplied Aegis shield logo and platform banner. The sign-in page shows the full banner beside the form on desktop and below it on mobile. Header, navigation, password recovery and browser icons use the same platform logo; the separate Aegis Agent identity is preserved. This frontend was deployed to the existing Mumbai OCI application on 23 October 2026. Previous artwork is archived under `delete/ags_frontend/`.

Version v26.1.10.1 removes the repeated logo/tagline above sign-in and uses a navy page background matching the unchanged banner. The platform logo remains in the signed-in header/navigation, password recovery and browser icon. This adjustment was included in the deployed v26.1.10.2 release; no separate v26.1.10.1 deployment is claimed.

Version v26.1.10.2 uses the supplied shield for the shared Aegis Agent identity throughout the signed-in interface, including navigation, chat, welcome screens, guidance and the floating shortcut. Prior Agent artwork is archived under `delete/ags_frontend/public/`. It was deployed with the sign-in refinement to the existing Mumbai application on 23 October 2026.

Version v26.1.10.3 restores the white-toned sign-in background with subtle blue and cyan accents to coordinate with the unchanged banner. This correction was deployed to the existing Mumbai application on 23 October 2026.

The original platform branding is kept in one commit. To restore the preceding code and artwork while retaining history, run `git revert <branding-commit>` on a clean working tree (the commit titled `feat: add supplied Aegis platform branding (v26.1.10.0)`); check the resulting frontend and restart/rebuild it. `git revert <revert-commit>` reapplies the branding. Later edits to the same lines may require resolving a revert conflict. This change has no database or configuration migration.

## Dashboard chat view

Including indexed dataset knowledge opens a larger Dataset Knowledge Chat and collapses the dataset cards, Sources and guidance. The selected knowledge summary and **Add Dataset Knowledge** stay available. Use the source-panel icon to inspect or edit sources, and the expand/collapse icon to switch between the larger chat and full Dashboard. These controls have descriptive tooltips and accessible labels. Layout changes keep your draft, selected knowledge and conversation; opening chat sends no question automatically.

Frontend v26.1.2.2 was deployed to the existing Mumbai OCI application on 19 October 2026 from source commit `147adb9f9c7a5a1049061c8045953897a7011760`, release `release-20261019-192624-b8d433`. The production image, rollout, preserved configuration, HTTPS and seven live script assets passed; the served assets include v26.1.2.2. This approved Sprint1 frontend omits the separate governance screens. The existing backend, saved settings, database, models and data remain unchanged. Subsequent testing passed 19 authenticated live Dashboard checks, 15 isolated production-image browser/API checks and 53 focused backend regressions. The isolated chat path used real local retrieval/reranking with mock embeddings/answer generation. The native drag gesture remains unverified; no fresh live provider inference, live upload/extraction or full application browser suite was run. Private deployment/test evidence remains outside Git; see [CHANGELOG.md](CHANGELOG.md) for checks, limits, source fingerprint and image digest.

## Metadata Relationships

Open **Dashboard → Metadata Relationships** from the top-right of the Knowledge Source header. The graph opens on demand for the Dashboard's selected datasets and can include other accessible datasets, including inactive ones. It shows datasets, documents, extraction runs, saved prompt versions, review revisions and model mappings. Search records, explore categories, inspect connections, switch graph/list views and open an original document or extraction in Review. The graph uses Aegis blue and navy on a light canvas to match the Dashboard.

Drag any category or record node to arrange the graph; its connections and labels move with it. Drag the background to pan. Use the fit icon to bring the arranged nodes into view or the reset icon to restore the starting layout. A focused node also supports arrow keys, Shift for larger steps, Home to reset that node, and Enter/Space to inspect it. Scoped desktop/mobile arrangements stay separate and survive graph/list switches and refresh while the explorer remains open. These layout changes stay in the browser and do not update saved metadata. The node-layout enhancement introduced in v26.1.8.0 is included in the v26.1.9.0 frontend deployment.

Switch between category and record views. Double-click a record or use **Expand connections** to add its saved neighbours to the current scene; **Collapse expansion** removes that branch while preserving records shared with other branches. Pin positions before arranging as a network or lineage, highlight connected records by selecting or hovering, and use entity-type filters or the label icon to reduce clutter. Scroll over the canvas to zoom at the pointer. Expansions retain the selected dataset scope and are cancelled when the view or scope changes. The graph uses the bundled ISC-licensed D3 force layout; metadata stays in the existing catalog.

Frontend v26.1.9.0 was deployed to the existing Mumbai OCI application on 19 October 2026 from Sprint1 commit `63f6a4b55c6f17916bd865fc82fa6d32673727ef`, release `release-20261019-213637-0446f2`, image digest `sha256:5cd4d2250ec8837abb3c9ed79bfac4bd7a0e4f699bb6a2a3c1328f7d270ef0fc`. The frontend rollout, HTTPS, all seven initial script assets, preserved configuration and unchanged backend images passed verification. Twelve targeted read-only live graph checks covered loading, expansion/collapse, pinning, mouse/link movement, layouts, filters, focused records and emulated mobile controls/touch. No live inference or upload/extraction tests were run. See [CHANGELOG.md](CHANGELOG.md) for validation details and limits; private receipts remain under `ags_deploy/deployment-records/`.

The endpoint is read-only and does not run chat, inference, knowledge indexing or provider connection tests. Combined extraction lineage uses the saved document list. Current model mappings and pinned extraction model versions are separate links. Graph rendering is bounded; category totals and paginated matching records disclose larger scopes. Relationships come from the authorized metadata catalog and saved record snapshots, independently of the vector store used for knowledge retrieval. No new database tables or Neo4j service are required. Version v26.1.2.0 was published to the existing Mumbai OCI application on 18 October 2026 from commit `1280406c365de7b429ece2c989474110c34321b7` (release `release-20261018-111729-f3a940`). Web, API and worker rollouts, preserved configuration/schema, readiness and HTTPS checks passed. Private receipts are retained under `ags_deploy/deployment-records/`; no database DDL was performed.

## Start here

| Need | Maintained reference |
| --- | --- |
| Architecture, technology stack, workflows, approved Mural diagram and model placement | [Architecture handover PDF](ags_docs/Aegis_Architecture_Handover.pdf) or [editable Word document](ags_docs/Aegis_Architecture_Handover.docx) |
| Provisioning prerequisites and initial installation handoff | [OCI deployment guide](ags_docs/Aegis_OCI_Deployment_Guide.pdf), Section 1, pages 2-7 |
| Windows workstation setup, destination JSON, build and deployment commands | [Windows deployment README](ags_deploy/README.md); deployment PDF pages 10-11 and 15 |
| AI-assisted prerequisite setup and deployment | [Aegis deployment agent skill](.agents/skills/aegis-deploy/SKILL.md) |
| Database scripts and object release behavior | [Database README](ags_database/README.md) |
| Local development and runtime launchers | [Local-use README](ags_local_use/README.md) |
| Automated tests, fixtures and manual QA | [Testing README](ags_testing/README.md) |

The two PDFs above are the documents to share for architecture/technology and provisioning/deployment. Deployment PDF Section 2 (pages 8-18) includes the workflow on page 9, Windows and Cloud Shell instructions, component selection, approvals, verification and recovery. Provisioning and initial application configuration are separate from the code/object release scripts and deployment skill.

## Architecture diagram

GitHub renders this overview directly in the README. The approved detailed Mural diagram follows it.

```mermaid
flowchart TB
    Browser["User browser"] -->|HTTPS| LB["OCI load balancer"]
    LB --> Web

    subgraph OKE["Existing OCI OKE application"]
        Web["Caddy HTTPS proxy / Next.js WebApp"] --> API["FastAPI / LangGraph agents"]
        API --> Chat["Unified Chat workflow"]
        Worker["Python processing worker"]
        Reranker["CPU reranker in the backend"]
        Chat -->|Reranks retrieved evidence| Reranker
    end

    subgraph Data["Existing OCI data services"]
        DB[("Oracle Database: application records, SQL job queue and vector search")]
        Storage["Oracle Object Storage: originals, JSON and Parquet results"]
    end

    API -->|Approved processing jobs| DB
    DB -->|Claim queued jobs| Worker
    Worker -->|Save status and searchable knowledge| DB
    API <-->|Read and write files| Storage
    Worker <-->|Read originals and save results| Storage
    Chat -->|Scoped hybrid retrieval| DB
    Chat -->|Model calls| Models["Configured model endpoints: Gemini on GCP, local Ollama or other mapped providers"]
    Worker -->|OCR, embeddings and extraction| Models
```

Original Aegis Agent Unified Chat and Dashboard knowledge-grounded answers follow **scope/access checks -> hybrid retrieval -> CPU reranking -> model generation -> answer and citation validation**. Dashboard greetings, small talk and clearly self-contained general questions use the selected Chat model directly, without a knowledge lookup. Processing jobs retain their confirmation and external-data consent requirements. Model providers follow saved dataset mappings; the diagram does not imply all providers are running or required.

### Approved detailed architecture

![Aegis component architecture showing OCI services, web application, FastAPI and worker, AI providers, database and storage](ags_docs/assets/aegis-architecture.png)

[Open the full-resolution diagram](ags_docs/assets/aegis-architecture.png). This is the approved Mural diagram reused from the [architecture handover](ags_docs/Aegis_Architecture_Handover.pdf). Its provisioned-services configuration snapshot is dated **15 October 2026**; cloud provider blocks show supported hosting alternatives. Effective model connections follow each environment's saved dataset mappings.

## Prerequisites before deployment

The normal Windows workflow is **Setup-Aegis.ps1, then Deploy-Aegis.ps1**. Have these ready first:

- An open Windows PowerShell 5.1 or newer window and a local Aegis Git checkout with saved, validated source files.
- App Installer / WinGet and internet access for missing tool installation. For application releases, a workstation that supports Docker Desktop Linux containers, installer/UAC access when required, and at least 10 GiB free on the source/work drive. Actual images/builds can require more space.
- An **existing prepared OCI environment** with compatible Aegis workloads, database access, persistent state, storage, Secrets, required model/reranker assets and HTTPS routing as applicable. A bare OKE cluster or new tenancy is insufficient.
- Your destination's usable kubeconfig/context, authorized OCI authentication and registry access; a database wallet and authorized credentials when database objects are selected.
- A filled private destination JSON and truthful test/CI evidence for the source being released. Keep passwords, tokens, private keys and wallets out of Git, JSON, command arguments and logs.

Normal setup reuses working tools and installs supported missing Git, Python 3.12, kubectl and Docker Desktop through WinGet as applicable. It creates a missing project `.venv`, installs an isolated OCI CLI if kubeconfig authentication needs it, and the pinned Oracle driver for database object releases. WSL/Docker setup, private login, UAC and restart prompts can require operator action. It cannot provide credentials, grant OCI access or create the destination resources. It does not restart Windows automatically.

Setup does not clone the repository. If Git is needed before cloning, follow the [manual tool installation commands](ags_deploy/README.md#manual-reference-install-missing-workstation-tools), install Microsoft's App Installer first if WinGet is unavailable, then reopen PowerShell. Local Node/npm installation is needed for local frontend development/testing, while deployment installs application dependencies inside the maintained Docker images.

## Windows quick start for a colleague

### 1. Obtain the source

If you do not already have a checkout, run in a directory where a new `Aegis` folder can be created:

```powershell
git clone --branch ags_sprint1 https://github.com/Maniatramco/Aegis.git
Set-Location .\Aegis\ags_deploy
```

For an existing checkout, open its `ags_deploy` folder instead. Review any saved local changes before deploying; do not overwrite the checkout or reset someone else's work.

### 2. Prepare your environment's private JSON

Run from `ags_deploy`. Create the destination file from the [clean non-secret template](ags_deploy/templates/deployment-inputs.example.json), then edit it:

```powershell
New-Item -ItemType Directory -Path 'C:\aegis-target' -Force
if (-not (Test-Path -LiteralPath 'C:\aegis-target\colleague-oci.json')) {
    Copy-Item -LiteralPath '.\templates\deployment-inputs.example.json' -Destination 'C:\aegis-target\colleague-oci.json'
}
notepad 'C:\aegis-target\colleague-oci.json'
```

Fill the local source path (or leave `SourcePath` blank), component selections, destination kubeconfig/context/namespace, registry, platform, public URL and validation evidence. Fill the database identity/wallet fields when `DB_Object` is `Y`. Use your own prepared environment's values and credentials. The template initially selects database objects and both application components; review every `Y`/`N` before running it. See the [field descriptions and component examples](ags_deploy/README.md#prepare-the-target-json).

Keep a separate private JSON for each tenancy/cluster. Use the **same file on both commands** below. If `-Inputs` is omitted, the scripts use the ignored `ags_deploy/aegis-oci-inputs.json` beside them. Filled destination files are private operator state, not distributable templates.

### 3. Run prerequisite setup

```powershell
.\Setup-Aegis.ps1 -Inputs 'C:\aegis-target\colleague-oci.json'
```

Complete installation/credential prompts and type `CONNECT` when asked to authorize remote read-only checks. Setup checks the selected source, tools, target access, registry metadata and schema/configuration as applicable. It does not build or publish images, apply database DDL, update workloads or run application regressions.

Continue only after successful completion prints **`AEGIS_PREREQUISITES_READY`**. If setup stops, inspect its exact printed report, resolve the stated issue and rerun the same setup command. Complete any requested Windows restart yourself before retrying. The marker confirms checks at that time; it does not guarantee image build, registry push or rollout success.

### 4. Build and deploy

```powershell
.\Deploy-Aegis.ps1 -Inputs 'C:\aegis-target\colleague-oci.json'
```

The release performs **CONNECT -> preflight -> selected image builds -> saved plan -> PUBLISH -> release -> verification**. Review the exact source, destination, images, database action and restart impact in the printed `plan.json` before typing `PUBLISH`. There is no additional manual application build command. Setup and deployment never auto-answer approval words.

## The two Windows invocation methods

Both methods use the same prerequisite setup, target JSON and maintained release workflow. Run from `ags_deploy`; choose one release command per run.

| Method | Optional read-only release preflight | Build and release |
| --- | --- | --- |
| Main script | `.\deploy.ps1 -Inputs 'C:\aegis-target\colleague-oci.json' -CheckOnly` | `.\deploy.ps1 -Inputs 'C:\aegis-target\colleague-oci.json'` |
| Shortcut scripts | `.\Check-Aegis.ps1 -Inputs 'C:\aegis-target\colleague-oci.json'` | `.\Deploy-Aegis.ps1 -Inputs 'C:\aegis-target\colleague-oci.json'` |

The shortcuts call `deploy.ps1` and pause so the result can be read. A release already includes target preflight; a separate `Check-Aegis.ps1` invocation is optional. `Setup-Aegis.ps1 -CheckOnly` checks prerequisites without installing tools, creating a virtual environment, starting Docker or performing registry login; it still requires permission for remote read-only checks and writes local reports.

## Saved source, component selection and database behavior

Each normal Windows release snapshots saved local application/database source and the maintained release helper, including non-ignored new files and saved deletions. No Git commit or JSON `Ref` update is required. Private state, credentials, ignored new files, generated output and the `delete/` archive are excluded. The plan records `source_mode: working-tree`, the base commit, snapshot fingerprint and `source-manifest.json`; the saved snapshot is the actual build input. Save and validate intended edits before starting. Later edits go into a subsequent run.

Each invocation runs the selected Docker builds; unchanged layers may use cache. Saving a file alone does not trigger a deployment. For an explicitly committed-source release, add `-CommittedSource` to both setup and deployment; only that mode exports the JSON `Ref` and excludes uncommitted edits.

| Release | `DB_Object` | `DeployFrontend` | `DeployBackend` |
| --- | --- | --- | --- |
| Frontend and backend code, no database DDL | N | Y | Y |
| Frontend only | N | Y | N |
| Backend API and worker only | N | N | Y |
| Database objects only | Y | N | N |

All N is rejected. `DB_ReleaseFile` normally selects [ags_database/release.json](ags_database/release.json). Matching objects are preserved, listed supported missing objects can be created after approval, and incompatible existing definitions stop the release. The file can explicitly permit a missing app user/schema inside the existing database; show its grants/quota and objects in the final plan before approval. Existing accounts, settings, objects and data remain intact. This is not infrastructure provisioning, a data import or an arbitrary migration runner.

Database-only releases do not require Docker or Kubernetes. With database objects disabled, a backend release still needs read-only schema compatibility and active-job checks; frontend-only releases make no Oracle queries. Use private password prompts. A backup reference is optional and is not required or prompted for.

## Deployment agent skill

The shareable agent skill is included in this repository at [.agents/skills/aegis-deploy/SKILL.md](.agents/skills/aegis-deploy/SKILL.md), with its [agent metadata](.agents/skills/aegis-deploy/agents/openai.yaml). It covers workstation setup, private target inputs, saved-source builds, plan approval, verification and failure handling. Ask your agent:

> Use the repository's aegis-deploy skill to prepare my Windows prerequisites, verify the destination in my private target JSON, and build and deploy Aegis after I approve the exact release plan.

Give the agent your actual checkout and private JSON paths; provide secrets through private prompts rather than chat. Approve read-only connection scope and the exact publication plan separately. The skill uses the same maintained scripts and prepared-resource boundary as the manual route. The [aegis-release skill](.agents/skills/aegis-release/SKILL.md) covers source freezes and handover maintenance.

## Verify the outcome and handle stops

A completed application release prints `Release completed; configuration checks passed`, the application URL, exact receipt/record paths and exit code 0. A successful setup or `-CheckOnly` run is not a deployment. Database-only releases report their database result without claiming an application rollout. Retain the exact plan, result and receipt printed by that invocation; do not pick a guessed or latest record.

Setup reports are under `ags_runtime/deployment-setup/setup-.../result.json`; release records are under `ags_deploy/deployment-records/release-.../`. They remain ignored by Git. Read the [outcome and troubleshooting sections](ags_deploy/README.md#confirm-the-outcome) for commands and common failures, including missing approval, hidden/closed terminals and Docker/authentication issues.

Releases preserve infrastructure, configuration, model mappings, persistent state and unselected components. Selected Recreate deployments restart pods and can briefly interrupt service. On failure, inspect completed phases and actual images before proposing recovery. There is no automatic retry or rollback. Setup/deployment do not run regression, upload/extraction or model inference tests; supply truthful source validation evidence and run only authorized acceptance checks.

## Application version and Connections footer

The current version and in-app release notes are defined in [application-version.json](ags_frontend/app/application-version.json). The compact footer shows **Connections** and the current application version (**v26.1.12.0** in this source update); hover, focus or click Connections to inspect service details. AI model hosting is derived from authorized dataset defaults: Gemini is labeled GCP, Ollama Local, and mixed connections can show Local / GCP. This metadata is not a provider health test or a change to model registrations. Open **About** from the sidebar or click the footer version to see what each version includes. The project change history is maintained in [CHANGELOG.md](CHANGELOG.md); it distinguishes included code from a verified live deployment.

Dashboard opens a three-panel knowledge workspace with **Authorized datasets** on the left, a larger **Dataset Knowledge Chat** in the centre and **Sources** on the right. Dataset and source lists scroll independently; selecting knowledge keeps both side panels visible. Chat expansion is explicit. On smaller screens, Datasets, Knowledge Chat and Sources view buttons preserve the mounted chat and draft. This read-only chat is separate from **Aegis Agent V2**: it uses `/api/dataset-chat/*`, its own `dataset_chat` conversations and browser storage. It cannot create Agent plans, goals, uploads, extractions or re-extractions. The existing Aegis Agent keeps its original component, routes, selectors, tools and history; open it from navigation or the Agent shortcut for processing. Dataset cards set the dashboard chat scope, so no duplicate dataset selector is shown. **All accessible knowledge** supports questions across accessible datasets. Dashboard loads the dataset cards and sources first; chat initializes only after a dataset is chosen or **Open chat** is clicked. Opening Dashboard, opening chat and changing source scope never generate an automatic summary; model requests start only when the user sends a question. Greetings and clearly general questions get a brief model answer without resolving embeddings or searching knowledge. Mixed, dataset-specific, application-specific and uncertain questions keep the full grounded path. Direct replies are marked as general answers with no knowledge lookup or invented citations. **Add Dataset Knowledge** stays in the chat-panel toolbar outside the scrolling lists and conversation, including when Sources is collapsed. Use the dataset-card checkboxes to combine multiple datasets, or drag a dataset card onto Sources to include its accessible indexed files. Existing file exclusions remain excluded when adding a different dataset; stale, unindexed and inactive sources cannot be added. An empty selection stays empty. The picker supports multiple datasets and individual indexed files without uploading or duplicating originals. Retrieval rechecks grants, searches each embedding space separately, reranks evidence, generates the answer and validates citations. Empty file selections and revoked access cannot widen the scope. Each answer shows a compact status with distinct knowledge sources checked and cited. Expand it for the source-type breakdown and actual workflow details. Multiple passages from one document count once; saved results and dataset descriptions are separate knowledge sources. Counts describe retrieved evidence, not every file in the selected datasets. Sources can collapse. The continuous workflow guide remains below. The displayed page and navigation label is **Dashboard**, with existing Home links retained as aliases.

Dataset creation remains in the original Dataset workspace: use **Onboard → Dataset → New dataset** to open its existing inline onboarding form. The separate Onboard dataset page and navigation entry have been removed; its old URL resolves to Dataset. The original Aegis Agent onboarding, upload, extraction and re-extraction workflows are unchanged. Dashboard has no onboarding action.

## Additional OCI route and current limitation

The separate Cloud Shell route uses committed source, Linux paths and Podman. It is not one of the two Windows invocation methods above. See deployment PDF pages 16-17 for preparation and execution:

```bash
bash ./ags_deploy/cloud_shell/deploy-cloud-shell.sh --inputs ~/aegis-private/target.json
```

Add `--check-only` for read-only preflight. Native architecture, disk space, remaining Cloud Shell allowance, existing registry login and applicable private database wallet/driver must be checked. The route does not provision infrastructure or choose a paid fallback. OCI DevOps managed build runners are not enabled by these Windows/Cloud Shell scripts.

**Recorded Mumbai limitation, 16 October 2026:** the existing OKE API rules rejected the Cloud Shell public connection. Network settings were kept unchanged. This target requires an authorized connection that passes preflight before any publication; do not infer availability from this historical note or change firewall rules as part of a code release.

## Source layout, technology and validation

Application code lives in `ags_backend/` and `ags_frontend/`; native Oracle scripts in `ags_database/`; release/authentication helpers in `ags_deploy/scripts/` and `ags_deploy/ags_oke/`; local runtime options in `ags_local_use/`; and automated tests, fixtures and QA tools in `ags_testing/`. Preserve the [Unified Chat workflow](AGENTS.md): enforce scope, hybrid retrieval, reranking, generation and answer/citation validation.

The release Dockerfiles retain immutable Python 3.12.15 and Node.js 22.23.3 base digests and committed dependency locks. The OCI backend profile includes Oracle/OCI and native AWS/Google SDKs, with local in-process embeddings disabled. Existing model files, mappings, endpoints and runtime configuration are preserved. The architecture handover records observed technology versions and deployment placement; a documentation/GitHub push does not update the running application.

Use the maintained files linked above rather than superseded guide names. Any historical `delete/` archive stays outside builds and active test discovery. Private state, generated reports, wallets and release records stay out of Git.

For manual validation, follow [ags_testing/README.md](ags_testing/README.md). From the repository root with a supported project Python environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r ags_testing\backend\requirements.txt
.\.venv\Scripts\python.exe -B ags_testing\run_backend_tests.py
```

The backend runner uses temporary SQLite storage and mock providers in a child process. For frontend validation, install dependencies once with `npm --prefix ags_frontend ci`, then run:

```powershell
npm --prefix ags_frontend run test:unit
npm --prefix ags_frontend run typecheck
npm --prefix ags_frontend run build
```

These local checks do not deploy or establish live OCI/provider acceptance. Use the testing guide for deployment guard tests and opt-in integration checks; report actual results for the source being released.

### Direct Claude Chat setup (v26.1.12.0)

In **Model Registration**, choose **Anthropic · Claude (direct)**, category **Chat**. Enter the exact model ID provided by your API administrator and the API key. The base endpoint is `https://api.anthropic.com/v1`; this native protocol accepts only the official service host and needs no custom hostname allowlist. Supply the optional Anthropic workspace ID only if your key is not workspace-scoped. API keys are stored in encrypted, versioned connection profiles and are not returned to the browser.

Allow the small billed synthetic request, run **Test Connection**, then **Save Model**. The test requires a real, schema-valid tool call; a plain-text response does not pass. In **Model Mapping**, enable this Chat registration for the required datasets, **Save & Apply**, and select it in **Aegis Agent** or **Dataset Knowledge Chat**. New runs resolve the saved registration; in-progress snapshots retain their previous model/key version. Changing only Chat does not require reindexing. Keep the existing Embedding and Extraction models: this integration exposes Claude for Chat only. General-model and knowledge-model routing, authorization and citation validation retain their existing contracts.

The adapter uses the native [Messages API](https://platform.claude.com/docs/en/api/messages/create), pinned API version `2026-10-21`, with API-key authentication and optional workspace header. It uses automatic tool choice plus Aegis required-call/schema validation, rather than relying on model-specific forced tool modes. Sampling overrides are not exposed; this API version removes them ([version history](https://platform.claude.com/docs/en/api/versioning)). Native responses are validated before one completed text event is emitted; incremental Claude token streaming is not implemented. No new SDK dependency or global Anthropic environment key is required. Live credentials, quota, model access and real-provider quality must be verified with tomorrow's key; mock contract tests do not establish those.
