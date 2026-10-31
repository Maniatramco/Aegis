---
name: aegis-oci-replicate
description: Replicate the complete Aegis OCI infrastructure (networking, OKE, Autonomous AI Database, Object Storage, OCIR, IAM, Kubernetes Secrets/ConfigMaps, HTTPS, reranker, models) on a new or colleague's OCI tenancy, then hand over to the normal aegis-deploy release workflow. Use when someone asks to set up, onboard, clone or rebuild Aegis in another tenancy/region from scratch.
---

# Replicate Aegis on a new OCI tenancy

This skill covers the one-time **provisioning and first install** of a new destination.
It fills the gap that [aegis-deploy](../aegis-deploy/SKILL.md) explicitly does not
cover: aegis-deploy only updates an *already prepared* installation. Once this skill has
finished and the handover checklist (section 10) passes, use aegis-deploy for every later release.

Reference values come from the live Mumbai pilot (`ap-mumbai-1`, v26.1.12.18, branch
`ags_sprint1`, verified 26 Oct 2026). They describe that installation; they are not defaults
for the new tenancy. Use new names, CIDRs, OCIDs, credentials and keys for the new
destination. Sources: `ags_docs/Aegis_OCI_Deployment_Guide.pdf` pp. 2-7, the
`ags_docs/Aegis_Architecture_Handover.pdf`, the retired pilot helpers in git history
(`ags_deploy/ags_oke/ags_provision.py`, `ags_render.py`, `ags_registry.py`, deleted in
commit `ff49e35`) and the current release guard (`ags_deploy/scripts/check-code-release.py`).

## Ground rules

- **Approval is MANDATORY at every gate below. No exceptions.** Before each gate, tell the human in plain
  words *what you are going to do*: the exact resources/commands, the target (tenancy, region, compartment,
  kubeconfig context), sizing, cost impact and what cannot be undone. Then **stop and wait** for their explicit
  approval of that gate. Silence, an earlier approval, a general "go ahead", shared credentials or a
  successful previous step are **not** approval for the next gate. If anything in the plan changes, explain the
  change and ask again. Never type, pipe, prefill or auto-answer `PROVISION`, `DESTROY`, `CONNECT` or `PUBLISH`;
  the human types them. If the human declines, stop and report what was (not) done. Record every OCID created
  (template in section 10).
- **Secrets.** Never copy the pilot's kubeconfig, OCI API key, auth token, wallet,
  `AEGIS_MASTER_KEY`, bootstrap token or `/data` volume to the new tenancy. Generate new ones.
  Keep all secrets out of Git, images, JSON inputs, command arguments, chat and logs. Use
  `kubectl create secret ... --from-file` from a private folder (for example `C:\aegis-target\`).
- **Never touch the live pilot.** Use a separate kubeconfig file per destination and check
  `kubectl config current-context` before every `apply`.
- Do not use local Compose files, `container_prepare` or `ags_local_use/ags_kubernetes/`
  as the OCI installer. They are a separate design that uses Oracle Free, Qdrant and Ollama.

## Mandatory approval gates

| Gate | Before you run | Tell the human | They approve by |
| --- | --- | --- | --- |
| G0 Read-only discovery | `oci` / `terraform plan` / `kubectl get` against their tenancy | Which account/profile/region you will inspect; nothing is created | Saying yes |
| G1 Provision infrastructure | `Provision-Aegis.ps1` (Terraform apply) or any Console/CLI create in sections 2-5 | The full plan list it prints: every resource, node size, DB size, bucket, IAM, cost, region/compartment | Typing `PROVISION` (and `DESTROY` if the plan removes anything) |
| G2 Database schema | `Deploy-Aegis.ps1` with `DB_Object=Y` (section 4) | Owner user to be created, 13 tables, quota, target DB/service | Typing `CONNECT`, then `PUBLISH` after reviewing the printed plan |
| G3 Push images | first `docker buildx ... --push` (section 5) | Registry/repositories, tags, architecture, source commit | Saying yes |
| G4 Kubernetes secrets & base | section 6 `k create secret/configmap`, `01-base.yaml` | Cluster context (must be the NEW one), namespace, which Secrets (names only, never values), two 50 GB volumes | Saying yes |
| G5 Public load balancer | `02-public-service.yaml` | A billable public LB with ports 80/443 open to the internet | Saying yes |
| G6 Seed state | seed pod + `seed_oci_state.py` + reranker copy (section 7.4) | What files are written to `/data`, temporary password Secret created and deleted | Saying yes |
| G7 Start the application | `03-config.yaml`, `04-workloads.yaml` | Images/digests, hostname, that the app becomes publicly reachable | Saying yes |
| G8 Every later release | `Deploy-Aegis.ps1` (aegis-deploy skill) | The printed release plan | Typing `CONNECT`, then `PUBLISH` |

Use this message shape before each gate:

> **Gate G1: Provision infrastructure (needs your approval).** I am going to run `Provision-Aegis.ps1` against
> tenancy `<name>`, region `<region>`, compartment `<name>`. It will create: <list>. Estimated cost: <...>.
> The database and bucket are protected from deletion. Nothing has been created yet. Do you approve? If yes,
> type `PROVISION` at the prompt yourself.

## 0. What you are building

```
Internet ──80/443──> OCI flexible LB (10 Mbps)  [Service aegis-public]
                          │
              ┌───────────▼─────────── OKE Basic cluster, 1x A1.Flex ARM64 node ─────────────┐
              │ Deployment aegis-web          Deployment aegis-api-worker (Recreate, 1 replica) │
              │  ├ web   (Next.js :3000)        ├ init verify-existing-oci-state               │
              │  └ https (Caddy :80/:443)       ├ api    (FastAPI :8000)  ◄─ Service api        │
              │     PVC https-state 50Gi        └ worker (python -m ags_app.worker)            │
              │                                    PVC application-state 50Gi at /data         │
              └───────────────┬───────────────────────┬────────────────────┬──────────────────┘
                              │ mTLS wallet           │ OCI API key        │ HTTPS
                  Autonomous AI DB 26ai       Object Storage bucket    Google Gemini API
                  (tables + native VECTOR)    (originals, results)     (embed/chat/extract/OCR)
                  CPU reranker (ONNX MiniLM) runs inside api/worker from /data/models/reranker
```

## 1. Prerequisites and decisions (collect before starting)

| Item | Pilot value | New tenancy: decide/collect |
| --- | --- | --- |
| Tenancy, home region, target region | `ap-mumbai-1` | Region with A1 (or chosen shape) capacity |
| Compartment | (pilot compartment) | New dedicated compartment, e.g. `aegis` |
| Operator identity | OCI user + API key profile | Operator user in an admin group for the compartment, OCI CLI profile on the operator machine |
| App service identity | API-key user whose config is in Secret `oci-credentials` | Separate low-privilege user `aegis-app` + API key (section 3) |
| Budget/limits | Free-tier-sized pilot | Check service limits: A1 OCPUs, LB, block volume, ADB ECPU |
| Node architecture | `linux/arm64` | Same, unless you choose an x86 shape (then build `linux/amd64`) |
| Model provider | Google Gemini API (`generativelanguage.googleapis.com`) | Registered after deployment (section 8); no key needed to deploy. Nodes only need outbound HTTPS to it |
| Public hostname | `aegis.<LB-IP>.sslip.io` | sslip.io from the LB IP, or a real DNS name you control |
| Operator machine | Windows, PowerShell 5.1+, Docker Desktop, Python 3.12, kubectl, OCI CLI, Git | Same. `Setup-Aegis.ps1` installs what is missing. OCI Cloud Shell (Podman) is an alternative |

Operator machine tools: `git`, `py -3.12`, `kubectl` (version compatible with the cluster),
OCI CLI (`oci`), Docker Desktop with Linux containers and buildx (it builds arm64 through
QEMU), and at least 10 GiB free disk space. If the DB release is selected, also the pinned
Oracle driver (`ags_backend/requirements-oracle.txt`).

### Inputs the AI will ask the human for

An agent following this skill cannot invent these. Collect them up front:
- Tenancy, region, compartment, cost approval, node shape and architecture, Kubernetes version, VCN CIDRs, the operator's public `/32`.
- Hostname choice (sslip.io or own DNS) and whether to reserve a public IP.
- ADB sizing and owner quota; owner name and TNS alias. ADMIN, wallet and owner passwords are typed by the human at hidden prompts only.
- Bucket name, prefix, versioning; where OCIR repos live (tenancy root or compartment); registry user, identity domain, auth tokens.
- The `aegis-app` API key (and passphrase if any) for Secret `oci-credentials`.
- Not needed during deployment: the Gemini API key and model choices. The administrator registers models in the browser after the install (section 8). Do not ask for them earlier.
- Offline backup location for `AEGIS_MASTER_KEY`.
- A truthful `ValidationReference`; typing `CONNECT` and `PUBLISH` at every release gate.
- Authorization for acceptance tests that write data or call model providers.

## Fast path: Terraform (recommended)

`ags_deploy/ags_terraform/` provisions everything in sections 2-5 that does not involve a secret: compartment, VCN,
subnets, security lists, OKE cluster and node pool, Autonomous AI Database, bucket, OCIR repositories and (optionally) IAM.
It needs three inputs (`tenancy_ocid`, `region`, `operator_cidr`) plus the ADMIN password at a prompt.
Read its [README](../../../ags_deploy/ags_terraform/README.md). Pass gate G0, run
`.\Provision-Aegis.ps1 -PlanOnly`, show the human the printed list, then pass gate G1: the human runs
`.\Provision-Aegis.ps1` and types `PROVISION` themselves (never run `terraform apply` directly or with `-auto-approve`).
Then use `terraform output` for the kubeconfig and wallet commands,
the LB subnet OCID, the deployment JSON values and the seed values, and continue at **section 4 step 4** (schema), the
first image build in section 5, then sections 6-9. Sections 2-5 below describe the same resources for manual/Console
creation and review.

## 2. Networking and OKE cluster

Use OCI Console (Networking, then Developer Services > Kubernetes Clusters > **Custom create**),
Terraform, or the OCI CLI. The retired pilot SDK helper did exactly this:

| Resource | Pilot setting |
| --- | --- |
| VCN | `ags-aegis-vcn`, `10.42.0.0/16`, DNS label `agsaegis` |
| Internet gateway + route table | `ags-aegis-ig`; route `0.0.0.0/0` -> IGW (all three subnets are public) |
| Subnet `api` (K8s API endpoint) | `10.42.0.0/24`, security list `ags-aegis-api-security` |
| Subnet `worker` (nodes) | `10.42.1.0/24`, security list `ags-aegis-worker-security` |
| Subnet `lb` (load balancers) | `10.42.2.0/24`, security list `ags-aegis-lb-security` |
| Egress (all lists) | all protocols to `0.0.0.0/0` |
| Ingress api | TCP 6443 and 12250 from `10.42.1.0/24`; TCP 6443 from operator `/32` |
| Ingress worker | all from `10.42.0.0/24`, `10.42.1.0/24`, `10.42.2.0/24`; TCP 22 from operator `/32` (32022 only for the optional relay) |
| Ingress lb | TCP 80 and 443 from `0.0.0.0/0` |
| Cluster | `BASIC_CLUSTER`, public API endpoint in `api` subnet, **Flannel overlay**, pods `10.244.0.0/16`, services `10.96.0.0/16`, service LB subnet = `lb`, dashboard off |
| Node pool | `ags-aegis-a1-node-pool`: 1 node, `VM.Standard.A1.Flex`, 2 OCPU, 12 GB, 50 GB boot, Oracle Linux 9 aarch64 OKE image matching the K8s version, node cycling off, operator SSH public key |
| Kubernetes version | `v1.36.4` observed. Pick a currently supported version |

Notes:
- Never expose the database or Ollama port 11434 publicly. Keep 6443 and 22 restricted to the operator `/32` (or use a private endpoint plus Bastion).
- The LB Service sets `security-list-management-mode: None`, so the worker list rule "all from lb subnet" is what lets LB health checks and NodePort traffic through. Keep it.
- For private worker nodes instead, add a NAT gateway and a Service gateway (OCIR, Object Storage). Nodes must reach OCIR, Object Storage, the ADB endpoint and `generativelanguage.googleapis.com:443`.

Kubeconfig for the new cluster (operator machine, new file, never overwrite the pilot's):

```powershell
oci ce cluster create-kubeconfig --cluster-id <cluster-ocid> --file C:\aegis-target\kubeconfig.yaml `
  --region <region> --token-version 2.0.0 --kube-endpoint PUBLIC_ENDPOINT --profile <operator-profile>
kubectl --kubeconfig C:\aegis-target\kubeconfig.yaml get nodes -o wide      # 1 node Ready, arm64
kubectl --kubeconfig C:\aegis-target\kubeconfig.yaml get storageclass        # oci-bv present
```

The pilot kubeconfig uses a private helper (`ags_deploy/ags_oke/ags_kubeconfig.py` together with a local `ags_runtime/ags_oke/provision-state.json`). That setup is not portable. Use the standard `oci ce` exec plugin above.

## 3. IAM: groups, users and policies

Create in the tenancy (Identity domain > Groups/Users/Policies). Adjust names:

| Principal | Purpose | Credentials |
| --- | --- | --- |
| Group `aegis-operators` (people deploying) | Provision + release | Personal API key in OCI CLI profile, personal OCIR auth token for `docker login` |
| User `aegis-app` in group `aegis-app-runtime` | Backend access to Object Storage at runtime | API key pair whose `config` + PEM go into Secret `oci-credentials` |
| User `aegis-registry` in group `aegis-registry-pull` (or reuse operator) | OKE image pulls | Auth token in Secret `ocir-pull` |

Policies (compartment `aegis`; replace names). Pilot repositories were created at the
**tenancy root**, so if you do the same, write the repos statements `in tenancy`:

```
Allow group aegis-operators to manage virtual-network-family in compartment aegis
Allow group aegis-operators to manage cluster-family in compartment aegis
Allow group aegis-operators to manage instance-family in compartment aegis
Allow group aegis-operators to manage volume-family in compartment aegis
Allow group aegis-operators to manage load-balancers in compartment aegis
Allow group aegis-operators to manage autonomous-database-family in compartment aegis
Allow group aegis-operators to manage object-family in compartment aegis
Allow group aegis-operators to manage repos in compartment aegis
Allow group aegis-operators to use cloud-shell in tenancy
Allow group aegis-app-runtime to read buckets in compartment aegis
Allow group aegis-app-runtime to manage objects in compartment aegis where target.bucket.name='<bucket>'
Allow group aegis-registry-pull to read repos in compartment aegis
```

Add the OKE service policy if Console asks for it during cluster creation. Kubernetes
RBAC: the operator who generated the kubeconfig is cluster-admin. Add other operators with a
`ClusterRoleBinding` to their OCI user OCID.

## 4. Autonomous AI Database, schema and wallet

1. Create the **Autonomous AI Database** in the compartment: Oracle AI Database **26ai**
   (native `VECTOR`/`BOOLEAN` required), workload Transaction Processing. Pilot: `ags_ora_db`
   / DB name `agsora`, 1 ECPU, 20 GB, mTLS required. Size for real use. Set a private `ADMIN` password.
2. Network access: secure access from everywhere with mTLS (pilot), or an ACL/private endpoint
   that allows both the operator machine and the OKE worker subnet/NAT egress IP.
3. Download the **instance wallet** ZIP into `C:\aegis-target\wallet\` with a new wallet
   password. Record the TNS alias you will use (pilot `agsora_low`) and the full
   `SERVICE_NAME` from `tnsnames.ora`.
4. Create the application owner and the 13 tables with the maintained release tool. This is a
   database-only run, so it needs no Docker and no Kubernetes; it can run before the cluster exists.
   Copy the template to a private file (`Copy-Item ags_deploy\templates\deployment-inputs.example.json C:\aegis-target\new-tenancy.json`)
   and set:
   - `DB_Object=Y`, `DeployFrontend=N`, `DeployBackend=N`, `DB_ReleaseFile=ags_database/release.json`
   - `WalletPath` = the **wallet `.zip` file itself** (for example `C:\aegis-target\Wallet_agsnew.zip`), not a folder
   - `DatabaseOwner` (e.g. `AGS_OWNER`), `DBAdminUser=ADMIN`
   - `ServiceAlias` (e.g. `agsnew_low`) and `ExpectedService` (the full `SERVICE_NAME` of that alias in `tnsnames.ora`)
   - `ValidationReference` (truthful test/CI evidence for the source; otherwise you are prompted)

   **Use the same alias everywhere:** `ServiceAlias` here, `AEGIS_SEED_DB_ALIAS` in section 7 and the JSON in
   section 9 must be identical. Later releases compare the saved connection against these values.
   ```powershell
   Set-Location <checkout>\ags_deploy
   .\Setup-Aegis.ps1  -Inputs C:\aegis-target\new-tenancy.json   # until AEGIS_PREREQUISITES_READY
   .\Deploy-Aegis.ps1 -Inputs C:\aegis-target\new-tenancy.json   # CONNECT, review plan, PUBLISH
   Set-Location ..                                                 # back to the repository root for sections 5-7
   ```
   `release.json` has `CreateSchemaIfMissing: Y`, so the tool creates the user (`DEFAULT TABLESPACE DATA QUOTA 256M`,
   `GRANT CREATE SESSION, CREATE TABLE`) and the 13 tables (165 columns, 49 FKs, 20 indexes,
   `aegis_knowledge_vectors` with native VECTOR). The ADMIN password and the new owner password are entered
   at private prompts only. 256 MB is small for vectors, so ask the DBA to raise the quota
   (`ALTER USER ... QUOTA ... ON DATA`) to the size you need. Setup also creates the repository `.venv`
   used below. Read-only check: `ags_database/ags_schema/verify_live_schema.sql`.
   Do not use the legacy `ags_database/deploy-oci-database.ps1` installer.

## 5. Object Storage bucket and OCIR repositories

All commands from here on run from the **repository root** in the same PowerShell window.

- **Bucket:** Standard tier, private (the pilot's `ObjectRead` public access is an observation only, not a requirement), versioning
  as you choose. Pilot bucket `mk-aegis`, prefix `aegis`. Record namespace
  (`oci os ns get`), bucket and region.
- **OCIR:** create **private** repositories `ags-aegis-web` and `ags-aegis-backend`
  (pilot also has `ags-aegis-ssh`, which only the optional relay needs). Registry host is `<region-key>.ocir.io`
  (pilot `bom.ocir.io`, namespace `bmyljaecivrj`). Login username is
  `<tenancy-namespace>/<username>` (for a non-default identity domain: `<tenancy-namespace>/<domain>/<username>`).
  The password is an auth token.
- **First images** (later releases are built by `deploy.ps1`). Use the same build args as the release tool:
  ```powershell
  $reg = '<region-key>.ocir.io/<tenancy-namespace>'; $tag = 'init-' + (git rev-parse --short HEAD)
  docker login <region-key>.ocir.io
  docker buildx build --platform linux/arm64 -t "$reg/ags-aegis-web:$tag" --push .\ags_frontend
  docker buildx build --platform linux/arm64 `
    --build-arg INSTALL_LOCAL_EMBEDDINGS=false --build-arg INSTALL_CLOUD_MODELS=true `
    --build-arg INSTALL_ORACLE=true --build-arg INSTALL_OCI=true `
    -t "$reg/ags-aegis-backend:$tag" --push .\ags_backend
  docker buildx imagetools inspect "$reg/ags-aegis-web:$tag"      # note the top-level sha256 digest
  docker buildx imagetools inspect "$reg/ags-aegis-backend:$tag"
  docker buildx imagetools inspect caddy:2.10.2-alpine             # pilot Caddy tag; use its digest
  ```
  Image references used later have the form `<region-key>.ocir.io/<ns>/ags-aegis-backend@sha256:<digest>`
  and `docker.io/library/caddy@sha256:<digest>`.
- **Keep the first backend image.** Later releases update only the `api` and `worker` images. The init container
  `verify-existing-oci-state` stays on this first digest, so exclude it from any OCIR retention/cleanup policy.

## 6. Kubernetes Secrets and runtime ConfigMap (namespace `aegis-oci`)

**Safety first.** The live pilot also uses namespace `aegis-oci`, so every kubectl command must name the new kubeconfig.
Define these once in the window and use `k` for every command:

```powershell
$kc  = 'C:\aegis-target\kubeconfig.yaml'
function k { kubectl --kubeconfig $kc -n aegis-oci @args }
kubectl --kubeconfig $kc config current-context     # must be the NEW cluster
kubectl --kubeconfig $kc get nodes                  # must show the new node(s)
$py  = (Resolve-Path .\.venv\Scripts\python.exe).Path   # created by Setup-Aegis.ps1; has cryptography
# Write private files as UTF-8 without BOM and without a trailing newline.
# Do NOT use '>' or Out-File: Windows PowerShell 5.1 writes UTF-16 plus a newline, which breaks keys and passwords.
function Save-Private([string]$Path, [string]$Value) { [IO.File]::WriteAllText($Path, $Value) }
function Read-Private([string]$Label) {
  $s = Read-Host $Label -AsSecureString
  [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
}
New-Item -ItemType Directory -Force C:\aegis-target\secrets | Out-Null
```

Then apply stage 1 (namespace and PVCs; no placeholders):
`k apply -f .agents\skills\aegis-oci-replicate\references\01-base.yaml`.

| Secret / ConfigMap | Keys | How to create |
| --- | --- | --- |
| `aegis-app` | `AEGIS_MASTER_KEY` (new Fernet key that encrypts every saved credential; **back it up offline**, because losing it makes saved DB/model secrets unreadable), `AEGIS_BOOTSTRAP_TOKEN` (random; used once to create the first administrator) | See the commands below |
| `ocir-pull` (dockerconfigjson) | `.dockerconfigjson` | See the commands below. Use a registry user whose group has `read repos` |
| `oci-credentials` | `config`, `aegis_api_key.pem` | `config` is a standard OCI config `[DEFAULT]` for user `aegis-app` (`user`, `fingerprint`, `tenancy`, `region`, `key_file=/run/oci/aegis_api_key.pem`, plus `pass_phrase` if the key has one). Mounted read-only at `/run/oci`. `k create secret generic oci-credentials --from-file=config=C:\aegis-target\oci\config --from-file=aegis_api_key.pem=C:\aegis-target\oci\aegis_api_key.pem` |
| `database-wallet` | every file of the unzipped wallet (`tnsnames.ora`, `ewallet.pem`, `cwallet.sso`, `sqlnet.ora`, ...) | `Expand-Archive C:\aegis-target\Wallet_agsnew.zip C:\aegis-target\wallet-unzipped`, then `k create secret generic database-wallet --from-file=C:\aegis-target\wallet-unzipped\`. Mounted at `/run/aegis-db/wallet` |
| ConfigMap `aegis-runtime-config` | `runtime.toml` | `k create configmap aegis-runtime-config --from-file=runtime.toml=ags_backend\ags_app\ags_config\runtime.toml` (the `oci` profile is selected by env). Operational settings live here, not in env |
| `ssh-relay` | host key + authorized_keys | **Only** for the optional laptop-Ollama relay. Skip it for the Gemini design |

```powershell
# aegis-app
Save-Private C:\aegis-target\secrets\master.key ((& $py -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())") | Out-String).Trim()
Save-Private C:\aegis-target\secrets\bootstrap.token ((& $py -c "import secrets;print(secrets.token_urlsafe(32))") | Out-String).Trim()
k create secret generic aegis-app `
  --from-file=AEGIS_MASTER_KEY=C:\aegis-target\secrets\master.key `
  --from-file=AEGIS_BOOTSTRAP_TOKEN=C:\aegis-target\secrets\bootstrap.token

# ocir-pull (token typed at a hidden prompt, never on the command line)
$ocirHost = '<region-key>.ocir.io'; $ocirUser = '<tenancy-namespace>/<username>'
$auth = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($ocirUser + ':' + (Read-Private 'OCIR auth token')))
Save-Private C:\aegis-target\secrets\ocir-config.json ('{"auths":{"' + $ocirHost + '":{"auth":"' + $auth + '"}}}')
k create secret generic ocir-pull --type=kubernetes.io/dockerconfigjson `
  --from-file=.dockerconfigjson=C:\aegis-target\secrets\ocir-config.json
```

Check that no file starts with a BOM: `Format-Hex C:\aegis-target\secrets\master.key | Select-Object -First 1` must not begin with `FF FE` or `EF BB BF`.

## 7. Load balancer, hostname, seed state, workloads

The backend init container refuses to start unless `/data` already contains
`configuration/database.json` (active OCI connection + encrypted secret),
`configuration/settings.json` (OCI storage) and `models/reranker/`. A new volume has none of
these. Do the steps in this order:

1. **Stage the reranker** on the operator machine (pinned `cross-encoder/ms-marco-MiniLM-L6-v2`,
   revision `233902d25c440f23af6f7d6e94d2946bac0bee0a`; the script verifies hashes). Only one package is needed:
   ```powershell
   & $py -m pip install huggingface-hub==1.33.0
   & $py .\ags_local_use\ags_scripts\setup-reranker.py --directory C:\aegis-target\reranker
   ```
   Expect `onnx\model.onnx`, `tokenizer.json` and `aegis-model.json` in that folder.
2. **Create the load balancer first** so its IP is known before choosing the hostname:
   ```powershell
   $ref = (Resolve-Path .agents\skills\aegis-oci-replicate\references).Path
   $out = 'C:\aegis-target\manifests'; New-Item -ItemType Directory -Force $out | Out-Null
   function Fill([string]$Name, [hashtable]$Values) {
     $t = [IO.File]::ReadAllText("$ref\$Name")
     foreach ($key in $Values.Keys) { $t = $t.Replace($key, $Values[$key]) }
     if ($t -match '__[A-Z_]+__') { throw "Unfilled placeholder in $Name : $($Matches[0])" }
     [IO.File]::WriteAllText("$out\$Name", $t)
   }
   Fill '02-public-service.yaml' @{ '__LB_SUBNET_OCID__' = '<lb-subnet-ocid>' }
   k apply --dry-run=server -f "$out\02-public-service.yaml"; k apply -f "$out\02-public-service.yaml"
   k get svc aegis-public -w        # wait for EXTERNAL-IP, then Ctrl+C
   ```
   Choose `$appHost`: `aegis.<EXTERNAL-IP>.sslip.io` (as in the pilot) or your own DNS name with an A record pointing to that IP.
   (Do not name the variable `$host`; that name is reserved in PowerShell.) Optional: to keep the same IP if the Service is ever re-created,
   reserve a public IP in OCI and set `spec.loadBalancerIP: <reserved-ip>` in `02-public-service.yaml` before applying.
3. **Apply non-secret configuration:**
   ```powershell
   $appHost = 'aegis.<EXTERNAL-IP>.sslip.io'
   Fill '03-config.yaml' @{ '__APP_HOST__' = $appHost }
   k apply --dry-run=server -f "$out\03-config.yaml"; k apply -f "$out\03-config.yaml"
   ```
4. **Seed `/data` with a one-off pod** ([references/seed-pod.yaml](references/seed-pod.yaml)). It mounts `application-state`,
   the wallet and `aegis-app`/`aegis-config`, plus a temporary Secret `aegis-seed` holding the owner and wallet passwords:
   ```powershell
   $backend = '<region-key>.ocir.io/<ns>/ags-aegis-backend@sha256:<digest>'
   Save-Private C:\aegis-target\secrets\db.pw     (Read-Private 'Database owner password')
   Save-Private C:\aegis-target\secrets\wallet.pw (Read-Private 'Wallet password')
   k create secret generic aegis-seed `
     --from-file=AEGIS_SEED_DB_PASSWORD=C:\aegis-target\secrets\db.pw `
     --from-file=AEGIS_SEED_WALLET_PASSWORD=C:\aegis-target\secrets\wallet.pw
   Fill 'seed-pod.yaml' @{ '__BACKEND_IMAGE__' = $backend }
   k apply -f "$out\seed-pod.yaml"; k wait --for=condition=Ready pod/aegis-seed --timeout=600s
   k cp .agents/skills/aegis-oci-replicate/scripts/seed_oci_state.py aegis-seed:/tmp/seed.py
   k exec aegis-seed -- env AEGIS_SEED_DB_USER=AGS_OWNER AEGIS_SEED_DB_ALIAS=<same alias as section 4> `
     AEGIS_SEED_DB_NAME=<dbname> AEGIS_SEED_REGION=<region> `
     AEGIS_SEED_BUCKET_NAMESPACE=<namespace> AEGIS_SEED_BUCKET=<bucket> python /tmp/seed.py
   Push-Location C:\aegis-target                     # relative path avoids kubectl misreading "C:" as a pod name
   k cp reranker aegis-seed:/data/models/reranker
   Pop-Location
   k exec aegis-seed -- ls -la /data/configuration /data/models/reranker /data/models/reranker/onnx
   k delete pod aegis-seed; k delete secret aegis-seed
   Remove-Item C:\aegis-target\secrets\db.pw, C:\aegis-target\secrets\wallet.pw
   ```
   [scripts/seed_oci_state.py](scripts/seed_oci_state.py) uses the app's own `database_control.save_draft()`
   to write the same encrypted format as the Settings > Database screen. It refuses to overwrite existing
   state, checks that the alias exists in the wallet, decrypts its own result, and does not connect to the database.
   The schema must already exist (section 4). The pilot instead configured these settings in a local container
   and moved `/data` to the cluster; that path was never written down.
5. **Install the workloads:**
   ```powershell
   Fill '04-workloads.yaml' @{ '__BACKEND_IMAGE__' = $backend
     '__WEB_IMAGE__'   = '<region-key>.ocir.io/<ns>/ags-aegis-web@sha256:<digest>'
     '__CADDY_IMAGE__' = 'docker.io/library/caddy@sha256:<digest>' }
   k apply --dry-run=server -f "$out\04-workloads.yaml"; k apply -f "$out\04-workloads.yaml"
   k rollout status deploy/aegis-api-worker --timeout=15m; k rollout status deploy/aegis-web --timeout=10m
   ```
   Caddy obtains a Let's Encrypt certificate for `$appHost` over ports 80/443 and keeps it on `https-state`.
   Later releases discover and preserve this URL from the `https-config` ConfigMap.
6. **Confirm:** both Deployments show `1/1 Ready`; `curl.exe -sI https://$appHost/` returns 200 with a valid certificate;
   `k logs deploy/aegis-api-worker -c api --tail=50` shows no errors. `/ready` checks the DB connection,
   the vector table and the reranker. Keep `C:\aegis-target\manifests` privately as the install record.

## 8. First application setup (in the browser)

1. Open `https://<host>`. The first run asks for setup. Create the administrator with the `AEGIS_BOOTSTRAP_TOKEN`
   (password at least 12 characters). Afterwards you may rotate or remove the token from `aegis-app`.
2. Settings > Storage: **Test** the OCI bucket (read is verified, write on first upload). Settings > Database should show OCI active.
3. Register models (Gemini endpoint `generativelanguage.googleapis.com`, own API key; the app encrypts it with the master key):
   Embedding `gemini-embedding-2`, Chat `gemini-3.5-flash-lite`, Extraction `gemini-3.5-flash-lite` (also used for OCR).
   Test each one, then map **every** dataset's defaults to them. Confirm the account supports these IDs. Fix the embedding model and
   dimensions before indexing; changing them later means reindexing. The global fallbacks in `aegis-config`
   (`MODEL_PROVIDER=ollama`, OCR URL `http://ollama:11434`) point to a relay that this design does not install,
   so an unmapped dataset or unmapped OCR will fail. That is expected; map the datasets.
4. Create users and colleagues, datasets and access assignments.
5. Acceptance (needs authorization for writes and provider calls): upload a harmless test document, index it, extract, and ask a cited chat question. Record what passed.

## 9. Ongoing releases: hand over to aegis-deploy

Copy `ags_deploy/templates/deployment-inputs.example.json` to a private file and fill in:
`Kubeconfig` (new file), `Context`, `Namespace=aegis-oci`, `Registry=<region-key>.ocir.io`,
`RegistryNamespace=<tenancy-ns>`, `Platform=linux/arm64`, `AppUrl=https://<host>`, the DB fields from
section 4 (same alias and service), `DeployFrontend`/`DeployBackend`, and `ValidationReference`.
Use **`DB_Object=N` for routine code releases.** With `Y` the tool connects as ADMIN and prompts for its password every time;
use `Y` only when `ags_database/release.json` adds tables. Then follow
[aegis-deploy](../aegis-deploy/SKILL.md): `Setup-Aegis.ps1 -Inputs ...` until `AEGIS_PREREQUISITES_READY`,
then `Deploy-Aegis.ps1 -Inputs ...` (CONNECT, review plan, PUBLISH). It updates only images and approved DB objects
and preserves everything above.

## 10. Handover inventory (fill in and keep privately, no secrets)

```
Tenancy / region / compartment OCID:
Operator group / app user / registry user:
VCN / IGW / route table / 3 subnets / 3 security lists (OCIDs):
Cluster OCID / K8s version / API endpoint / node pool / node shape & arch:
Kubeconfig path / context:
ADB OCID / DB name / version 26ai / ECPU / storage / TNS alias / full SERVICE_NAME / owner:
Wallet location (private) / wallet download date:
Bucket namespace / name / prefix / region:
OCIR host / namespace / repos / initial digests (web, backend, caddy):
LB OCID / public IP / hostname / TLS issued (date):
Secrets present: ocir-pull aegis-app oci-credentials database-wallet  ConfigMaps: aegis-config aegis-runtime-config https-config
PVCs bound: application-state https-state (backing volume OCIDs)
Reranker revision 233902d2... verified (aegis-model.json present):
Master key backup location (offline):
Models registered and mapped (IDs) / Gemini quota owner:
Acceptance tests run and results:
```

Completion checklist: nodes Ready on the expected architecture; PVCs Bound; init container passed; `/ready` is 200;
HTTPS valid; admin created; storage test OK; models tested; `Setup-Aegis.ps1 -CheckOnly -Inputs <new json>` passes CONNECT preflight.

## Optional: laptop Ollama relay (the pilot has it; the Gemini design does not need it)

The pilot adds a `model-relay` sidecar (image `ags-aegis-ssh`, Alpine sshd on 2222 that only allows a reverse
forward to 0.0.0.0:11434), Secret `ssh-relay` (`ssh_host_ed25519_key`, `authorized_keys`), Service `ollama`
(ClusterIP 11434) and NodePort Service `model-relay-ssh` (32022, `externalTrafficPolicy: Local`, open only to the
operator `/32`). The laptop runs `ags_local_use/ags_scripts/start-oke-model-relay.ps1`. Recover the image files
from git history (`ags_deploy/ags_oke/ags_ssh/`) only if this design is explicitly chosen. The laptop must stay online for every model it serves.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Init container fails: "Seed the existing OCI configuration" / "secret reference missing" / "reranker files missing" | Section 7 not completed on this PVC |
| `ImagePullBackOff` | `ocir-pull` wrong username format/token, repo in another compartment without policy, or image arch not arm64 |
| PVC `Pending` | `oci-bv` binds on first consumer; check the pod is scheduled and block volume limits |
| `/ready` fails, DB errors | Wallet Secret incomplete, wrong alias/password (re-seed with overwrite only on a fresh install), ADB ACL blocks node egress IP, schema missing |
| Storage test fails | `oci-credentials` config/key path not `/run/oci/aegis_api_key.pem`, wrong region/namespace, missing bucket policy |
| No certificate | Hostname does not resolve to LB IP, port 80 blocked, wrong host in Caddyfile |
| Saved secrets unreadable after redeploy | `AEGIS_MASTER_KEY` changed. Restore the original key |
| LB has no IP | Wrong `oci-load-balancer-subnet1`, LB limits, or missing load-balancer policy |
