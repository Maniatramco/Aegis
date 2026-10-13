# Local development and testing

Laptop Compose configurations, environment templates and launch helpers live here.
Run the commands below from the repository root. `--project-directory .` keeps
build contexts, secrets, wallet mounts and storage paths anchored to that root.
Existing private `.env`, `.env.oracle`, `secrets/`, data and model directories
remain in their existing locations; they are not committed.

```text
local/
  compose*.yaml                 Local runtime and isolated CI test configurations
  .env.example                 Local PostgreSQL configuration template
  .env.oracle.example          Local Oracle/Ollama configuration template
  Aegis-local.code-workspace    VS Code workspace, opening the repository root
  ags_scripts/                 Laptop setup, launch and hardware helpers
```

Default Docker development environment:

```sh
./local/ags_scripts/setup.sh
docker compose --project-directory . --env-file .env -f local/compose.yaml up --build -d
```

Windows Oracle/Ollama launcher:

```powershell
./local/ags_scripts/start-oracle.ps1
```

Existing laptop configuration with OCI credentials and local GPU inference:

```sh
docker compose --project-directory . --env-file .env.oracle -f local/compose.oracle.yaml -f local/compose.gpu.yaml -f local/compose.oracle-client.yaml -f local/compose.agents-low-memory.yaml -f local/compose.oci-storage.yaml ps
```

Use the same arguments for subsequent Docker operations. The Oracle client
overlay is optional and provides only loopback access to the local Oracle service.
The local database services are not the OKE application deployment.

Native development uses `ags_scripts/windows-dev.py` or `ags_scripts/local-smoke.sh`
inside this folder. Open `Aegis-local.code-workspace` for the Windows launch tasks.
Shared automated tests stay in `../ags_backend/ags_tests` and
`../ags_frontend/ags_tests`; manual real-model benchmarks stay in
`../ags_scripts/ags_qa`. CI uses `compose.yaml` plus `compose.test.yaml` from this
folder with disposable mock data. Never apply the test overlay to a real workspace.
