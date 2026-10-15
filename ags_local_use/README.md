# Local development and testing

Laptop Compose configurations, environment templates, launch helpers and optional
testing tools live here. OCI installation and release tools stay in `../ags_deploy/`.
Run the commands below from the repository root. `--project-directory .` keeps
build contexts, secrets, wallet mounts and storage paths anchored to that root.
Existing private `.env`, `.env.oracle`, `secrets/`, data and model directories
remain in their existing locations; they are not committed.

```text
ags_local_use/
  compose*.yaml                 Local runtime and isolated CI test configurations
  .env.example                 Local PostgreSQL configuration template
  .env.oracle.example          Local Oracle/Ollama configuration template
  Aegis-local.code-workspace    VS Code workspace, opening the repository root
  ags_scripts/                 Local setup, launch, checks, backup and recovery helpers
  ags_docker/                  Oracle test and browser QA container support
  ags_kubernetes/              Alternative self-hosted Kubernetes CPU/GPU manifests
  ags_qa/                      Manual checks, benchmarks, relay smoke and fictional fixtures
```

Default Docker development environment:

```sh
./ags_local_use/ags_scripts/setup.sh
docker compose --project-directory . --env-file .env -f ags_local_use/compose.yaml up --build -d
```

Windows Oracle/Ollama launcher:

```powershell
./ags_local_use/ags_scripts/start-oracle.ps1
```

Existing laptop configuration with OCI credentials and local GPU inference:

```sh
docker compose --project-directory . --env-file .env.oracle -f ags_local_use/compose.oracle.yaml -f ags_local_use/compose.gpu.yaml -f ags_local_use/compose.oracle-client.yaml -f ags_local_use/compose.agents-low-memory.yaml -f ags_local_use/compose.oci-storage.yaml ps
```

Use the same arguments for subsequent Docker operations. The Oracle client
overlay is optional and provides only loopback access to the local Oracle service.
The local database services are not the OKE application deployment.

Native development uses `ags_scripts/windows-dev.py` or `ags_scripts/local-smoke.sh`
inside this folder. Open `Aegis-local.code-workspace` for the Windows launch tasks.
Shared automated tests stay in `../ags_backend/ags_tests` and
`../ags_frontend/ags_tests`; manual real-model benchmarks stay in
`ags_qa/`. CI uses `compose.yaml` plus `compose.test.yaml` from this
folder with disposable mock data. Never apply the test overlay to a real workspace.

The optional `ags_kubernetes/` configuration uses Oracle Free, Qdrant and Ollama.
Render it with `./ags_local_use/ags_scripts/render-kubernetes.ps1 -Hardware Cpu`
from the repository root. It differs from the live OCI Autonomous Database
installation. The renderer writes manifests without applying them.

Manual tools in `ags_qa/` can contact models, OCI or an application and some write
test records. Read their existing README and select an authorized test workspace
before running them. Moving these files does not execute them.
