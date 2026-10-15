# Aegis OCI deployment record

Updated 14 October 2026. **WebUI, API and worker are running at https://aegis.92.4.67.183.sslip.io/ under the user's explicit trial-credit activation approval.** The chat-popup fix is deployed. No account upgrade or new infrastructure was performed. This is trial-credit operation, not a confirmed permanently cost-free deployment.

## Approved boundaries and account eligibility

WebUI, FastAPI and the worker run on OCI OKE. Qwen chat/extraction, Nomic embeddings and Qwen vision OCR remain on the laptop, reached through a private reverse SSH relay. The existing `agsora` database, Oracle vectors and `mk-aegis` bucket are reused. No account upgrade, paid substitute, additional node, autoscaler, GPU instance, local database deployment or data reset was performed.

The account reports `FREE_TIER` and is currently in a trial. The user authorized an actual creation attempt after the initial capacity report and post-trial uncertainty were explained. A subscription record ends on 10 November 2026 at 23:59:59 UTC; this does **not** prove permanent OKE eligibility. Recheck entitlement before trial expiry. Do not upgrade without the user's approval. Resource sizing fits the documented allowances, but a billing invoice of zero and continuing post-trial access have not been established.

Credit clarification checked read-only on **14 October 2026 at 10:58 IST**: the Organizations Subscription API confirms `payment_model=FREE_TRIAL`, `subscription_tier=FREE_AND_TRIAL`, lifecycle ACTIVE, currency SGD, and an ACTIVE promotion with amount **SGD 400.00**, duration 30 DAY, and `is_intent_to_pay=false`. The subscription starts October 12 and ends November 10 at 23:59:59.999 UTC (**November 11 at approximately 05:30 IST**). The SGD 400 commitment displayed by the user corresponds to this promotional credit; it is not a SGD 400 invoice or recurring Always Free allowance. OneSubscription balance APIs did not return an accessible balance (404/401); an exact remaining-credit balance was not independently confirmed.

The Usage API currently reports **SGD 0.106890434846** total computed usage since October 12. Arithmetic against the original promotion gives approximately **SGD 399.89 remaining**, but this is an estimate from delayed usage reporting, not a confirmed live credit ledger balance. Above-Always-Free eligible service use can consume promotional trial credits without establishing a permanent free deployment. The earlier pause protected the user's explicit lasting-free gate; it did not mean the trial credits were exhausted or that a credit-card charge had been established. This check made no account upgrade and did not resume the backend. Evidence outside Git: `subscription-detail.json` and `trial-credit-usage-check.json`.

## Services created and reused

| Service | Actual configuration | Verified state |
|---|---|---|
| Region | Mumbai, `ap-mumbai-1` | Existing home region |
| Cluster | `ags-aegis-basic`, Basic, Kubernetes v1.36.4, Flannel | ACTIVE; creation work request succeeded |
| Worker node | `ags-aegis-a1-node-pool`, one VM.Standard.A1.Flex, ARM64 Oracle Linux 9.8, 2 OCPUs / 12 GB | RUNNING, Kubernetes Ready |
| Node boot volume | 50 GB, 10 VPUs/GB | AVAILABLE |
| Application state | `application-state` RWO PVC, 50 Gi requested / 50 GB OCI volume | Bound / AVAILABLE |
| HTTPS state | `https-state` RWO PVC, 50 Gi requested / 50 GB OCI volume | Bound / AVAILABLE; certificates persist |
| Public load balancer | Flexible, minimum=maximum=10 Mbps, public IP 92.4.67.183 | ACTIVE; sizes checked through OCI API |
| Networking | `ags-aegis-vcn` 10.42.0.0/16, Internet Gateway, API/worker/LB subnets | Management ports restricted to laptop 49.206.14.107/32; public ports 80/443 |
| WebUI | One Next.js replica, existing /api proxy to internal FastAPI | Ready; public HTTPS sign-in and existing Mani login verified |
| API and worker | One shared Pod, API and worker containers, Recreate, shared state volume | Running, 3/3 containers Ready after approved resumption; laptop writers remain stopped |
| Caddy | HTTPS reverse proxy, Let's Encrypt, persisted certificates, streaming enabled | Certificate issued; HTTPS 200 and HSTS verified |
| SSH relay sidecar | Restricted remote-only key authentication; no shell or TTY; only remote port 11434 allowed | Reverse forwarding and denied shell/other port tested |
| Private OCIR | `ags-aegis-web`, `ags-aegis-backend`, `ags-aegis-ssh` | Private; all deployments pinned to image digests |
| Existing database | `agsora` / `ags_ora_db`, ADMIN, wallet alias agsora_low | Always Free; 20 GB; both autoscaling settings disabled; 13 tables and 5 users preserved |
| Existing vector knowledge | Oracle vector destination | Reused; no bulk copy, reset or reindex |
| Existing bucket | `bmyljaecivrj` / `mk-aegis` | Reused; current ObjectRead access retained as explicitly requested |
| Laptop models | qwen3:4b, nomic-embed-text:latest, qwen2.5vl:3b | Relay resumed; cloud /api/tags reports all three laptop models |
| CPU reranker | Existing /data/models/reranker | Copied with existing runtime state; runs in cloud API/worker |

No NAT gateway or additional local Oracle/Qdrant/model Pod was created. Combined boot and block allocation is **150 GB**. OCI reports registry layer sizes approximately 281,903,103 bytes backend, 90,951,308 web and 5,403,740 relay, including the original and consent-fix backend releases. Image counts include platform and attestation manifests; do not delete those by treating every untagged manifest as an unused release. Registry request charges/free consumption have not been independently metered.

## Image provenance

Application source starts from commit `7c200d7b203c65cb139919f0ffdd4d808db0c5de`, branch `python`. Deployment helpers, storage request reductions and the tested chat-consent correction are additional local changes. No existing PR was merged.

| Component | Immutable deployed reference |
|---|---|
| Web | `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:6d03a60f3c3ec47cad8a995af5319401ecd6dddd555425cd2761258c264368b0` |
| API / worker | `bom.ocir.io/bmyljaecivrj/ags-aegis-backend@sha256:4099fa958f6a3c1ad86eef2c94becb34c66b9add1fa331c97318627223f720af` |
| SSH relay | bom.ocir.io/bmyljaecivrj/ags-aegis-ssh@sha256:37189e82533c3e893f261b9735880e74f521f2ee6ce15f4490e3087ea1944870 |
| Caddy | docker.io/library/caddy@sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d |

API and worker share the ARM64 backend image. Database administration scripts are excluded. No dependency/model upgrades or downloads were performed. OCIR did not support the attempted repository immutability flag; the **deployment digest references**, rather than a repository setting, provide immutable release selection. Retain the active and one rollback release.

## Cutover and credential handling

The 14 existing jobs were completed before cutover. Laptop WebUI, API and worker were stopped before cloud application startup. The original laptop volume `aegis-oracle_storage` and images remain available for rollback. Ollama remains running on the laptop with its original image ID, GPU device requests and model-volume identity. Its only host publication is 127.0.0.1:11436.

Required runtime state was copied through an encrypted kubectl connection after stopping local writers. Snapshot size: 88,754,815 bytes; SHA256 `5a79fa0c1b96c2d859434b6f9019f27ac8400877de4a7e9b2e6678fabf6cf719`. Existing originals, JSON/Parquet objects and vectors stayed in OCI. Temporary lock and diagnostic files were excluded.

The existing master encryption key, OCI API key, database passwords and wallet are mounted using separate Kubernetes Secrets. They are absent from images, Git, the generated non-secret manifest and this document. Local secret artifacts and Docker registry credentials are in ignored `ags_runtime/ags_oke` paths with restricted Windows ACLs. The wallet mount remains /run/aegis-db/wallet and OCI configuration /run/oci/config.

## Model tunnel operation

For the daily manual pause and resume procedure, including job checks and both application Deployments, use [Aegis daily stop and start](AEGIS_DAILY_STOP_START.md). The commands preserve data and infrastructure; scaling application Pods down does not stop every OCI resource or guarantee zero cost.

For Console buttons instead of application scaling commands, use [Aegis stop and start through the OCI portal](AEGIS_PORTAL_STOP_START.md). It identifies the existing worker VM and describes graceful Stop/Start, preserved data and restoration of the separate laptop model tunnel. This documented procedure has not been executed as an additional live test.

The running hidden PowerShell relay uses `local/ags_scripts/start-oke-model-relay.ps1`. It pins the SSH server host key and reconnects after failure. Remote endpoint remains `http://ollama:11434`; the local destination is 127.0.0.1:11436. Public Ollama access is not enabled.

The prior stop flag was archived after the user approved ongoing trial-credit operation, and renderer state now records application_paused=false. When restarting the laptop connection, keep Docker/Ollama running and use this relay command from the repository (avoid starting a second relay while the existing hidden process is active):

```powershell
powershell -NoProfile -File local/ags_scripts/start-oke-model-relay.ps1
```

During an authorized live run, this process must remain running. If the laptop public IP changes, the restricted management allowlist must be deliberately updated before reconnection; do not broaden it to 0.0.0.0/0. AI operations require the laptop and tunnel online. Paid fallback models are not configured.

## Validation

- Backend regression suite: **896 passed, 4 skipped** after the consent fix (229.50 seconds).
- Consent regression suite after the fix: **5 passed**, including Oracle vector chat with local models; execution still rejects absent approval.
- Frontend unit suite: **150 passed**.
- ARM64 frontend production build and backend/relay container builds passed.
- Backend ARM64 offline smoke: imports OCI, Oracle, PyArrow and ONNX; health 200; unauthenticated protected endpoints 401; administration scripts absent.
- Relay smoke: pinned-key reverse forward works; shell and unapproved remote port denied.
- Kubernetes render checks: one node configuration, two 50 Gi claims, two one-replica Recreate deployments, internal API, public LB 10/10; no autoscaler, DB server or model Pods.
- Cloud HTTPS sign-in, Mani login, existing datasets, API/worker restart and tunnel reconnection verified.
- Discovered and fixed Oracle-query consent mismatch: local-model chat preflight previously omitted OCI Oracle knowledge, then execution rejected the request. Preflight now shows the correct approval popup; approval remains required.

Live browser checks now also confirm:

- Chat answers the existing Maya Rao employer question correctly: Blue Harbor Analytics and Cedar Systems; all cited extraction IDs are clickable.
- Citation drawer shows document name, saved version, extraction reference, page 1 and original PDF preview; opening and closing work.
- Existing reviewed result stays locked (readOnly fields and disabled Reviewed action); PDF expansion works.
- Extract table contains saved rows; browser CSV download succeeds with three records and correct names (Dev Patel and Maya Rao).
- Storage bucket test succeeds; Database test reports 13 of 13 tables and native vector search verified; registered models and dataset mappings load.
- Session cookie flags are Secure, HttpOnly and SameSite=Strict. HTTP redirects with 308; HTTPS returns 200; unauthenticated reads and mutations return 401.
- New fictional dataset `OCI Deployment QA 2026-10-14` created through Aegis Agent, with existing Nomic/Qwen model mappings and `oci-resume-qa.json`.
- New fictional resume upload and indexing succeeded. Real Qwen extraction over the tunnel returned all five expected fields, including both employers and all eight listed skills.
- New Parquet bytes read back successfully from the configured OCI route in mk-aegis and match validated result fields. Oracle SQL confirms 768-dimensional non-null embeddings for document chunks, document metadata, dataset, prompt, workflow and extraction sources.

The onboarding workflow completed all 9 steps, with a receipt verifying 9 unified knowledge vectors and the OCI Parquet artifact. Dataset ID: 908a8755-5a18-562f-ab0d-d9a85caf351c; document: 81bbc9f4-1c7c-459c-a497-a70a34fd6bdd; template: 4740e1dc-11a8-4456-8863-a6d61e6e1ac2; initial extraction: ef68c249-18ea-4779-9da6-e2b9b40ac19a; onboarding workflow: a8f987f5-5cc6-59eb-90eb-e4d8d6eeb450. The original extracted values match the fictional source.

Controlled tunnel interruption was performed while no jobs were queued/running. The model call returned a curated recoverable Ollama-unavailable error; API health stayed 200. Restarting the existing pinned-key relay restored cloud /api/tags to 200. No paid-provider fallback occurred. This was an idle connectivity/recovery test, not a forced crash in the middle of a paid or real-user operation.

The new result was marked Reviewed through the browser and is locked; fields remain unchanged. @ReExtract dispatched directly to the saved-document workflow. After selecting the existing prompt and confirming, re-extraction completed. New result 22becdfa-da4d-43a1-b7aa-898e83a1c621 was saved to extraction/22becdfa-da4d-43a1-b7aa-898e83a1c621/results/v1-f8435f1959419570.parquet in mk-aegis. Independent readback matched fields; Oracle SQL confirmed result vectors. The browser completion receipt reports 9 verified vectors and 1 saved Parquet file. The earlier Reviewed result is preserved.

Service restart checks verified that existing data survived the API/worker replacement and the tunnel reconnected. No active-job forced process-crash test or separate scanned-PDF OCR acceptance test was performed; unit coverage and model availability are not substitutes for those tests. A workspace refresh exceeded the UI's 30-second GET timeout once under concurrent processing; retry loaded the results. This performance observation is retained rather than counted as a clean pass.


## Final free-tier gate: Object Storage requests

The final OCI Usage API check returned **SGD 0.083574327096** of computed Object Storage usage for resource **mk-aegis**, SKU **Object Storage - Requests**, quantity **22.1326 units of 10K requests = 221,326 requests**, daily interval **13 October 2026 00:00 UTC to 14 October 2026 00:00 UTC**. This daily total includes activity before cloud cutover; it cannot all be attributed to this deployment. It is usage/cost reporting, not proof of an invoiced out-of-pocket payment. No account upgrade occurred.

Oracle documents **50,000 Object Storage API requests per month** in the [Always Free allowance](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm). The observed daily usage already exceeds that allowance. Trial credit consumption cannot establish a lasting free deployment.

To honor the explicit free-only gate, after the re-extraction completed and no jobs were queued/running, aegis-api-worker was scaled to **zero**, and the SSH relay was paused. The existing laptop API/worker remain stopped, preventing duplicate writers. The frontend, Basic cluster, single A1 node, load balancer and both persistent volumes remain; no data or cloud resource was deleted to conceal usage. The renderer honors application_paused=true, so a routine re-render preserves zero API/worker replicas. Both PVCs are Bound and the remaining Web/Caddy Pod is Ready.

At this initial pause, required work was to reduce Object Storage operations from mutable workflow/control-file reads, reconciliation and browser polling, and recheck entitlement before resumption. The fixes and later explicit trial-credit approval are recorded below. Originals and Parquet remain in mk-aegis and Oracle remains the metadata/vector source. Trial-credit approval does not increase the permanent free request allowance or authorize an account upgrade.

Billing evidence is saved outside Git in ags_runtime/ags_oke/billing-check.json and billing-detail.json. Acceptance screenshot: ags_runtime/ags_oke/cloud-reextract-proof.jpg. The public URL's backend is intentionally unavailable while this gate remains unresolved.

Read-only recheck at **14 October 2026 10:34 IST** (05:04 UTC), after the user requested another attempt: OCI's delayed report now shows **27.0951 units of 10K requests = 270,951 requests** for mk-aegis on October 13, computed amount **SGD 0.106890434846**. October 12 shows another 0.655 units = 6,550 requests with zero computed cost. The revised October 13 total is delayed usage evidence, not proof that requests continued after the API/worker pause. Kubernetes confirms API/worker 0/0 and WebUI 1/1. The no-cost gate still does not pass; specific approval was requested for a maximum ten-minute live verification with possible metered requests, followed by another pause. No such continuation was performed during this read-only recheck. Evidence: `ags_runtime/ags_oke/billing-recheck.json`.

## Object Storage request reduction prepared locally

The request amplification was traced to three-second browser polling of the entire job history, repeated workflow JSON reads by API/worker reconciliation, and writes of derived chat/progress snapshots during GET/SSE requests. The usage report alone cannot attribute each historical request to those paths.

The fix introduces active-job-only polling (`/api/jobs?ids=...`), stops progress polling when jobs are terminal, backs off hidden tabs, and refreshes result lists only on job status transitions. Onboarding polling uses four seconds instead of 1.5 seconds. GET/SSE still returns current progress, but unchanged plans and intermediate read projections no longer produce canonical plan writes. Terminal transitions, publication retries and goal recovery remain durable.

Small application-owned OCI JSON objects use a bounded persistent cache on the shared API/worker state volume: 4 MiB per entry, 64 MiB total and 2,048 entries. Writes still go to the bucket; identical writes are skipped. Per-key locks coalesce cold reads across API/worker processes. Pending-write markers invalidate old cached values across failures/crashes, and checksum validation detects corrupt cache entries. Originals and Parquet bypass the cache, including artifact readback verification. No OCI data or schema was moved or changed for this fix.

Cache coherence requires the existing single-writer deployment contract: API and worker share one state volume and all writes use Aegis RoutingStorage. An independent application or manual bucket edit requires invalidating the local `object-cache/` entries before resuming. Cache scope separates bucket/prefix/configuration and credential-file revisions. Do not run independent laptop/cloud writers against the same objects.

Validation: backend **906 passed, 4 skipped**; frontend **153 passed**; ARM64 frontend production build and backend image build succeeded. The repeat-read regression test made **14 backing GETs for 1,400 logical reads**, a **99% reduction in that simulated workload**, not a measured cloud-wide savings percentage. Concurrency, corruption, eviction, uncertain/late writes, permission filtering, unchanged-plan reads, and intermediate progress projection tests pass.

Browser checks use isolated local Docker containers, fictional data, a simulated OCI bucket with operation counters, SQLite/local vectors and a mock extraction model. No real OCI credentials/wallet/user data were copied into the fixture. Upload/indexing completed; extraction saved Parquet and published vectors; Review loaded the artifact and locked it after Reviewed. The mock provider deliberately rejects LLM agent planning, so its post-extraction narrative answer exhausted the existing bounded retry mechanism; this is not a real-model chat acceptance pass. The saved extraction remained available. Additional browser results are recorded below.

Re-extraction also completed in the browser with a receipt for one verified Parquet file and eight vectors. It produced a separate saved result and preserved the earlier Reviewed result. The Extract table showed both results, and the CSV download contained both records with their correct review states. Independent PyArrow reads confirmed all three Parquet artifacts (initial, Reviewed revision and re-extraction). API/worker restart preserved the conversation, saved results and shared cache; the UI needed a retry while the ARM64 emulated API was starting. This was an idle restart, not a forced in-flight crash test.

After restart recovery, the completed chat stayed open from fixture timestamp 1791936097.720 to 1791936143.750 (46 seconds). Simulated backing counters remained **45 reads / 194 writes**: **zero additional reads or writes**. API logs show no `/api/jobs` polling in the final 30-second interval. These totals include seeding, prompt saves, actual upload/extraction/review/re-extraction, publication and the deliberately bounded mock-answer retries; they are not a per-extraction cost estimate. Test services were stopped after verification; their isolated volume/logs were retained. Browser proof: `ags_runtime/ags_oke/storage-fix-browser-proof.jpg`; CSV: `C:/Users/Laya/Downloads/aegis-extract-data (1).csv`.

At the end of local verification these images were prepared locally (`aegis-oke-web:storage-fix-arm64`, `aegis-oke-backend:storage-fix-arm64`) and the cloud API/worker remained paused. The later, explicitly approved live window is recorded below. Publishing and live OCI verification must not bypass the user's free-only gate: the reported monthly Object Storage request allowance was already exceeded. No new resources, paid upgrade or cloud data movement occurred during the local fix.

### Approved bounded live verification, October 14

The user explicitly approved a maximum ten-minute live test with possible metered storage/registry requests, followed by another pause. The existing private repositories received the tested ARM64 images. WebUI image: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:e79aa525c2d7bde5c82226211aa9afe94adda4d20c78d828d400ff0e7841d354`. No repositories, OCI infrastructure or account upgrades were created. A hidden local shutdown guard began before scaling the existing API/worker deployment to one, with a pause deadline **10:46:25 IST / 05:16:25 UTC**. The durable renderer state remained paused so ordinary re-rendering cannot accidentally continue the test.

Initial cold-cache startup took approximately two minutes and the public UI reported unavailable/timeouts during that interval. The existing model relay recovered once API readiness made the Pod's Service endpoints available; laptop IP and security restrictions were unchanged. A real repeated-read probe exposed avoidable client initialization on cache hits. The cache now creates the OCI client lazily only when canonical IO is needed; a new regression test covers both cached reads and identical writes. **11 focused cache tests passed** and the updated ARM64 backend built/published successfully. Final backend image: `bom.ocir.io/bmyljaecivrj/ags-aegis-backend@sha256:06658e43205340c359d0a1f240706a97b1792d324751d012d833a407f01b76d5`. The first long repeated-read probe was stopped without changing production records. A bounded repeat check and browser verification continue under the original deadline; they do not extend it.

Live results: using the deployed RoutingStorage against the real bucket, the first check loaded 14 existing job files with **14 backing GETs**, then served **1,400 additional logical reads without any further GET/PUT/DELETE**; total time 4.08 seconds. A second check with the shared warm cache made **zero backing operations**, including the initial reads, and completed in **0.41 seconds**. Counters wrap the real OCI adapter in a separate read-only probe process; they measure this workload, not all account traffic or a daily billing reduction. The API logs show no idle `/api/jobs` polling; a deliberate workspace refresh still loads the authorized job history once.

The existing Mani session loaded the public WebUI. Qwen3 Chat answered through Oracle vector knowledge and the laptop tunnel in **35 seconds** (18 seconds understanding the request, about four seconds retrieval); citations opened published metadata, recorded page text and the original page image. Review opened the saved Parquet fields and the Reviewed lock. A stale initial workspace list after the startup timeout temporarily left Review selectors/original unavailable; Refresh reloaded the dataset/document/job lists successfully before pause. The question named Dev Patel, while the cited/Reviewed saved record now names Arjun Rao: company names matched the cited source, but this is **not a validated person-specific answer**. Entity matching/data freshness deserves a separate accuracy investigation; do not count the live check as an accuracy benchmark. No new upload, extraction or re-extraction was run in this limited window.

Before shutdown the SQL queue had **zero active jobs**. Pause was requested at **10:46:16 IST**, before the guard deadline; the guard independently requested pause at **10:46:27 IST**. Kubernetes then confirmed API/worker **0/0**, no API/worker Pod, WebUI **1/1** with Web/Caddy **2/2 Ready**, and the laptop SSH relay disconnected. The cloud API/worker had been resumed at approximately 10:36:55 IST, so the live window stayed below ten minutes. Renderer output remains at zero API replicas and references the final fixed images; rollback release references are preserved in ignored `release-before-storage-fix.json`. Evidence: `live-storage-cache-final.log`, `live-storage-cache-warm.log`, `live-test-api-final.log`, guard logs and `live-storage-fix-proof.jpg` under `ags_runtime/ags_oke`. OCI billing is delayed, so no final cost or whole-account reduction percentage can yet be inferred from this short test.

The complete backend regression suite was repeated after the lazy-client change: **907 passed, 4 skipped**, completed locally at **10:56 IST** in 854.92 seconds. Frontend remains unchanged after its **153 passing tests** and successful ARM64 production build. Final backend ARM64 build, focused cache tests and real OCI cache probes passed. Final full-suite log: `ags_runtime/ags_oke/backend-storage-fix-post-live.log`. No cloud service was resumed while these local tests finished.

## Aegis chat approval policy change, October 14

At the user's request, ordinary Aegis chat and planning/proposals use the configured model and scoped knowledge providers without an external-processing popup. The composer no longer performs consent preflight before every message. The read-only Aegis plan/reply endpoints apply this policy, including saved questions from the previous UI; ownership, model mappings, input validation and mock-provider restrictions still apply. Actual onboarding/upload/extraction/re-extraction submission retains its separate processing approval and confirmed-execution guards. A planning request never authorizes a processing job. Global provider consent guards for other APIs were not disabled. The footer now explains chat versus processing behavior.

Validation: **155 frontend tests passed**; chat/streaming/backend tests **46 passed**; the final consent/workspace/onboarding/re-extraction suite **65 passed**. An older test expecting consent before external planning was updated to verify that planning only proposes pending tools and creates no jobs. ARM64 frontend production and backend builds succeeded. Isolated browser checks used the new production images with a simulated bucket and deterministic metadata answers: two consecutive questions completed without a popup or consent preflight RPC, while Confirm extraction showed the approval popup. Cancelling left **zero queued/running jobs**. No real provider calls or OCI credentials were used by this fixture. Evidence: `chat-no-popup-proof.jpg`, `extraction-consent-proof.jpg`, `chat-consent-frontend-tests.log`, `chat-consent-backend-tests.log`, `chat-consent-workflow-tests-final.log` and build logs under `ags_runtime/ags_oke`.

At local validation completion, the candidate images had not yet replaced the deployed OCI images. The user subsequently explicitly approved **“Deploy and resume using trial credits.”** This authorizes ongoing operation under the active SGD 400 promotion, rather than another ten-minute window; it does not authorize an account upgrade or new OCI resources. The prior timed shutdown guard has finished and is not restarted.

The tested ARM64 images were published to the existing private repositories and applied only to the existing `aegis-web` and `aegis-api-worker` Deployments. WebUI: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:1ed9c8709c6c8d8e7915d69225739f717b4e722d4d26d3e7066746f05468914b`. API/worker: `bom.ocir.io/bmyljaecivrj/ags-aegis-backend@sha256:46cf90d749f19a4b07f88ae2a62eb88021004cc119cb9261953982e27098fa65`. Previous release references remain in ignored `release-before-chat-consent.json`. Renderer state records the approval and one API/worker replica. Existing wallet, secrets, database, vectors, bucket, volumes, load balancer and SSH restrictions are preserved. The existing hidden laptop model relay was resumed; the laptop API and worker remain stopped to preserve the single-writer rule. Public verification results follow below.

Service verification at **11:25 IST / 05:55 UTC**: WebUI Deployment 1/1 with Web/Caddy 2/2 Ready, API/worker Deployment 1/1 with all three containers Ready, zero container restarts, both existing PVCs Bound. Public HTTPS returns 200 with HSTS max-age=31536000. The cloud API reaches all three existing laptop models through `http://ollama:11434/api/tags`; SQL reports zero queued/running jobs. Only the original Ollama container is running on the laptop. Evidence: ignored `chat-consent-live-service-check.json` and relay logs.

After the user signed in again as Mani, the live browser completed two consecutive questions scoped to `OCI Deployment QA 2026-10-14`: “How many documents are in this dataset?” returned one document in **10 seconds**, and “List the documents in this dataset.” returned `01-arjun-rao-backend.pdf` in **2 seconds**. Neither displayed a consent popup. API logs show both plan/reply requests succeeded with 200 and no consent preflight calls in this test interval. These verify metadata chat and the popup policy; they are not a broad semantic accuracy benchmark. No processing job or new dataset was created. Evidence: ignored `chat-consent-live-browser-api.log` and `chat-consent-live-browser-proof.jpg`. Extraction approval was separately verified in the isolated production-image browser fixture above. Services remain running under the approved trial-credit activation.

## Review re-extraction approval fix October 14

The Review directory's Re-extract dialog previously inferred approval from the extraction model's provider alone. With local Qwen and Oracle vectors, it offered no approval control and submitted allow_external=false, causing a 409 confirmation error. The dialog now uses the existing workflow consent preflight for embedding and extraction destinations. Clicking Start re-extraction opens the processing popup when required; agreeing submits the request with approval, while cancellation creates no extraction. Existing source, prompt selection, idempotency protection, progress colors/animations and backend consent guards are preserved.

One focused local regression test passed, covering cancellation, pending approval and duplicate clicks followed by one approved submission. The ARM64 production build, including type checking, passed. Only the existing WebUI Deployment was updated to `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:72019f5a19d4b8f4f2f145984184e38236f81be05c344e09ce3a186bb507a912`; API/worker images and services were not restarted. No new infrastructure or upgrade was performed. Previous release references are retained in ignored `release-before-reextract-consent.json`.

One live browser round used the existing fictional QA dataset and `oci-resume-qa.json`. Start re-extraction opened the approval popup; Agree and continue created exactly one QA run, `acbe2371-7a2b-4469-9a0b-92dfe3d8346b`, at **11:47:49 IST**. All workflow stages completed, including Write Parquet, and Review results opened the new saved fields beside the original PDF. A single read-only verification loaded and validated the saved Parquet from OCI bucket `mk-aegis`, confirmed two non-null Oracle vectors for the current extraction version, and confirmed the original `ef68c249` result remains ready, Reviewed and version 2. No repeated extraction, upload, broad regression suite or model benchmark was run against OCI. Evidence: ignored `reextract-consent-popup-proof.jpg`, `reextract-consent-result-proof.jpg`, `reextract-consent-live-verification.log` and production build/publication logs under `ags_runtime/ags_oke`.

## Service connection footer October 14

The connection footer displays active file/database/vector destinations together with WebApp, FastAPI, worker and default model hosting. Hover, keyboard focus or click opens details. OCI deployment metadata explicitly sets `AEGIS_DEPLOYMENT_TARGET=oci`, `AEGIS_API_LOCATION=oci`, `AEGIS_WORKER_LOCATION=oci` and `AEGIS_MODEL_LOCATION=local` on the WebUI container. Local Compose files set local application hosting; unspecified external model hosts remain Unknown rather than being guessed. The frontend proxy adds only this allowlisted hosting metadata to the existing authenticated storage-status response. It strips API endpoint credentials and query strings and performs no extra provider/health probes. Worker/model details describe configuration, not a verified health result. The existing one-minute visible-tab refresh remains, with simultaneous calls coalesced.

One focused local test passed for all seven labels, local/OCI/unknown classification and exclusion of endpoint credentials/query strings. The ARM64 production build and type checking passed. Only the existing WebUI Deployment was updated to `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:8e08c5bef8686375cf89158bf8e1540c109d129f610a7b6e2d7836f7c6e112cd`; backend image, API and worker were not restarted. A single signed-in browser pass verified every hover popup: Storage OCI (`mk-aegis`, Mumbai), Database OCI (`agsora`, Mumbai), Vector DB OCI (`Oracle vectors`), FastAPI OCI (`http://api:8000`), WebApp OCI (public HTTPS origin), Worker OCI and AI models Local (laptop through SSH). All footer items fit the normal desktop width; the detail panel appears above the footer. No upload, extraction, inference or additional cloud resource was used for this check. Evidence: ignored `connection-footer-proof.jpg`, `connection-footer-browser-check.json`, build/publication logs and `release-before-connection-footer.json` under `ags_runtime/ags_oke`.

## Dataset onboarding scope and layout October 14

The onboarding card now carries literal name/description fields from its own current user request, defaults to dataset setup without processing, and selects eligible registered models using the current dataset defaults before falling back to the first eligible model. Existing explicit selections and accepted recovery receipts are retained. An explicit combined upload/extract request can still opt into processing. Dataset-only onboarding uses the existing five-stage server workflow. Its model selectors are in an expandable section and the shared compact stepper retains the approved colors/animations. The Latest message control reserves space in the composer instead of overlapping the workflow. Bare “extract” dispatches directly to the extraction operation, and current natural requests to create/onboard a dataset dispatch to onboarding. Questions explaining how to onboard remain ordinary questions. This changes the frontend handoff and presentation; backend authorization, confirmation, saved-model snapshots and processing endpoints remain unchanged.

Seven focused local onboarding checks passed, including recovery and explicit full processing, followed by a passing standalone TypeScript check and corrected final ARM64 production build. Only the existing WebUI Deployment was updated to `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:f8ca3f0a62ed6150b0d3c8ce7350c11b8123920450d7e65cdcdbce54f11f57ca`; backend/worker images were preserved. In one live browser round, the user's example request prefilled **TermSheet Dataset** and **Sample Termsheet Extraction Dataset**, selected Nomic Embedding, Qwen3 Chat and Qwen3 Extraction, and kept processing unchecked with no document/prompt inputs. Confirmation created that dataset, saved its model mappings, completed all five setup stages and published **four verified OCI knowledge vectors**. No upload or extraction ran. A subsequent bare “extract” request in the existing QA dataset displayed only the extraction call and its dataset/documents/prompt selectors; it was left unconfirmed and the test chat was cleared from the active view while saved history was retained. Aegis was left on TermSheet Dataset, ready for the user's documents. Preparation timings observed in this round were 0.8 seconds for onboarding and 0.7 seconds for the extract proposal, not a broad latency benchmark. Evidence: ignored `onboarding-scope-draft-proof.jpg`, `onboarding-scope-completed-proof.jpg`, `onboarding-scope-extract-only-proof.jpg`, final build/publication logs and `release-before-onboarding-scope.json` under `ags_runtime/ags_oke`.

## Rollback

Never run laptop and cloud workers concurrently. Drain cloud jobs, stop `aegis-api-worker` by scaling it to zero and verify its Pod has stopped before restarting the original laptop API/worker. Keep the cloud state volume, certificate volume, wallet, master key and original laptop volumes. If cloud work has changed control state, synchronize the required current state securely before switching; do not blindly restore the pre-cutover snapshot over newer results. Stop the cloud WebUI or avoid publishing two independent application sessions during rollback.

## Provisioning notes

The initial read-only capacity report returned OUT_OF_HOST_CAPACITY. After the user requested a real attempt, actual Basic cluster and fixed-size A1 node creation succeeded. No larger shape or paid capacity reservation was selected.

Oracle table names are chosen when the backend imports core. The cloud bootstrap uses DATABASE_PROVIDER=oracle and credential-free DATABASE_URL=oracle+oracledb://; the active engine obtains existing wallet credentials from runtime configuration. A SQLite bootstrap incorrectly selected conflicting table names and was corrected before activation. Existing tables/users were preserved. Automatic startup setup and Storage's table-creation action remain as authorized; no new OCI migration was requested.

The Caddy image reference must include docker.io/library because CRI-O enforces fully qualified image names. Resource IDs and idempotency records are stored in ignored `ags_runtime/ags_oke/provision-state.json`; release references in release.json, non-secret Kubernetes configuration in resources.json, and allocation evidence in allocation-check.json. Deployment code lives in ags_deploy/ags_oke; local Docker and tunnel scripts remain under local.


## Unified Chat Agent hybrid retrieval and accuracy fixes — 14 October 2026

The unified Chat Agent combines keyword BM25 ranking over the authorized publication manifest with the active Oracle vector query, fuses ranks by RRF, and uses the existing pinned CPU cross-encoder over a bounded candidate set. Final evidence is fetched from Oracle and checked against publication digests; the local manifest supplies ranking signals. Counts, catalogs, named prompts and scoped result summaries use exact published records. No Oracle Text index, DDL, republishing, provider upgrade or new infrastructure is required.

Prompt-file counts/listing have an explicit typed shortcut; template-content questions return the actual published instructions and schema. Bare summaries reuse only server-saved extraction IDs, revalidated against current dataset/document access. Explicit result names/IDs are enforced during retrieval even if the classifier omits them. Source metadata is excluded from extracted-value evidence. Result and prompt facts are rendered directly; free-form answers are buffered until citation/completeness checks pass. These checks do not constitute proof of every free-form semantic claim.

Local validation: 49 focused tests passed, including replay of the six exported follow-up requests; additional regression checks cover omitted names and retained document-filename scopes. ARM64 build/import smoke passed. Existing backend-only Deployment updates retain the Recreate strategy and the original wallet, credentials, state volume, database, vectors, storage routes and laptop AI endpoints. The first live named-result check exposed a classifier omission; the added server-side scope check passed locally and the live retest returned only the intended result. The six exported follow-up requests passed the live signed-in browser round on Arjun_Sample: Sara-only summary with explicit missing values, four stored documents, one prompt template for both count phrasings, prompt JSON listing, and actual template instructions/schema. The prompt citation opened the published version 3 source. Simple replies took 0.6–2 seconds; the named-result retest took 3 seconds. The semantic query initially failed the pre-display citation check; explicit string-array predicates now use verified membership checks and direct saved-value rendering. Its targeted regression passed. Completion regressions also verify that null values cannot be described as complete in either direct extraction completion or a generated goal summary. Final semantic retest passed on backend `51af067eb7619dc61775adff193ff793dac1ce1a1328ab65ed6306e735b4b4f3`: Oracle vector and keyword candidate counts were 4 each, RRF fused 4 entities, the pinned CPU reranker ran in 1812 ms, and explicit React + Accessibility membership checks retained only Sara records. Only name and skills entered the displayed evidence. End-to-end response time was 13 seconds. The dataset dropdown isolation check created a separate TermSheet Dataset conversation and retrieved that dataset's `Aegis_Term_Sheet_Extraction_Prompt_Strict.json`, rather than Arjun_Sample's `sample_resume.json`. Both datasets currently contain one prompt, so source IDs/names and recorded dataset scope—not equal counts—verify isolation. Existing user data was not changed. Three intermediate test image tags were removed; the active backend and original rollback digest remain. No new extraction, uploads, OCI resources, schema changes or model upgrades were performed. Ignored proof exports: `unified-chat-live-final.json`, `unified-chat-scope-check.json`; visual proof: `unified-chat-prompt-citation-proof.jpg`.

## Official references

[Always Free resource allowances](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm), [OCI and Basic OKE pricing](https://www.oracle.com/cloud/iaas-paas/), [Basic cluster creation](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengcreatingbasicclusters.htm), [OCIR image publishing](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrypushingimagesusingthedockercli.htm), [load balancer annotations](https://github.com/oracle/oci-cloud-controller-manager/blob/master/docs/load-balancer-annotations.md).


## Resource identifiers and operational commands

Cluster: `ocid1.cluster.oc1.ap-mumbai-1.aaaaaaaay4zari7krwtewgdg3uc3f7s6phzbwv4mejco23z44cks3v2b2eia`.
Node pool: `ocid1.nodepool.oc1.ap-mumbai-1.aaaaaaaajykjrvyfuq2nbv2whzmtje5ilg57tlvj5g6l5qk7cnfggtfxsxea`.
Instance: `ocid1.instance.oc1.ap-mumbai-1.anrg6ljrcbffg3icsmk34krt672mzuhgj4gdla6tkubac5c2k3oyvqxiyl2a`.
VCN: `ocid1.vcn.oc1.ap-mumbai-1.amaaaaaacbffg3ia22uoskaifferen7xtij6zex6fa6amiwsvswf2iovau3q`.
Node address: private 10.42.1.30; public 140.245.28.141.
Application PV: `csi-a19e75bd-623f-4e3c-8f77-c3ff176305ae`; HTTPS PV: `csi-dd30bb5b-3cc0-412a-8f2b-3f7bdc842eb3`.
The temporary state-bootstrap Pod was removed after transfer; both persistent claims remain Bound.

Run read-only service checks from the repository:

```powershell
kubectl --kubeconfig ags_runtime/ags_oke/kubeconfig.yaml -n aegis-oci get pods,svc,pvc
kubectl --kubeconfig ags_runtime/ags_oke/kubeconfig.yaml -n aegis-oci logs deployment/aegis-api-worker -c api --tail=30
kubectl --kubeconfig ags_runtime/ags_oke/kubeconfig.yaml -n aegis-oci logs deployment/aegis-api-worker -c worker --tail=30
```

The kubeconfig uses the existing OCI SDK and local config to generate an exec authentication token. Do not paste its generated authentication token or secret manifests into chat or Git. Re-rendering resources does not apply or create anything until kubectl apply is run. The provisioning helper reconciles saved resource IDs; do not create a second cluster/node pool for an ordinary application update.


## Chat Review link cleanup — 14 October 2026

Removed the redundant Extraction IDs navigation paragraph when the same saved results already have Review result buttons. The presentation filter applies to existing saved conversations and copied answer text; raw conversation records, exports, citations and extraction references remain intact. Published ARM64 WebUI digest `a47ce7f1db39f3694b747f1383e2b9255b0d15652121d3ac808fd71870abfd81`, retaining the previous WebUI release for rollback. Production compilation, type checks and static page generation passed. Only the existing WebUI Deployment was updated; API and worker were not restarted. One live check used the existing Termsheet Extract - 01 response: duplicate label count 0, Review result button count 1, and the retained button opened extraction `79b557d8-9323-4557-9541-4a36a8da4ee3` in Review. No new chat generation, extraction jobs, resources or upgrades. Screenshot outside Git: `ags_runtime/ags_oke/review-links-proof.png`.

## Shared translucent page headings — 14 October 2026

Applied the latest lavender-to-blue translucent title preview through one shared stylesheet and title class. All workspace page headers, the compact Review detail, sign-in and password recovery use it. Existing fonts, controls, logo components and workflow animation conventions remain. A generated raster texture with real alpha is mounted behind editable text, with compact padding on chat, Extract and Review. Asset: `ags_frontend/public/ags_assets/heading-blend.png`, produced with the built-in image generation tool. The full texture prompt is recorded below.

The ARM64 production build and type checks passed. Published WebUI digest `f776e39bed866e461a30f8c49764ae805b0673d83b7da24edda3290cab76c274` to the existing private OCIR repository and updated only `aegis-web`; previous release `a47ce7f1db39f3694b747f1383e2b9255b0d15652121d3ac808fd71870abfd81` remains available for rollback. No backend/worker restart, upgrades, new resources or data movement. A single live visual pass confirmed the texture and title fit on all eleven workspace destinations and the saved extraction Review detail. Home search worked and was cleared; captured browser error logs were empty. Local sign-in was checked at desktop size and its title measured at 375 px. Temporary browser viewport overrides were restored. QA: `design-qa.md`; ignored evidence: `blended-headings-comparison.png`, `blended-headings-final-proof.png`, `blended-heading-review-normal.png`, `blended-heading-checks.json`.

Texture prompt:
> Create ONLY a reusable raster background texture for the compact translucent Home title panel in the supplied Aegis screenshot. The screenshot is a color/style reference; output no screenshot and no UI. Texture dimensions wide 1000 by 220 pixels. A smooth restrained pastel lavender blend on the left transitioning through periwinkle to pale icy cyan on the right. Keep it delicate, visually about 20 to 25 percent color opacity, with real translucent alpha over a transparent background, fading softly at the far right. It will be placed behind editable dark navy headings on white or light blue application screens. No text, no letters, no icons, no borders, no shadows, no rounded corners, no objects, no noise, no checkerboard drawn into pixels, no patterns, no white opaque canvas. Flat uniform soft lighting. Match the subtle lavender/cyan title background of the reference and preserve plenty of contrast for text.

## Dataset directory table — 14 October 2026

Replaced the tall dataset directory list with a semantic table matching the Extract screen's compact table styling. Columns: Dataset, Description, Documents, Ready, Status and Actions. Dataset names still open their documents; the Chat icon has a dataset-specific tooltip and accessible label. Description text is clamped visually with the full description retained in its tooltip and text search. The table has sticky headers and a sticky dataset column for narrow-screen scrolling. Existing creation and authorization behavior is preserved; Home cards are unchanged.

The ARM64 production build, type checks and existing Home startup/loading regression passed. Published WebUI digest `8264ca00e223e78a6c44c4a29ba8327cfdd9f3333e35573d058aec3f996647ed`, updating only the existing WebUI deployment. Previous WebUI digest `f776e39bed866e461a30f8c49764ae805b0673d83b7da24edda3290cab76c274` is retained for rollback. The single live pass confirmed six dataset rows and six columns, matching TermSheet search and the no-match state, opening the dataset's existing PDF document list, canceling the New dataset form without creating data, and opening Chat with TermSheet Dataset selected (`53f60083-1dc6-587c-bb12-f296be00f889`). At a 920 px viewport all columns fit; the narrow browser viewport uses horizontal table scrolling. Browser error logs were empty. The browser was restored to its original viewport and left on the dataset table. No new dataset, upload, extraction, inference, backend restart, resource creation or account upgrade. Final proof outside Git: `ags_runtime/ags_oke/dataset-table-final-proof.png`.

## Full-width heading ribbon — 14 October 2026

The user's full-width reference supersedes the compact title badge. The shared translucent texture now belongs to the entire page heading row, including right-side controls; the title's separate surface is removed. All workspace page headers and the Review detail heading use the same full-width styling. Sign-in/recovery heading surfaces also fill their available width. Compact padding remains on Agent, Extract and Review, and existing fonts, content, actions and data destinations are preserved.

Production ARM64 build and type checks passed. Published WebUI digest `3023119070abc9a62c5bd7fd516eff71ffab2bc3267d199277e30438487f8e11`; only the existing WebUI deployment was updated. Previous WebUI digest `8264ca00e223e78a6c44c4a29ba8327cfdd9f3333e35573d058aec3f996647ed` remains the rollback release. In the focused browser pass, Home's ribbon measured 854.8 px against 854.8 px available, Aegis Agent 896 px against 896 px available, and Review detail 858.4 px against 858.4 px available. All action groups stayed inside their ribbons. Home search opened and closed correctly; the existing reviewed extraction's fields and PDF remained usable. Captured Review browser error logs were empty. Temporary viewport overrides were reset, and the separate Review test tab was closed. No new chat generation, datasets, upload, extraction, infrastructure, upgrades or backend/worker restart. Evidence outside Git: `full-width-heading-reference.png`, `full-width-heading-home-proof.png`, `full-width-heading-review-proof.png`, `full-width-heading-comparison.png`, `full-width-heading-checks.json`. Latest visual check: `design-qa.md`.


## Screen regions and translucent components — 14 October 2026

Each workspace main now forms one named visual region containing its full-width heading, actions, controls and content. Its existing flex and scrolling structure is retained. Removed the page eyebrow and introductory subtitles, plus redundant directory headings in Datasets, Model Registration, Prompt templates and Jobs. Dataset creation has one form heading. Model Mapping uses a compact category count. Removed decorative descriptions beneath the File storage, Database & knowledge and Users subheadings; actual dataset descriptions, credential guidance, consent, status, warnings and consequential-action explanations remain.

Shared `app/workspace-region.css` applies translucent light blue controls and primary actions with readable blue text, visible focus, hover, selected and disabled states. Modal buttons share the palette. Workflow progress colors/animation and success/error statuses remain unchanged. Dataset row names retain their original case.

Published ARM64 WebUI `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:0beeb0a3cc7c52c14dde85f0a3070b5622bf1e4b8e0776ade4587520ebb2a30d`. Rollback: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:3023119070abc9a62c5bd7fd516eff71ffab2bc3267d199277e30438487f8e11`. Only the existing WebUI deployment was replaced; API, worker, OCI database/vectors, bucket, laptop models, credentials and mounted state remain unchanged. No infrastructure creation, upgrades or data movement.

Validation: standalone TypeScript check, ARM64 production build, local ARM64 container HTTP 200 smoke check and OKE rollout passed. One live layout pass covered all eleven workspace destinations and the existing TermSheet Review detail; each had a single screen title, zero page-header subtitles and no page-level horizontal overflow at 920 × 668. Datasets search returned the matching TermSheet row; creation opened/cancelled without saving. Review showed one visible Review title, both 278.4 px panes and a fitting footer. At 375 × 812, Review had no horizontal overflow and its footer ended at 765.2 px; mobile pane tabs remained visible. Captured browser error logs were empty. No new datasets, chat inference, extraction jobs, exports or Storage configuration changes. Browser viewport override was restored and the temporary test tab closed. Proofs and measurements are under ignored `ags_runtime/ags_oke/workspace-region-*`; latest QA record is `design-qa.md`.


## Compact Agent and sideways Home search — 14 October 2026

Home search now expands inline to the left of its toggle, with a 260 ms width/opacity transition and reduced-motion support. The hidden input is inert; opening focuses it, Escape/toggle/outside click closes and clears it. The header retains its height. On narrow screens, search temporarily takes the title space and Refresh is icon-only, retaining its accessible label.

Removed the Agent-only title/Refresh ribbon and the standalone Onboard dataset toolbar button. Dataset/document/history/new-conversation/clear controls remain; onboarding through chat and @Onboard remains. Removing the ribbon gives more vertical room to the thread.

The answer progress rail now fits up to 665 px and its hover detail panel up to 760 px, bounded by the viewport. Active labels wrap instead of ellipsizing at 125 px. Summary text is 11 px and active caption text 12 px. The shared WorkflowStepper is retained, using fitted compact rails without a horizontal scroller; spinner, checkmarks, incoming particles, close, hover and keyboard inspection remain. Updated WORKFLOW-DESIGN.md for the user's wider answer rail.

WebUI: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:a174f5f388019f53390e601671ba8d015cb1a50d61266ad39163af87714d1a12`. Rollback: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:0beeb0a3cc7c52c14dde85f0a3070b5622bf1e4b8e0776ade4587520ebb2a30d`. Only the existing WebUI Deployment changed; API/worker and data connections remain unchanged. No upgrades, resources, data movement or new AI/extraction work.

Validation: TypeScript check, ARM64 production build, local ARM64 HTTP 200 smoke and OKE rollout passed. An isolated local Next preview imported the actual DatasetSearch, AgentAnswerWorkflow, WorkflowStepper and shared CSS. Eight sample stages fit: desktop rail 665 × 81.8 px; mobile rail 343.2 × 75.8 px. At desktop 920 px, search width grew from 0 to 220.8 px; its button x stayed 744.9 px, y stayed 101.8 px, and header height stayed 67.6 px. At 375 px, search grew to 185.2 px on the same row and there was no horizontal overflow. Focus/Escape/toggle checks passed. Sample progress was clearly labelled development-only and made no API calls. Temporary preview stopped and its tab closed.

The user renewed the expired sign-in session on the website. Authenticated Home search passed: one TermSheet card matched; input expanded left to 220.8 px with toggle x 707.7 px, y 101.8 px and header height 67.6 px unchanged. Escape cleared and collapsed search. Agent had zero extra heading rows and zero Onboard toolbar buttons; controls began at y 60.8 px, just below navigation ending at y 52 px.

The saved Local model recovery verification conversation exposed two hover/click obstructions: preview state enlarged the collapsed badge, and a large popup could cover its own centered trigger. Corrected the former by expanding layout only for a visible inline rail. Corrected the latter by placing above/below the anchor with a dynamic maximum height bounded by the chat area. Local centered-trigger verification at 920 × 668 and final live pointer click both passed. The final live rail measured 665 × 81.8 px, with all seven real saved stages visible and a 12 px caption. The preview measured 760 px wide, fit inside the chat and did not cover its trigger. Preview and rail close actions passed; captured browser error logs were empty. No new inference, extraction, uploads or Storage mutations. Temporary preview launchers and tabs were stopped/closed and viewport override reset.

Evidence: ignored ags_runtime/ags_oke/compact-chat-home-proof.png, compact-chat-agent-proof.png, compact-chat-workflow-details-proof.png, compact-chat-workflow-rail-proof.png, compact-chat-live-checks.json and compact-chat-local-*; design-qa.md records final validation.


Final WebUI release for this change: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:b53e4562c8c3f6e5dc08c48d7316d26b6abd1df3942bfcfa24097bebdf30c520`. ARM64 production build and OKE rollout passed after the hover/placement corrections. Prior `a174f5f3` and `4064f0d1` releases were intermediate verification builds, superseded by this release. Stable rollback remains `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:0beeb0a3cc7c52c14dde85f0a3070b5622bf1e4b8e0776ade4587520ebb2a30d`. API/worker images and services were preserved throughout. No new infrastructure, upgrade or data movement.


## Uniform title bars and Datasets search — 14 October 2026

Moved Datasets directory search into the region title row using the existing animated Home search component. The query is now controlled by the screen and passed to its directory table. Search hides during dataset detail/creation and clears when leaving the directory; the empty-result Clear search action remains. Removed the old inline field, unused field CSS and unreachable hidden legacy dataset cards. Outside closing now follows the completed click so filtering does not move a result between pointer-down and selection. Removed the decorative Documents-tab explanation. Real dataset descriptions, counts, field guidance, warnings and consent remain.

All workspace title bars, including Review detail, share the same 68 px desktop height, 24 px title text, 12 × 20 px padding and 12 px corners. Mobile uses 64 px, 20 px, 10 × 14 px and 10 px corners. The full-width blended texture is retained. Header buttons share a 40 px minimum target; narrow-screen action labels hide visually while tooltips and accessible names remain. The Agent screen retains its intentional absence of a title ribbon. Main title subtitles were already removed from current source; live verification confirmed none remained.

WebUI release: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:91189c5929d49c3683800ffa468ec7bf39cbb238e813fd207e90a976e917871b`; rollback: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:b53e4562c8c3f6e5dc08c48d7316d26b6abd1df3942bfcfa24097bebdf30c520`. Only the existing WebUI deployment changed. API/worker, secrets, mounted state and data destinations remain unchanged; no infrastructure, upgrade or data movement.

Validation: TypeScript check, ARM64 production build, HTTP 200 ARM64 container smoke and OKE rollout passed. Local actual-component checks covered title-row filtering, direct filtered-row selection, detail/create visibility, return/cancel and 375 px layout without API calls. One live pass checked Datasets filtering/direct selection, all ten ordinary workspace destinations and Review detail. Every desktop title bar measured 68 px, 24 px text, matching padding/corners, zero subtitle paragraphs and no page-level horizontal overflow. Directory/detail header heights matched. Review retained a 258.8 px field pane and fitting footer. At 375 × 812, Review measured 64 px/20 px with no horizontal overflow and a fitting footer. Agent had zero extra title rows. Captured browser error logs were empty. No new datasets, inference, extraction, exports or settings mutations. Temporary tabs/preview server stopped and viewport restored.

Evidence outside Git: `region-header-search-proof.png`, `region-header-datasets-proof.png`, `region-header-review-proof.png`, `region-header-mobile-review-proof.png`, `region-header-checks.json` under ignored ags_runtime/ags_oke. Latest QA: design-qa.md.


## Prompt templates table — 14 October 2026

Replaced the tall prompt cards with a semantic table: Prompt template, Dataset, Fields, Version and Actions. Names retain their case and wrap; matching uploaded filenames are no longer repeated. Edit, saved versions, JSON download and Use actions retain their existing handlers and now have template-specific accessible names and hover tooltips. Numeric columns have fixed widths so Fields and Version stay on one line. Sticky table headers and contained scrolling support long lists and narrow screens. Controls retain the shared light blue translucent palette.

The shared heading rules remain unchanged: Segoe UI, 24 px title / 68 px bar on desktop, 20 px / 64 px on mobile, with the same full-width blended background and padding as other screens.

Validation was limited to this cosmetic change: ARM64 production build (including type checks), a local responsive layout check and one focused live Prompt templates round. The live screen contained six templates and five columns; search returned one OCI QA template, the TermSheet dataset filter returned its single template, and Edit opened/cancelled without saving. All 24 icon controls retained accessible names/tooltips. Final title and column geometry fit at 920 × 668 without horizontal overflow; captured live browser error logs were empty. Local 375 px layout contained table scrolling without page overflow. No full frontend/backend suites, AI requests, extraction jobs, uploads, exports or settings writes were run.

WebUI: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:ed474554a01ce9ab9ad3cf285f50fc7845d0c587be0c8a416127c409769b0f99`. Rollback: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:91189c5929d49c3683800ffa468ec7bf39cbb238e813fd207e90a976e917871b`. Only the existing WebUI deployment changed. API, worker, Oracle database/vectors, bucket, laptop models, credentials and mounted state remain unchanged; no new OCI infrastructure or account upgrades. Temporary QA tabs/server were closed and the viewport override reset. Proof: ignored `ags_runtime/ags_oke/prompt-directory-table-proof.png`; measurements: `prompt-directory-table-checks.json`.


## Consistent Aegis typography — 14 October 2026

Added `ags_frontend/app/typography.css` as the shared application typography layer. Bundled the unmodified Inter variable font (352,240 bytes) and its SIL Open Font License inside `public/ags_assets/ags_fonts`; source: https://github.com/rsms/inter at commit `353b61b9f4430d5f420d56605a6e7993e0941470`. The app preloads and serves the font itself; browser sessions do not contact a third-party font provider. The supplied example was used only to inform typography hierarchy, without copying its branding, screens, controls or content.

Desktop scale: page title 24 px/600, section heading 18 px/600, card title 16 px/600, body/table values 14 px/400, form labels and secondary descriptions 13 px, metadata/table headers 12 px. Record names and actions use medium weight; table headers use title case with normal tracking. Text uses dark neutral ink and quieter secondary labels; blue interactive/status colors and the blended heading background remain. Numeric table values use tabular figures. Mobile titles use 20 px and inputs 16 px. The approved heading heights remain 68 px desktop / 64 px mobile.

Chat keeps 16 px reading text, including paragraphs inside answers. Compact answer workflow tables/captions are excluded from the broader table/helper rules so existing progress sizing remains. Layout, routes, APIs, jobs, permissions, consent and connection logic are unchanged.

Validation: local sample previews of Review, prompts, Home and compact chat progress; a 375 px prompt layout check; ARM64 production build with type checks; and one focused live visual round covering representative screens. The self-hosted font loaded, the title bars retained their heights and visible tables/controls fit. No exhaustive test suites or new model, extraction, upload, export or Storage-write operations. Screenshots and font/geometry measurements are under ignored `ags_runtime/ags_oke/typography-*`.

WebUI: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:9e6e868b67712b023c0f20abd5b7ac916337ddeebdf26eda7b98525218e03707`. Rollback: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:ed474554a01ce9ab9ad3cf285f50fc7845d0c587be0c8a416127c409769b0f99`. Only the existing WebUI deployment changed; API/worker, Oracle database/vectors, bucket, laptop models, credentials and mounted data remain unchanged. No new OCI infrastructure, account upgrades or dependency upgrades. Temporary QA tabs/server were closed and the viewport override reset.


## Remove duplicate screen title bands — 14 October 2026

Removed the shared page-title band from every workspace route. The existing top breadcrumb now contains the single visible page heading. Home/Datasets search, Refresh and Extract's New extraction action moved into the top bar, retaining their existing handlers, accessible names, disabled states and tooltips. Agent keeps its existing layout without adding a page-actions row.

Review detail retains processing/review status, Reload and result export in a compact unframed toolbar; its duplicate Review title is visually hidden while the original focus target remains available for assistive technology. Dataset names, form headings and content headings remain. Directory table height limits now allow more content in the space freed by the removed title bands.

Fixed the expanding search's nested border/outline. The input has no border, outline or shadow; its wrapper supplies one inset focus frame which is not clipped by the width animation. Keyboard focus remains visible, including a forced-colors fallback. Mobile expansion fits in the top bar and temporarily uses the breadcrumb space; closing restores the page label.

Validation: local desktop/mobile layout and search-focus checks; ARM64 production build with type checks; one focused live visual round. Captured screens had zero page-title bands, one top-bar page heading and no horizontal page overflow. Search/filter and existing Review controls remained available. No full test suites, new AI calls, extraction jobs, uploads, exports or Storage writes. Proofs/measurements are in ignored `ags_runtime/ags_oke/banner-free-*`.

WebUI: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:dd2c18e7785717501521a72f1f7265c98a8286f399f7ae418fa398fa92871169`. Rollback: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:9e6e868b67712b023c0f20abd5b7ac916337ddeebdf26eda7b98525218e03707`. Only the existing WebUI deployment changed. API/worker, Oracle database/vectors, bucket, laptop models, credentials and mounted state remain unchanged; no new OCI resources or account/dependency upgrades. Temporary QA tabs/server closed and viewport override reset.


## Datasets table and integrated model onboarding — 14 October 2026

Removed the separate dataset detail layout, Documents/Model Mapping/Settings tabs, document panel and obsolete upload/preview/reindex/delete handlers from the Datasets screen. Datasets always displays its directory table. Dataset names are plain text and Home no longer links to dataset details or its removed Settings view. Existing `#dataset/<id>` links preserve dataset context and normalize to `#Datasets`. Existing chat actions and Model Mapping under Manage workspace remain available; extraction model-configuration links now target that mapping screen.

New dataset uses the existing resumable onboarding workflow in a create-only mode. It shows name/description and Embedding, Chat and Extraction selections in the same flow, preselecting eligible credential-configured models (preferring the current defaults). Upload/extraction controls are absent. The existing worker creates the dataset, saves model mappings and publishes its knowledge metadata; completion updates the directory and returns to the table, clearing the completed request receipt. Interrupted or failed setups retain the existing idempotent confirmation receipt for resume/retry. Progress uses the shared WorkflowStepper only after submission in this form. Chat onboarding and full upload/extraction modes retain their prior behavior.

Validation: standalone TypeScript check, eight focused local onboarding/default-selection tests, an actual local mock create-and-map UI round returning to the table, a fresh subsequent form and 375 px layout check, ARM64 production build/type checks and a focused live inspection. The legacy Sample detail URL redirected to the six-row directory with no detail panels/tabs. New dataset exposed three preselected model controls and no document-processing toggle; it was closed without submission. No live test dataset, AI request, extraction, upload, export, data deletion or Storage configuration write. Evidence: ignored `ags_runtime/ags_oke/dataset-onboarding-only-*`.

WebUI: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:fbd2c28c18a86790f36373a35769366c2e84f21544742a00d484826932f5a8ef`. Rollback: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:dd2c18e7785717501521a72f1f7265c98a8286f399f7ae418fa398fa92871169`. Only the existing WebUI deployment changed. API/worker, database/vectors, bucket, laptop models, credentials and mounted state remain unchanged. No new OCI infrastructure, account/dependency upgrades or migrations. Temporary preview server/tabs closed and browser viewport restored.


## Compact Prompt templates toolbar — 14 October 2026

Moved Dataset, Search prompt templates and New prompt template into one aligned toolbar. Desktop controls share a 40 px height with compact label spacing; the count sits immediately above the table. Narrow layouts wrap search below the dataset/button pair, with a single-column fallback below 360 px. Existing dataset/search filtering, creation, editor and table actions retain their handlers and accessible labels. No title banner was reintroduced.

Validation: local actual-component checks at 920 × 668 and 375 × 812 found no horizontal page overflow. All three desktop controls measured 40 px with the same top position; the table begins at approximately 206 px. ARM64 production build including type checks and OKE WebUI rollout passed. One focused live round confirmed six templates, one result for OCI QA search and one result for TermSheet filtering. Browser error logs were empty. WebUI is 2/2 ready with zero restarts; API/worker remains 3/3 ready with zero restarts. No full test suites, AI calls, new datasets, extraction jobs, uploads, exports or settings writes.

Active WebUI: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:3c009b60e1b3f1db46f6424677ce5d27e750edf81dec7476a7e19f0697de55b2`. Rollback: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:fbd2c28c18a86790f36373a35769366c2e84f21544742a00d484826932f5a8ef`. Only the existing WebUI deployment changed; no new OCI resources, account upgrades, dependency upgrades or data movement. Temporary preview server/tabs closed and browser viewport restored.

Proof and focused check data are outside Git under ignored `ags_runtime/ags_oke/compact-prompt-toolbar-*`.


## Compact workspace action icons — 14 October 2026

Introduced shared ActionButton controls with 36 px targets, distinct Lucide icons, native hover tooltips and explicit accessible names. Converted common actions across Home, Datasets/model mappings, Prompt templates/field editor, Extract/Review, Jobs, Model Registration, Users, Storage/connections and agent/citation/document panels. Review and Re-extract are now side-by-side icons; New extraction, dataset, prompt, model and user actions use a plus. Prompt Add retains a 40 px target aligned with its filter/search controls. Existing icon controls gained missing hover titles. Native button attributes, handlers, disabled states and implicit submit behavior are preserved. Navigation, filter/tab/provider choices, consent/confirmation labels and workflow state text remain readable.

Validation was limited to the cosmetic scope: standalone TypeScript check, ARM64 production build/type checks, local actual-component Review/Prompt/Home desktop/mobile checks and one focused live Review/Prompt round. Local Review and Re-extract callbacks worked; the prompt Add icon opened the form and Add field updated its draft, which was cancelled. At 375 px Home had no page overflow. Live Review icons measured 36 × 36 px with empty visual text and populated accessible names/titles; re-extract options opened and were cancelled without starting a run. The prompt plus measured 40 × 40 px and stayed in the filter row. Live browser error logs were empty. No full test suites, AI calls, extractions, uploads, exports, dataset creation or configuration writes. The local synthetic SSR preview reported an existing locale-date hydration mismatch and a controlled-input warning; date/input logic was not changed and these warnings did not appear in the live round.

Active WebUI: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:ce208cb22a6248078fa92cd9fd9c0f10b6178d5b39aece5b41d0ef88497b8f57`. Rollback: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:3c009b60e1b3f1db46f6424677ce5d27e750edf81dec7476a7e19f0697de55b2`. WebUI is 2/2 ready and API/worker remains 3/3 ready, both with zero restarts. Only the existing WebUI deployment changed; no new OCI resources, upgrades, credentials changes or data movement. Temporary preview server and QA tabs closed, viewport restored.

Evidence outside Git: ignored `ags_runtime/ags_oke/workspace-action-icons-*-proof.png`, `workspace-action-icons-live-checks.json`, and `icon-actions-local-*`.


## Compact reference typography — 14 October 2026

Applied a shared compact sans-serif hierarchy using the existing bundled Aegis Inter font: workspace/section headings 18 px semibold; table headings and all sidebar navigation 14 px medium; table rows, names, desktop fields/labels and chat body 14 px regular; secondary details, table IDs and connection footer 12 px. Section headings inside dialogs use the same scale. Mobile rows remain 14 px; editable mobile inputs retain 16 px to prevent focus zoom. Home card names retain their secondary 16 px hierarchy. Icon actions, tooltips, colors and the absence of title banners are preserved.

Review sortable headers can wrap instead of clipping at the larger size. Desktop status/actions column widths were balanced to give badges more room alongside both action icons. Narrow tables retain their contained horizontal scrolling. A live check found that the sidebar is a sibling of the page shell; its typography rule now targets the actual workspace-navigation element and includes nested/selected items.

Validation: local actual-component Review/Prompt desktop checks, 375 px layout, 18 px form/section heading checks and actual sidebar validation; ARM64 production build with type checks; focused live font measurements. All visible navigation items measured 14 px/500, Review headers 14 px/500, rows/controls 14 px/400, secondary details 12 px/400 and the workspace title 18 px/600. The bundled font loaded, no page-level horizontal overflow was found, and final browser error logs were empty. No full test suites, AI calls, extraction jobs, uploads, exports, new datasets or settings writes were performed. Earlier typography releases were superseded during verification to correct the sidebar selector; the final image below is authoritative.

Active WebUI: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:0111685119051785dc971400f57d3985e4e1b036f9bb6d01f2f9005f4116d33b`. Stable rollback: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:ce208cb22a6248078fa92cd9fd9c0f10b6178d5b39aece5b41d0ef88497b8f57`. Only the existing WebUI deployment changed. API/worker, data destinations, credentials and mounted state were preserved; no infrastructure, account/dependency upgrades or data movement. Temporary preview servers and QA tabs closed and viewport restored.

Evidence outside Git: ignored `ags_runtime/ags_oke/compact-font-reference-*`.


## Laptop standby interrupted local AI — 14 October 2026

Investigated the user-reported "Local Ollama is unavailable or returned invalid data" extraction error without changing services or saved data. Laptop Ollama was healthy, loopback-only at 127.0.0.1:11436, with qwen3:4b, nomic-embed-text:latest and qwen2.5vl:3b installed. OCI could retrieve the installed model list through http://ollama:11434.

Correlated the failed extraction's job metadata with relay and Windows power events (IST): extraction began at 20:10:39; Windows entered Modern Standby at 20:15:33 with Reason: Lid; the cloud SSH relay reported an unresponsive client at 20:17:26.301; the extraction was marked failed at 20:17:26.618; Windows exited Modern Standby at 20:17:28 with Reason: Lid; the relay accepted the reconnected laptop at 20:17:40. The hidden reconnecting relay recovered automatically. This was a laptop sleep interruption, not a missing model or stopped Ollama container.

There were zero active jobs before verification. One synthetic eight-token Qwen request from OCI returned HTTP 200 with a completed JSON response in 14.25 seconds. This verified connectivity/inference availability only, not extraction accuracy or full document processing. No live extraction was retried, and no files, model settings, power settings, cloud resources, images or credentials were changed. Laptop AI operations require the laptop to remain awake with Docker/Ollama and the private relay running. The user can retry the failed extraction after wake/reconnection.


## Roomier Review detail and distinct action icons — 14 October 2026

Removed the visible Ready/review-status/version heading row and its inline extraction-ID disclosure. Extraction details, status/version, source provenance and existing notices remain in a native information dialog accessed by a labelled icon. Reload and Download are compact icons with hover titles; all four export formats and their existing links remain. Re-extract now uses the document-scan icon throughout shared actions and its start dialog, distinguishing it from Reload's circular arrow. The existing focusable visually hidden Review heading is retained.

Back sits beside the Dataset/Prompt/Extraction filters on desktop and mobile instead of consuming a separate row. Review detail uses a viewport-height flex layout with the existing top bar and connection footer reserved. The result and document panes fill the remaining height; only their contents scroll. Page-level scrolling remains available on other screens. Mobile retains tabs to choose fields or source; Reviewed/Cancel and the original permanent-lock explanation remain accessible. Data, field editing, result locking, dataset scope and source/download behavior were not changed.

Validation: standalone TypeScript check, ARM64 production build with type checks, local actual-component 51-field/PDF layout at 920 × 668 and 375 × 812, information-dialog and export-menu checks, then one focused live round on the user-selected result. Live document dimensions matched the viewport at both sizes (no outer vertical/horizontal overflow). Desktop panes measured 382 px, with the filters starting at 70 px; mobile pane height was 430 px. The PDF image loaded; the removed status rows were absent; Reload and Re-extract SVG identities differed; metadata opened/closed, four export choices remained and mobile source switching worked. Browser error logs were empty. No full suites, AI calls, new extractions, exports, edits or Reviewed submissions were run.

Active WebUI: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:22dbca5a34686faa7a78110bca9592d3aba860cf01512c2cf8cc32643a38b506`. Rollback: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:0111685119051785dc971400f57d3985e4e1b036f9bb6d01f2f9005f4116d33b`. WebUI is 2/2 ready and API/worker is 3/3 ready with zero restarts. Only the existing WebUI deployment changed; no OCI infrastructure, account/dependency upgrades, credentials changes or data movement. Temporary preview server and QA tabs closed, viewport restored.

Evidence outside Git: ignored `ags_runtime/ags_oke/compact-review-desktop-proof.png`, `compact-review-mobile-proof.png`, `compact-review-live-checks.json` and `compact-review-local-*`.


## Review evidence status in details — 14 October 2026

Removed the yellow no-evidence notice from the extracted-results pane. Field-evidence metadata is now in the existing Extraction details information dialog: results without evidence show “No verified field citations saved.”; results with evidence show the saved citation count. The extracted values, evidence records, source-document behavior and review/save controls were not changed.

Validation: ARM64 WebUI production build with type checks, existing OKE WebUI rollout and one focused live check of extraction 93ebc191-e304-4401-ad17-a95d67529599 at 683 × 668. The inline notice was absent, the PDF image loaded, the information dialog showed the evidence status, document dimensions matched the viewport and browser error logs were empty. No full suites, AI calls, re-extractions, exports, edits or Reviewed submissions. WebUI is 2/2 ready and API/worker remains 3/3 ready, both with zero restarts.

Active WebUI: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:396465f87f9fbe7b976f27f8017899e8d0aaea4b9f6517bb05f4a004d6b47bf0`. Rollback: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:22dbca5a34686faa7a78110bca9592d3aba860cf01512c2cf8cc32643a38b506`. Only the existing WebUI deployment changed; no new infrastructure, upgrades, backend/model/credential changes or data movement. The temporary QA tab was closed and viewport override reset.

Evidence outside Git: ignored `ags_runtime/ags_oke/review-evidence-details-proof.png`, `review-evidence-details-dialog-proof.png` and `review-evidence-details-checks.json`.


## Compact Review footer — 14 October 2026

Removed the normal-state “Ready for review” footer message and its save/lock explanation. Reviewed and Cancel remain aligned right; the footer minimum height is 48 px. Reviewed's native tooltip explains that it saves and permanently locks the result. Conditional unsaved-change, invalid-JSON and locked-state feedback remains available; save, cancellation, authorization and locking behavior are unchanged.

Validation: ARM64 production build including type checks, existing WebUI rollout and one focused live Review inspection at 683 × 668. The normal footer contains only Cancel and Reviewed, Reviewed retains the lock tooltip, the source PDF loads, the earlier evidence banner is absent, page dimensions equal the viewport and browser error logs are empty. No full suites, AI requests, re-extractions, edits, exports or review-lock submissions.

Active WebUI: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:4e8c2f96e42fbd3eccb39fe32ac2a5268526a1646d28cbc03179e6a77b22e50d`. Rollback: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:396465f87f9fbe7b976f27f8017899e8d0aaea4b9f6517bb05f4a004d6b47bf0`. Only the existing WebUI deployment changed; no new resources, upgrades, backend/model/credential changes or data movement. Temporary QA tab closed and viewport restored. Evidence outside Git: ignored `ags_runtime/ags_oke/review-footer-cleanup-proof.png` and `review-footer-cleanup-checks.json`.


## Remove inline Review re-extraction control — 14 October 2026

Removed the Re-extract results icon from the extracted-results pane and its now-unused local handler. The Review directory's existing Re-extract action remains. Field editing, versions/provenance, source preview, save/cancel and lock behavior are unchanged.

Validation: ARM64 WebUI production build with type checks, existing OKE WebUI rollout and one focused live Review check at 683 × 668. At the bottom of the results pane, the removed control count was zero and Versions and provenance remained. The source PDF loaded, Cancel/Reviewed remained, document dimensions matched the viewport and browser error logs were empty. No full suites, AI calls, re-extractions, edits, exports or review-lock submissions.

Active WebUI: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:2d4070420df255eab5abb2bb98ec6c44f732831a612211a93c4d85bbb212b703`. Rollback: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:4e8c2f96e42fbd3eccb39fe32ac2a5268526a1646d28cbc03179e6a77b22e50d`. Only the existing WebUI deployment changed; no new infrastructure, upgrades, backend/model/credential changes or data movement. Temporary QA tab closed and viewport restored. Evidence outside Git: ignored `ags_runtime/ags_oke/review-remove-inline-reextract-proof.png` and `review-remove-inline-reextract-checks.json`.


## Remove Review versions/provenance section — 14 October 2026

Removed the Versions and provenance disclosure, explanatory copy and Load saved versions control from the extracted-results pane. Saved history and backend endpoints are untouched. The information dialog, extracted fields, source preview and review controls remain.

Validation: ARM64 WebUI production build with type checks, existing OKE WebUI rollout and one focused live check at 683 × 668. The disclosure and Load saved versions control were absent, the source PDF loaded, fields and Cancel/Reviewed remained, page dimensions matched the viewport and browser error logs were empty. The bottom of the extracted-results pane was inspected. No full suites, AI calls, re-extractions, edits, exports, history deletion or review-lock submissions.

Active WebUI: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:5d626c37b38816d6b0f510f088326516e586e265e257414b44041031d6f96cfa`. Rollback: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:2d4070420df255eab5abb2bb98ec6c44f732831a612211a93c4d85bbb212b703`. Only the existing WebUI deployment changed; no infrastructure, upgrades, backend/model/credential changes or data movement. Temporary QA tab closed and viewport restored. Evidence outside Git: ignored `ags_runtime/ags_oke/review-remove-provenance-proof.png` and `review-remove-provenance-checks.json`.


## Remove Review Extraction details control — 14 October 2026

Removed the Extraction details information icon and its associated popup. Removed the unused dialog reference, Info/MergedDetails imports and dialog-specific CSS. The Review toolbar now contains Reload extraction and Download results. Extracted values, source-document preview and save/cancel behavior are unchanged; stored extraction metadata and history are untouched.

Validation: ARM64 WebUI production build including type checks, existing OKE WebUI rollout and one focused live Review check at 683 × 668. The details control and dialog counts were zero, Reload and Download remained, the PDF loaded, fields and Cancel/Reviewed remained, page dimensions matched the viewport and browser error logs were empty. No full suites, AI requests, extractions, edits, exports or review-lock submissions.

Active WebUI: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:6d03a60f3c3ec47cad8a995af5319401ecd6dddd555425cd2761258c264368b0`. Rollback: `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:5d626c37b38816d6b0f510f088326516e586e265e257414b44041031d6f96cfa`. Only the existing WebUI deployment changed; no infrastructure, upgrades, backend/model/credential changes or data movement. Temporary QA tab closed and viewport restored. Evidence outside Git: ignored `ags_runtime/ags_oke/review-remove-details-proof.png` and `review-remove-details-checks.json`.


## Mandatory Unified Chat hybrid retrieval and scoped citations — 14 October 2026

Unified Chat now runs access/dataset/document checks, hybrid vector and keyword retrieval, CPU reranking, model answer generation and answer validation for application help, General chat, document content, prompts, saved results and exact catalog questions. Exact counts/lists/field reads supplement ranked evidence with the complete authorized published catalog. Catalog helpers supply verified facts to the model rather than bypassing generation. Scoped root IDs are enforced before retrieval/reranking; other datasets and unselected documents remain excluded. Greeting shortcuts are disabled only for the vector-backed chat path.

Chat validation normalizes recognizable citation syntax, rejects empty/citation-only answers, unknown references, unsupported completeness and missing numeric exact counts, allows one bounded repair, and records the failure reason. Failed validation does not attach retrieved passages as supporting citations to an error. A chat-only Ollama JSON reply schema requires a non-empty answer plus citation IDs selected by the model from the actual evidence. Shared model adapters and legacy non-chat validation behavior are preserved. These checks validate basic provenance/count constraints, not full semantic truth of every sentence.

Aegis guidance: refreshed all eight application topics to describe dataset-only onboarding with preselected models, separate document/prompt/extraction work, current Review controls, configured Local/OCI destinations and the mandatory chat retrieval sequence. Published into the existing Oracle unified collection; eight guidance entries were upserted, zero entries removed and zero entities failed. An application-only publication mode skips unrelated record synchronization/deletion. No document, Parquet, vector namespace or database destination was moved/reset.

Service changes: only the existing shared API/worker backend image was replaced using Recreate; no jobs were active before cutover. API startup took approximately two minutes loading the existing CPU reranker, so initial 45-second readiness waits timed out before successful rollout; final API/worker is 3/3 ready, WebUI 2/2 ready, both with zero restarts. WebUI, relay, Caddy, model profiles/endpoints, credentials/wallets, mounted state, resources and node sizing are unchanged. Compared Python file hashes against the pre-change live service: only agent_graph.py, chat_agent.py, chat_knowledge.py, chat_policy.py and knowledge.py differ. Onboarding, Upload, Extract and Re-extract processing implementations are unchanged. No upgrades or new OCI resources.

Validation: focused offline scope, mandatory-stage, citation, repair, complete-catalog and guidance-only publication tests; 37 passed / one optional exported-conversation replay skipped in the relevant existing suites, and 15 final focused checks passed after the structured-reply correction. ARM64 backend builds and network-disabled import/validation smoke checks passed with cached pinned dependencies. One live browser round used two questions: “What can you do?” in General chat and “How many documents are in this dataset?” in TermSheet Dataset. Help succeeded with hybrid retrieval (four keyword candidates, eight vector candidates), reranking and a valid citation after one repair. The first count step failed on missing citations on both attempts, leading to the chat-only structured format fix; only that failed step was rechecked. It returned `1 [1]`, matching the complete authorized document catalog, with one eligible vector/citation entirely within TermSheet Dataset and first-attempt validation success. A zero lexical match count for this wording did not bypass the keyword retriever. Saved workflow order explicitly verified Hybrid search < Reranking evidence < Model answering < Validating answer. Final browser error logs were empty. No uploads, new datasets, extraction/re-extraction, exports or Reviewed submissions were used as tests.

Active backend: `bom.ocir.io/bmyljaecivrj/ags-aegis-backend@sha256:dc6e891a3cdcc6ba5241e962c0b0b295f9d6e6b8c73c3bbc911ad9ece46ce409`. Stable rollback: `bom.ocir.io/bmyljaecivrj/ags-aegis-backend@sha256:51af067eb7619dc61775adff193ff793dac1ce1a1328ab65ed6306e735b4b4f3`. The first hybrid-only backend release was superseded by the structured-citation release after the failed count case. Code remains local on branch python; no existing PR was merged. Test questions remain in two saved chat conversations; temporary QA tab closed.

Evidence outside Git: ignored `ags_runtime/ags_oke/chat-required-hybrid-help-proof.png`, `chat-required-hybrid-count-proof.png`, and `chat-required-hybrid-final-checks.json`.


## Unified Chat budget increase — passed — 14 October 2026

User authorized increasing the limits behind “The indexed answer scope exceeds the chat budget.” These are application limits, not an OCI account quota. Unified Chat context increased from 8,192 to 16,384 tokens and evidence from 11,000 to 22,000 UTF-8 JSON bytes. Answer output remains 1,024 tokens, with a 512-token safety reserve. A narrower selected model profile still limits context/output; invalid configurations fail explicitly. Other processing agents and shared model contracts retain their existing budgets.

Where to configure: existing namespace `aegis-oci`, ConfigMap `aegis-config`, keys `AEGIS_CHAT_CONTEXT_TOKENS=16384`, `AEGIS_CHAT_EVIDENCE_BYTES=22000`, and `AEGIS_CHAT_OUTPUT_TOKENS=1024`. Restart the existing API/worker deployment after a ConfigMap change so containers receive the new environment. Canonical deployment defaults are in `ags_deploy/ags_oke/ags_render.py`; chat-specific defaults and guards are in `ags_backend/ags_app/chat_agent.py` (`chat_limits`). Existing model registrations were not edited.

The single-prompt answer previously sent a complete schema plus a second prose copy of its field descriptions. Keep the complete schema/instructions once, omitting only the duplicate summary for a single prompt. TermSheet evidence falls from 26,799 to 19,887 bytes without discarding fields; multi-prompt ambiguity handling and supplementary exact catalog facts remain.

Service changes: patched only the three budget keys in the existing ConfigMap and replaced the existing shared API/worker image using Recreate. No processing jobs were queued/running before cutover. Active backend: `bom.ocir.io/bmyljaecivrj/ags-aegis-backend@sha256:4099fa958f6a3c1ad86eef2c94becb34c66b9add1fa331c97318627223f720af`. Stable rollback: `bom.ocir.io/bmyljaecivrj/ags-aegis-backend@sha256:dc6e891a3cdcc6ba5241e962c0b0b295f9d6e6b8c73c3bbc911ad9ece46ce409`, plus the prior ConfigMap values in ignored `chat-budget-before-config.json`. Initial 45-second readiness wait expired during existing reranker warmup; eventual rollout succeeded. API/worker 3/3 ready and WebUI 2/2 ready, both with zero restarts. WebUI, relay, Caddy, infrastructure, sizing, secrets, wallets, storage and model endpoints are unchanged. No upgrades, new resources, reindexing or data movement.

Validation: seven focused offline checks passed for defaults, narrower model limits, overrides, invalid settings, the new evidence band/oversize guard and full single-prompt packing. Cached-dependency ARM64 backend build and network-disabled ARM64 smoke passed. Only one live question was submitted: “Summarize the instructions in prompt template Aegis_Term_Sheet_Extraction_Prompt_Strict.json.” It succeeded in approximately 35 seconds with citation [1], first-attempt validation and no browser errors. Saved conversation `c2c4b02b-0e9c-4889-81ed-1aa041fe93a8` confirms 19,887 evidence bytes (above the old cap), estimated total 13,004 tokens including the 1,024-token answer reservation and 512 safety tokens, context limit 16,384 and dispatch allowed. Hybrid retrieval produced eight keyword and eight vector candidates, one fused eligible entity, and reranking took 437.31 ms. Saved workflow confirms hybrid search, reranking, model answer, then validation. Scope remained TermSheet Dataset (`53f60083-1dc6-587c-bb12-f296be00f889`). No full suites, extraction/re-extraction, uploads or review locking. Temporary QA tab closed; saved test chat retained.

Evidence outside Git: ignored `ags_runtime/ags_oke/chat-budget-16k-proof.png`, `chat-budget-16k-checks.json`, `chat-budget-config-patch.json`, `chat-budget-before-config.json` and `release-before-chat-budget-16k.json`.


## User deletion and Arjun access removal — 15 October 2026

Added an administrator-only trash action to Users & passwords. HTTP deletion requires the acting administrator password and exact username confirmation, revokes every target session and dataset assignment, protects the current account and last administrator, and rejects removal of accounts owning shared content or processing jobs. Private conversation and agent-plan metadata is removed from the active catalog and archived with artifact and historical audit references under protected account-archives on the existing application volume. Password hashes and session credentials are excluded. Original private payload files remain stored; shared content is preserved.

Removed the explicitly requested Arjun account: one sign-in session and one dataset assignment revoked, 22 private records archived. Verified the user, sessions and assignments are absent. Shared counts are unchanged: 8 datasets, 15 documents, 27 extraction results, 17 model records and 8 templates.

Published ARM64 backend `bom.ocir.io/bmyljaecivrj/ags-aegis-backend@sha256:fe2ea263dd76ef2a1b50a56b2b26cab0eb81da43cbf0c852dd270f5b8d046ae5` and WebUI `bom.ocir.io/bmyljaecivrj/ags-aegis-web@sha256:12336119afcca52b7eb9bbc34329cc967279787398406a637b52d2b4740b31fc`. The backend layers the account-management module onto the preceding deployed backend, preserving other live processing code. Previous deployment templates and image references are in ignored `ags_runtime/ags_oke/user-deletion-before-deployments.json`. Existing infrastructure, resources, configuration, wallets, secrets and destinations were retained.

Validation: 24 existing backend account/role checks passed; six new account-deletion checks passed after correcting their fixture import; seven frontend role/deletion checks passed; TypeScript check and production build passed. Live Oracle deletion succeeded; API/worker is 3/3 ready and WebUI 2/2 ready with zero restarts. One browser round verified Arjun is absent, trash controls are present, self-deletion is disabled, the delete confirmation requires administrator password and exact username, and Cancel closes the form without deleting User1. No inference/extraction verification jobs or new accounts were created.
