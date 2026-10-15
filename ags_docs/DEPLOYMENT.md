# Aegis deployment and fresh onboarding

Freeze reference: `aegis-freeze-2026-10-15`. Prepared 15 October 2026. This guide contains operator instructions for a future authorized installation or release. Preparing and pushing the handover does not execute them or disturb the current deployed application.

## Choose the correct deployment path

- **Separate local environment:** follow [the root README](../README.md) or [Oracle setup](ORACLE.md). Use independent database, content and secrets.
- **Empty OCI destination:** prepare infrastructure and the initial application installation described below. The historic `ags_oke` provisioner and renderer are tied to the recorded pilot; the renderer requires seeded state. They are not a general new-tenancy installer.
- **Prepared OKE installation:** follow the code release and onboarding steps below. No region restriction is imposed by `deploy-aegis-code.ps1`.

## Runtime settings for this freeze

The source of operational limits is `ags_backend/ags_app/ags_config/runtime.toml`; see [runtime configuration](RUNTIME-CONFIG.md). Current ceilings are 262144 context tokens, 1000000 evidence bytes and 1024 answer tokens, subject to each saved model's smaller limits. The OCI profile requires local reranker files at `/data/models/reranker`. Do not follow earlier ConfigMap-only budget examples as the current source of settings.

The release script builds with `INSTALL_CLOUD_MODELS=false` and `INSTALL_LOCAL_EMBEDDINGS=false`, plus Oracle and OCI enabled. This suits the recorded Ollama/OCI topology. If a destination uses native cloud adapters or local sentence-transformers, build and verify the required optional packages before deploying that image. Use `-SkipBuild` only for the exact verified destination tags.

## 1 Confirm the fresh installation handoff

The destination platform must be ready before running the code deployment script. Obtain these items from the person responsible for that environment:

| Item | Required handoff |
| --- | --- |
| Kubernetes access | A separate kubeconfig for the destination cluster and its exact context name |
| Container registry | Registry hostname, destination tenancy namespace and permission to push images |
| Private repositories | `ags-aegis-web` and `ags-aegis-backend`, with image-pull credentials configured in Kubernetes |
| Application workloads | Namespace `aegis-oci`; deployments `aegis-web` and `aegis-api-worker` |
| Container names | `web` in the frontend deployment; `api` and `worker` in the backend deployment |
| Fresh application state | Separate persistent configuration and state, a fresh application database/schema and content destination, with no old workspace restored |
| Database and storage | Destination connection settings, wallet where required, credentials and bucket access configured outside the application images |
| Application secrets | A new workspace encryption key and installation bootstrap token, supplied through the deployment's secret mechanism |
| Runtime prerequisites | Runtime configuration, reranker files, HTTPS endpoint and required supporting services installed |
| AI connectivity | Reachable model endpoints; for laptop-hosted models, the destination's relay configured and running |
| Application address | The new installation's HTTPS URL |

The existing encryption key must remain stable across future releases of this workspace. New application versions must remain compatible with its schema and stored configuration.

**First installation boundary:** `deploy-aegis-code.ps1` updates existing application workloads. It does not create the initial workloads, prepare their persistent configuration, initialize a database or install secrets. A completely empty cluster needs that application installation handoff first. The old deployment renderer expects seeded runtime state; running it against an empty volume is not a fresh installer.

Do not copy the original tenancy's runtime folder, wallet, encryption key, application secrets or user database into a fresh workspace. Do not use **START FRESH** on the existing workspace to prepare another tenancy; that feature resets the workspace you are currently using.

**Ready to continue:** the destination application workloads exist and their fresh runtime configuration belongs to the destination environment.

## 2 Prepare the release computer and source

1. Start Docker Desktop.
2. Open PowerShell and confirm Docker and kubectl work:

```powershell
docker version
kubectl version --client
```

3. Use a clean checkout of the Aegis freeze tag. An example checkout location is:

```text
C:\work\Aegis
```

4. Confirm it contains `ags_frontend/Dockerfile` and `ags_backend/Dockerfile`.
5. Run from the repository root. The release script is checked in at `ags_deploy/deploy-aegis-code.ps1`. Receipts are private files under `ags_deploy/deployment-records/`.

Build from a clean checkout of the freeze tag so local changes cannot enter an image unnoticed. The script builds the selected working directory, including changes allowed by the component Docker ignore rules. Record the Git tag and commit with the deployment receipt.

## 3 Enter destination settings once

Copy this block into PowerShell. Replace every `YOUR_...` value and the kubeconfig path before continuing. If you move the guide and script, change `$taskGuideFolder`.

```powershell
$taskGuideFolder = Join-Path (Get-Location).Path "ags_deploy"
$taskDeployScript = Join-Path $taskGuideFolder "deploy-aegis-code.ps1"
$taskSource = (Get-Location).Path
$taskKubeconfig = "C:\path\new-tenancy-kubeconfig.yaml"
$taskContext = "YOUR_NEW_CLUSTER_CONTEXT"
$taskRegistry = "YOUR_REGISTRY_HOST"
$taskRegistryNamespace = "YOUR_NEW_TENANCY_NAMESPACE"
$taskNamespace = "aegis-oci"
$taskPlatform = "linux/arm64"
$taskRelease = "release-20261015-01"
$taskBaseUrl = "https://YOUR_AEGIS_HOST"
```

- **Registry hostname:** use the hostname supplied for the destination's OCI Container Registry. The script has no region allowlist and does not require Mumbai.
- **Registry namespace:** use the destination tenancy's Object Storage namespace, not its display name, tenancy OCID or Kubernetes namespace.
- **Context:** select the destination cluster explicitly. The script does not rely on your current default context.
- **Platform:** `linux/arm64` matches the existing A1 setup. Use `linux/amd64` for an x86 destination. This is a build parameter; no application source change is required.
- **Release:** choose a new tag for each new release and record it. Avoid reusing a tag for different code.

These settings select the release destination. They do not change infrastructure or connection settings inside the running workspace.

## 4 Log in to the destination registry

```powershell
docker login $taskRegistry
```

Enter the destination registry username and an OCI **auth token** when prompted. The username normally uses `tenancy-namespace/username`; federated accounts can require `tenancy-namespace/domain-name/username`. Use the format appropriate to the destination account. The password prompt expects an auth token rather than your Console password. [Oracle registry login instructions](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrypushingimagesusingthedockercli.htm)

Keep passwords, tokens and private keys outside this guide, source code and release commands. The cluster needs its own working image-pull credentials; signing in on your computer does not configure them.

**Expected result:** Docker reports that login succeeded.

## 5 Verify the destination before publishing

Run each command separately. Stop and resolve any error before moving on.

```powershell
kubectl --kubeconfig $taskKubeconfig config get-contexts
```

Confirm `$taskContext` is the intended destination context, then inspect its server and application deployments:

```powershell
kubectl --kubeconfig $taskKubeconfig --context $taskContext config view --minify
```

```powershell
kubectl --kubeconfig $taskKubeconfig --context $taskContext -n $taskNamespace get deployments aegis-web aegis-api-worker
```

```powershell
kubectl --kubeconfig $taskKubeconfig --context $taskContext -n $taskNamespace get pods
```

If either deployment is missing, return to the first installation handoff in Step 1. The code release script cannot fill that gap. If Pods already fail because configuration, a wallet, a secret, model weights or storage are missing, resolve that setup problem before publishing a code release.

For an existing workspace, finish active uploads, indexing and extraction jobs before deployment. The current backend deployment uses `Recreate`; a release can briefly interrupt the API and worker.

## 6 Deploy the application code

With the settings from Step 3 still loaded in PowerShell, run:

```powershell
& $taskDeployScript `
  -SourcePath $taskSource `
  -Kubeconfig $taskKubeconfig `
  -Context $taskContext `
  -Registry $taskRegistry `
  -RegistryNamespace $taskRegistryNamespace `
  -Namespace $taskNamespace `
  -Platform $taskPlatform `
  -Release $taskRelease
```

The script performs this sequence:

1. Checks the destination and expected application container names.
2. Builds the frontend and backend images. The backend includes the Oracle and OCI dependencies used by the current architecture.
3. Verifies the built image architecture and pushes both images to the destination registry.
4. Saves the previous application images, destination and new image digests under ignored `ags_deploy/deployment-records/`.
5. Updates the `api` and `worker` containers to the same backend image digest and waits for readiness.
6. Updates the `web` container to the frontend image digest and waits for readiness.

The script changes application image references through Kubernetes. It leaves supporting services, infrastructure and externally supplied runtime settings in place. Image updates use the standard [`kubectl set image` operation](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_set/kubectl_set_image/).

Allow roughly **10–30 minutes** for a prepared environment. A cold build, ARM64 emulation on an x64 laptop, a slow upload or an image download can extend this estimate. Each rollout wait allows up to 15 minutes.

**Expected result:** the script reports that both image rollouts completed. This confirms deployment readiness, not the complete application workflow.

## 7 Create the first administrator

1. Open the new installation's HTTPS address from Step 3.
2. On an empty, initialized application database, the page should show **Create your workspace**.
3. Enter the installation's **Bootstrap token**, a username and a password of at least 12 characters.
4. Select **Create administrator**. Sign in with that account if prompted.

The bootstrap token must match the destination's server-side `AEGIS_BOOTSTRAP_TOKEN`. Obtain it through the installation's secret handoff; it is not your OCI password or registry token.

If the page shows ordinary sign-in on an installation intended to be empty, check whether the selected database already contains a user. If it reports **Administrator already configured**, use the existing destination administrator account and inspect the installation state. Do not reset another workspace to force bootstrap.

**Expected result:** the administrator reaches Home with no previous workspace datasets or documents.

## 8 Verify application connections

Open **Manage workspace → Storage**.

1. In **Database & knowledge**, verify that the active database is the destination supplied for this workspace. Test the connection and native vector support.
2. In file storage, verify the destination namespace, bucket, prefix and authentication configuration. Test the connection.
3. If a saved destination is incomplete, have the installation operator correct the external configuration. The Storage screen also supports saving database settings, creating Aegis tables and activating a configured database; those are deliberate application setup operations, separate from publishing code.
4. Verify API and worker share the required persistent application state, wallet and encryption key.

Connection tests do not prove every write operation. The single onboarding check in Step 11 verifies an actual document and result flow.

## 9 Register and test the models

Open **Manage workspace → Model Registration**. Create the required registrations:

| Role | Example for the existing laptop model architecture |
| --- | --- |
| Embedding | `nomic-embed-text` |
| Chat | `qwen3:4b` |
| Extraction | `qwen3:4b`, registered separately for the Extraction category |

For each registration:

1. Enter a clear name and select the correct category and connection protocol.
2. Enter the actual endpoint and installed model identifier for this environment.
3. Supply authentication when the selected provider requires it.
4. Set limits within the model's supported capacity.
5. Run **Test Connection**, then **Save Model**, and confirm the model is enabled.

For the same laptop relay architecture, the backend reaches Ollama through `http://ollama:11434` once the destination relay is configured. A server-side `127.0.0.1` address points to that server/container, not your laptop. Keep laptop Docker/Ollama and the destination's relay running. Use the destination's relay settings rather than restarting a relay configured for the original tenancy.

Configure OCR separately if your documents require it. Use the model that is installed and supported by your selected OCR connection.

## 10 Onboard the first dataset

1. Open **Datasets** and select **New dataset**.
2. Enter a name such as `Onboarding Test` and a short description, then save.
3. Open **Model Mapping** and select that dataset.
4. Assign the saved **Embedding**, **Chat** and **Extraction** registrations.
5. Select **Save & Apply** and keep the dataset **Active**.

Alternatively, an administrator can use **Onboard dataset** in Aegis Agent, review the proposed setup and confirm it. Use the options displayed by your deployed release; review its dataset and model selections before confirming.

New users do not automatically receive dataset access. Add users through **Manage workspace → Users & passwords**, then use **Dataset access** to assign this dataset as needed.

## 11 Run one focused application check

Use one small document containing harmless test content. A small text document such as “Company: Example Ltd. Amount: 1250.” is sufficient for a basic check.

1. Select the new dataset and upload the document. Confirm the destination and any external-processing notice shown by the application.
2. Wait until indexing completes and the document is ready.
3. Add a prompt template through **Prompt Templates**, using a valid JSON Schema and instructions to return only values supported by the document. For a simple test schema, use:

```json
{
  "type": "object",
  "properties": {
    "company": { "type": "string" },
    "amount": { "type": "number" }
  },
  "required": ["company", "amount"],
  "additionalProperties": false
}
```

4. Run extraction with that document, template and mapped Extraction model. Review any execution confirmation before starting it.
5. Open **Review** and confirm the result matches the document.
6. Ask a question about the same document using the mapped Chat model. Confirm the answer and its citations resolve to the selected document.
7. Verify the document and result remain available after refreshing the application.

Unified Chat must enforce access and dataset/document scope, retrieve evidence with hybrid search, rerank, generate the answer and validate its citations. A successful model connection alone does not verify this workflow.

Run this check once. Repeat only a failed step after fixing its cause. Live model tests, extraction and chat may incur usage charges for the configured services.

**Onboarding is complete when:** administrator access, model connections, dataset mappings, document indexing, extraction, saved results and cited chat all work in the destination workspace.

## 12 Publish later functionality changes

For the next release:

1. Finish the intended technical or functionality changes in the selected source checkout.
2. Run the focused checks appropriate to those changes.
3. Confirm no processing jobs are active in the destination.
4. Set `$taskRelease` to a new value and rerun Step 6 with the same destination settings.
5. Run one focused application check and retain the release record.

Do not rerun administrator creation, recreate datasets, change regions, reset storage or rebuild infrastructure for a normal code release. Database migrations and runtime configuration changes require their own explicit release instructions when a feature actually needs them; the image deployment script does not perform them.

To reuse images already built and tagged locally for this exact registry, namespace and release, add `-SkipBuild` to the Step 6 command. Both local tags must exist as `REGISTRY/NAMESPACE/ags-aegis-web:RELEASE` and `REGISTRY/NAMESPACE/ags-aegis-backend:RELEASE`. The script still uploads them and deploys their digests.

## 13 Resolve deployment problems

| Symptom | Next action |
| --- | --- |
| Registry login or push denied | Check the destination auth token, username format, namespace, repository and push permission |
| Deployment not found | Check kubeconfig, context and namespace; complete the first installation handoff if the workloads are absent |
| `ImagePullBackOff` | Check that the pushed image exists and the destination's image-pull credentials can read its private repository |
| Architecture or executable error | Confirm the build platform matches the destination worker architecture |
| Init container fails | Inspect its error; check fresh persistent configuration, database credentials, storage selection and reranker files |
| API or worker does not become ready | Inspect logs and events; check database reachability, wallet, encryption key, runtime configuration and model weights |
| Model test fails | Check the model identifier, protocol, reachable endpoint and credentials; for laptop AI, check the destination relay and laptop sleep state |
| Dataset has no usable model | Enable the registration, assign the correct category and save the dataset mapping |

Read-only diagnostic commands:

```powershell
kubectl --kubeconfig $taskKubeconfig --context $taskContext -n $taskNamespace get pods
```

```powershell
kubectl --kubeconfig $taskKubeconfig --context $taskContext -n $taskNamespace get events --sort-by=.metadata.creationTimestamp
```

```powershell
kubectl --kubeconfig $taskKubeconfig --context $taskContext -n $taskNamespace logs deployment/aegis-api-worker -c api --tail=80
```

Keep diagnostic output containing private application data within the workspace's support process.

## 14 Restore previous application images when needed

The release script stops on a failed command; it does not automatically undo earlier successful updates. If backend deployment succeeds but frontend deployment fails, inspect both versions before deciding what to restore.

1. Open the JSON record for the attempted release in `deployment-records` beside the script.
2. Copy the relevant image references from its **previous** section. Preserve separate API and worker references if they differ.
3. Restore only the deployments changed by the failed release. Replace the three placeholders below with the recorded previous image references:

```powershell
$taskPreviousApiImage = "YOUR_PREVIOUS_API_IMAGE"
$taskPreviousWorkerImage = "YOUR_PREVIOUS_WORKER_IMAGE"
$taskPreviousWebImage = "YOUR_PREVIOUS_WEB_IMAGE"
```

Restore backend images if needed:

```powershell
kubectl --kubeconfig $taskKubeconfig --context $taskContext -n $taskNamespace set image deployment/aegis-api-worker "api=$taskPreviousApiImage" "worker=$taskPreviousWorkerImage"
```

```powershell
kubectl --kubeconfig $taskKubeconfig --context $taskContext -n $taskNamespace rollout status deployment/aegis-api-worker --timeout=15m
```

Restore the frontend image if needed:

```powershell
kubectl --kubeconfig $taskKubeconfig --context $taskContext -n $taskNamespace set image deployment/aegis-web "web=$taskPreviousWebImage"
```

```powershell
kubectl --kubeconfig $taskKubeconfig --context $taskContext -n $taskNamespace rollout status deployment/aegis-web --timeout=15m
```

Restoring images does not reverse database or content changes. Confirm the previous release remains compatible with the workspace before restoring it.


## Source freeze and validation

Checkout the immutable freeze tag before building. Use `npm ci` and the committed Python locks. Run the checks in [RELEASE-FREEZE.md](RELEASE-FREEZE.md). Preserve the Git tag, source manifest, build flags, image digests and previous deployment receipt together. The script records image and destination information; record the source tag in the operator release log as well.

Cloud restore requires coordinated Oracle, Object Storage and shared-state recovery. The local PostgreSQL backup/restore shell scripts do not establish cloud recovery readiness. An image rollback does not reverse data, schema or credential changes.
