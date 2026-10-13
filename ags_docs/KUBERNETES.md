# Aegis on Oracle Kubernetes (OKE)

These manifests run the same web/backend images, Oracle Free database, Qdrant and
Ollama models as local Docker. They are a single-workspace pilot configuration,
not a validated high-availability deployment. No live Oracle cluster was used.
Use `ags_deploy/ags_kubernetes/ags_base` on CPU; the GPU overlay changes only Ollama's resource
allocation. Neither application code nor user workflows depend on laptop hardware.

The model-provisioning init container also installs `qwen2.5vl:3b` for scanned
PDFs and visible DOCX raster images. [OCR configuration](OCR.md) uses the same
environment variables and application images locally and on OKE. Native-only
files bypass vision inference. Validate actual transcription and review against
originals with `python -m ags_app.ocr_smoke` and the complete container smoke check;
readiness alone does not certify OCR accuracy or model inference.

## Prerequisites

- An OKE cluster with Linux amd64 nodes, kubectl access and a default CSI storage
  class supporting ReadWriteOnce volumes. Verify the exact Oracle image's target
  architecture before choosing ARM nodes. Allow at least 100 GiB of persistent
  storage across the four claims and enough node capacity for all CPU/memory
  requests (including system workloads). The Ollama limit is 8 GiB; benchmark and
  adjust CPU/memory budgets for your actual templates and concurrency.
- A private registry your nodes can pull from, containing the current app images.
  Oracle registry authentication/license requirements must be satisfied separately.
  Add `imagePullSecrets` when required. No credentials are embedded in manifests.
- Private DNS/network reachability among services; outbound model downloads from
  Ollama. The NetworkPolicy requires a CNI that enforces it. Only ClusterIP services
  are provided; the initial test uses a local port-forward. Do not expose database,
  vector or model services publicly.
- For NVIDIA GPU mode only: compatible GPU nodes, driver, container runtime and
  NVIDIA device plugin advertising `nvidia.com/gpu`. The CPU base requires none.
  The current pinned Ollama image/auto probe targets NVIDIA; AMD/Intel acceleration
  is not configured or validated. Auto uses CPU if compatible access is absent.

API and worker share one Pod and the same `/data` PVC, UID and filesystem locks.
Keep replicas at **one** and the Recreate strategy. Independently scaling these
components requires a shared-storage/locking design and further validation.
Oracle, Qdrant and Ollama have separate persistent claims. This creates a fresh
cluster workspace; existing laptop data is not automatically migrated. See the
backup/restore guide before any data transfer; preserve its master key.

## Prepare images and configuration

Build using the existing Dockerfiles (substitute your private registry/tag):

```sh
docker build --build-arg INSTALL_ORACLE=true --build-arg INSTALL_LOCAL_EMBEDDINGS=false --build-arg INSTALL_CLOUD_MODELS=false -t REGISTRY/aegis-backend:TAG backend
docker build -t REGISTRY/aegis-web:TAG frontend
docker push REGISTRY/aegis-backend:TAG
docker push REGISTRY/aegis-web:TAG
```

Set Kustomize image replacements in a deployment-specific overlay or with
`kubectl kustomize`/Kustomize image editing:

```yaml
images:
  - name: aegis-backend
    newName: REGISTRY/aegis-backend
    newTag: TAG
  - name: aegis-web
    newName: REGISTRY/aegis-web
    newTag: TAG
```

Create namespace `aegis` and a Secret named `aegis-secrets` there, using your private
configuration/secret manager. Required keys:

| Key | Source/value |
| --- | --- |
| `master-key` | Existing `AEGIS_MASTER_KEY` (Fernet key); preserve for encrypted data |
| `bootstrap-token` | Existing `AEGIS_BOOTSTRAP_TOKEN` |
| `oracle-password` | `secrets/oracle/admin-password` |
| `database-password` | `secrets/oracle/app-password` |
| `test-database-password` | `secrets/oracle/test-password` |

Use file/secret-manager inputs rather than passwords in command-line arguments.
Trim trailing newlines from Secret values, especially the Oracle admin password
which becomes `ORACLE_PWD`. Do not commit the generated Secret manifest.
The included Oracle account startup/health scripts mirror Docker's scripts.
The application owner is `AGS_OWNER`; fresh volumes create it automatically.
Existing AEGIS data must be migrated during a maintenance window using
[the migration procedure](../ags_database/ags_migrations/01_aegis_to_ags_owner.md), with the same
application storage mounted. Changing the ConfigMap alone does not migrate data.
Adjust `aegis-config.ALLOWED_ORIGINS` to the real HTTPS origin if adding an ingress.
Configure TLS, ingress upload limits (20 files, each up to the app limit), request
and streaming timeouts, authentication and backups for that deployment. Extraction
runs asynchronously in the worker; do not hold an ingress request open for the
whole inference. There is no ingress/load balancer created by these manifests.

## Render, then validate on your cluster

Rendering **does not deploy**:

```powershell
./ags_scripts/render-kubernetes.ps1 -Hardware Auto -OutputPath work/kubernetes-rendered.yaml
```

Auto reads cluster nodes and allocated GPUs, choosing the NVIDIA overlay only when
an untainted Ready node has a free advertised GPU. Without cluster inventory/RBAC
it warns and renders CPU. `-Hardware Cpu` never checks GPUs. `-Hardware Gpu` fails
unless that capacity was verified. GPU limits are mandatory scheduler allocations;
Ollama cannot discover an unallocated cluster GPU from a CPU Pod. Capacity can change
after rendering, and inventory does not prove the device/plugin can run this model.
For tainted GPU node pools, configure the corresponding tolerations/affinity in a
site overlay and validate scheduling rather than blindly tolerating every taint.

After replacing images and preparing secrets, an operator can review and run:

```sh
kubectl apply --dry-run=server -f work/kubernetes-rendered.yaml
kubectl apply -f work/kubernetes-rendered.yaml
kubectl -n aegis get pods,pvc
kubectl -n aegis rollout status statefulset/oracle --timeout=30m
kubectl -n aegis rollout status deployment/api --timeout=60m
kubectl -n aegis rollout status deployment/web --timeout=20m
kubectl -n aegis exec deployment/api -c api -- python -m ags_app.container_smoke
kubectl -n aegis port-forward service/web 3003:3000
```

These are operator instructions, not actions performed during preparation.
The API init container waits for the real database application account, Qdrant
and Ollama, then pulls the required models onto Ollama's persistent volume.
Large first downloads can take longer than later starts; inspect init logs if
startup stalls. API startup/readiness probes check database/vector availability;
the smoke test additionally verifies installed models, actual JSON generation,
embedding and observed GPU offload (`size_vram_bytes`), rather than host inventory.

If GPU scheduling/access fails, render/apply the CPU base explicitly; do not leave
CPU-only nodes waiting for an impossible GPU request. Auto selection is performed
when rendering, not a live scheduler failover controller. A GPU exposed but too
small for the full model can lead Ollama to partial CPU offload; inspect smoke
output and `ollama ps` instead of assuming 100% GPU.

Open `http://localhost:3003`, create the initial account, register the three local
connections to `http://ollama:11434`, map them to a dataset and run the fictional
resume pack. For the detailed template use extraction context 8,192/output 2,048,
one resume per extraction, and a measured CPU timeout budget up to 1,800 seconds.
The same limits are configured through Model Registration in both deployments.

The cluster acceptance gate remains: server-side dry-run/RBAC, image pulls,
PVC provisioning/permissions, Oracle account startup, init model downloads,
health probes, smoke test, upload/confirm/extract/review, persistence after restart,
and GPU/CPU observations on the actual OKE nodes. Local rendering/schema checks
cannot prove these cluster-specific properties.
