# Oracle AI Database Free integration

This configuration runs six services: Web, API, Worker, Oracle AI Database Free,
Qdrant, and Ollama. It uses the official Full image pinned to
`container-registry.oracle.com/database/free:23.26.3.0` (26ai Free). It is separate
from the existing PostgreSQL Compose file and the native SQLite workspace.

The application owner defaults to `AGS_OWNER` with twelve custom tables. Existing
AEGIS data requires [the one-time migration](../ags_database/ags_migrations/01_aegis_to_ags_owner.md).
For tables, relationships, audit fields and model category mappings, see
[the data model](../ags_database/ags_docs/DATA-MODEL.md). To query the local
database from VS Code, see [the connection guide](ORACLE-VSCODE.md) and
[example SQL](../ags_database/ags_queries/oracle-queries.sql).

## Current verification status

The latest Assistant resume and hardware checks are recorded in
[the 2026-10-10 test report](ags_testing/assistant-resume-2026-10-10.md), including
actual timings, prior timeouts and memory limitations. Keep sufficient available
RAM for CPU inference and host applications; GPU support does not remove the
container memory requirement. For OKE, see [Kubernetes preparation](KUBERNETES.md).

Scanned PDFs and visible DOCX images use local Qwen2.5-VL OCR before embedding.
See [OCR configuration, accuracy and failure handling](OCR.md). Originals,
transcriptions and extraction results remain outside Oracle; Oracle retains
application metadata and audit information.

The six application containers have been built and started on the development
computer. All 20 Oracle checks passed, including actual database login,
upload/indexing, extraction, review/export, and concurrent worker claims.
The separate real-model check also passed with Qwen3, Nomic embeddings, and Qdrant:
known invoice facts, agent confirmation/progress, JSON/schema validation,
filename-based prompt versions, retained reviews after re-extraction, cited
document chat, and logout/sign-in. Tests used a separate Oracle schema and removed
their own records; the application workspace was left empty after those initial checks.
These synthetic checks do not establish accuracy for every document or workload.

## Start on Windows

Install Docker Desktop and enable Linux containers. From the repository root:

```powershell
./local/ags_scripts/start-oracle.ps1
```

The script generates `.env.oracle` and three private password files under
`secrets/oracle`, builds the application, starts the services, and downloads
Qwen3/Nomic models. Neither Node.js nor Python is required on the host; setup
uses a short-lived Python helper container. The default app URL is
**http://localhost:3003**. First-time image/model downloads require internet.
The Oracle database, Qdrant, and Ollama ports are not published.

On Linux/macOS:

```sh
sh local/ags_scripts/start-oracle.sh
```

Oracle Free limits database processing to two CPU cores, database memory to 2 GB,
and user data to 12 GB. These are Oracle's limits, not the total application's
requirements. Oracle's registry guide requires at least 13 GB free container
storage for the Full database image, plus space for app images, models and
documents. Startup selects an accessible NVIDIA GPU automatically, or uses CPU.

## Create your colleague's Aegis login

After the containers are healthy:

```powershell
./local/ags_scripts/create-colleague.ps1 -Username colleague-name
```

Enter the password privately when prompted (12–200 characters). Give the username
and password directly to the colleague. Passwords are hashed in Oracle; the command
does not print or accept them as command-line arguments. Existing usernames are
rejected without changing their passwords. This operator command does not add a
public registration endpoint or expose database administration.

The app always opens the username/password sign-in screen, including on a new
installation. Alternatively, choose **Set up your first account** to open the
separate setup form, using the bootstrap token from your private `.env.oracle`.
The setup link is available only while the database has no accounts. Linux/macOS operators
can use `bash local/ags_scripts/create-colleague.sh`; it reads credentials privately and pipes
them directly into the API container, without storing them in a shared file.
There is no per-role permission system: these accounts use Aegis's existing
workspace behavior. Documents, conversations and templates are owned per account;
global connection/settings changes are deployment-wide. This configuration is for
trusted colleagues, not an Internet-facing multi-tenant service.

## Set up and test the application

Each account starts with its own empty document workspace. Sign in, create a
dataset, and use Model Registration/Model Mapping to configure:

| Role | Protocol | Endpoint | Model |
| --- | --- | --- | --- |
| Chat | Ollama | `http://ollama:11434` | `qwen3:4b` |
| Extraction | Ollama | `http://ollama:11434` | `qwen3:4b` |
| Embedding | Ollama | `http://ollama:11434` | `nomic-embed-text` |

For a small test dataset on the CPU configuration, start with a 300-second timeout
and these registration limits: Chat context 8,192 / output 1,024; Extraction
context 8,192 / output 2,048; Embedding input 2,048 with default output dimensions.
The downloaded Nomic model returns 768-dimensional vectors. Chat needs the larger
context for the Assistant's planning instructions and schema: a 4,096-token
registration can pass Test Connection but still reject workflow planning before
calling Ollama. Larger catalogs, prompts, or document scopes may need larger
budgets within the model's supported capacity.

For detailed resume templates, process one resume per extraction and allow a
1,200-second extraction timeout on CPU (the registration permits up to 1,800).
The detailed resume test exceeded 600 seconds on this laptop; this is a budget,
not a speed guarantee. A 4,096-token extraction limit can reject
the schema plus a single resume before inference. The output budget also covers
field evidence, not only the extracted data.

`./local/ags_scripts/start-oracle.ps1` defaults to `-Hardware Auto`: it probes GPU access
inside the pinned Ollama container image, chooses the NVIDIA override only when
that succeeds, and otherwise starts CPU without requiring GPU tooling. If GPU
startup subsequently fails in Auto, it retries the CPU configuration with the
same volumes. `-Hardware Cpu` forces CPU and skips the device probe; `-Hardware Gpu`
requires successful access and fails clearly if unavailable (`-Gpu` remains an
alias). Linux startup uses `AEGIS_HARDWARE=auto|cpu|gpu`, default `auto`.

Startup pulls the configured local models, then runs a real JSON-generation and
embedding smoke test, reporting observed GPU offload through Ollama's `/api/ps`.
Each tiny inference smoke request is limited to 180 seconds. A failing GPU smoke
in Auto restarts only Ollama in CPU mode and retries, preserving its model volume.
A host GPU listing is not proof of usable model acceleration. The selected mode
does not promise all model layers fit in VRAM or that any template finishes within
a particular time. The configured NVIDIA path follows Docker Desktop WSL 2/Linux
NVIDIA runtime requirements; other GPU vendors are not configured here.

For an already configured stack, without rerunning setup or replacing volumes:
For an already configured stack, without rerunning setup or replacing volumes:

```powershell
docker compose --project-directory . --env-file .env.oracle -f local/compose.oracle.yaml -f local/compose.gpu.yaml up -d --no-deps ollama
docker compose --project-directory . --env-file .env.oracle -f local/compose.oracle.yaml -f local/compose.gpu.yaml exec ollama ollama ps
```

Use the same two Compose files for later startup commands so Ollama keeps its
GPU reservation. Check `ollama ps` after a model request for actual GPU use.
The base configuration still supports CPU machines. This follows the official
[Docker Compose GPU guide](https://docs.docker.com/compose/how-tos/gpu-support/)
and [Ollama Docker guide](https://docs.ollama.com/docker).

Run `./local/ags_scripts/test-model-hardware.ps1` for selection/fallback regression checks.
Kubernetes uses the same containers with deployment-specific environment and
storage configuration; see [Oracle Kubernetes preparation](KUBERNETES.md).

Use no authentication for Ollama. The server explicitly approves only the
`ollama` container hostname in addition to the existing loopback endpoints.
Ollama's network port is internal and cloud model names are rejected. The
existing paid/remote adapters still require explicit configuration and consent;
the default Oracle configuration sends inference to the local Ollama container.

Upload a synthetic invoice with a known total, wait for Ready, ask a question
with source citations, upload `mani.json` as a prompt template, and verify:

- Invalid JSON and schemas show validation errors before saving.
- Templates appear by filename; repeated uploads create saved versions.
- Extraction asks for confirmation and shows actual progress.
- Extraction Review opens values and source evidence, saves edits, and exports.
- Re-extraction preserves earlier results and the original file.
- Sign out/sign in and restart containers; saved results remain available.

Mock tests verify workflows. Real Ollama tests must separately verify answer and
extraction quality against known source facts.

The native desktop's direct password-reset flow intentionally remains restricted
to SQLite and loopback requests. Oracle has no unauthenticated password reset.
The provisioning command creates users, not replacements for existing users.
A token-based browser recovery flow is separate work and is not claimed to be
implemented in this Oracle integration.

## Where your colleague runs it

**Their computer:** share a versioned source checkout/release, then have them run
the startup script. Their database credentials and data will be independent.
You can create their application login on that installation, or let them complete
first-account setup. Your machine's accounts do not automatically appear in theirs.

**Your computer on a trusted LAN:** create their account on your running instance.
In your private `.env.oracle`, set `AEGIS_BIND_ADDRESS=0.0.0.0` and
`AEGIS_PUBLIC_ORIGIN=http://YOUR-LAN-IP:3003`, recreate the web/API containers,
and give them that address. `localhost` on their computer cannot reach yours.
This does not configure the host firewall or provide TLS. Use a TLS reverse proxy
for broader/shared deployment; do not publish the Oracle listener.

## Operate without deleting data

```sh
docker compose --project-directory . --env-file .env.oracle -f local/compose.oracle.yaml ps
docker compose --project-directory . --env-file .env.oracle -f local/compose.oracle.yaml logs --tail=100 api worker
docker compose --project-directory . --env-file .env.oracle -f local/compose.oracle.yaml stop
docker compose --project-directory . --env-file .env.oracle -f local/compose.oracle.yaml start
```

Rerunning setup preserves existing credentials. Keep Oracle data and application
storage backed up together, and keep the master key/password files privately.
The PostgreSQL backup/restore scripts are not Oracle backup tools; use an Oracle
Data Pump/RMAN procedure plus a consistent application-storage backup before
considering this configuration ready for persistent shared use.
Never use `down -v` on a deployment whose saved data you want to keep.

## Developer verification

```sh
pip install -r ags_backend/requirements-dev.txt -r ags_backend/requirements-oracle.txt
PYTHONPATH=ags_backend pytest ags_backend/ags_tests/test_oracle_database.py -q
```

Run the container check using the dedicated `AEGIS_TEST` database schema:

```sh
docker compose --project-directory . --env-file .env.oracle -f local/compose.oracle.yaml --profile test run --rm --build oracle-test
```

This starts a short-lived test container in addition to the six application
services. It has its own password and schema; application records are untouched.

After the startup script has downloaded the models, verify actual local inference:

```sh
docker compose --project-directory . --env-file .env.oracle -f local/compose.oracle.yaml --profile test run --rm --build oracle-test python ags_scripts/oracle_check.py --real-models
```

This uses the dedicated test schema with real Qwen3, Nomic embeddings, and Qdrant.
It checks known synthetic invoice facts, agent confirmation/progress, prompt JSON
validation and filename versions, review/export, and retained re-extraction results.
It refuses an occupied test schema and removes only its own records/vector points.

For a developer running the test outside Docker, set `AEGIS_TEST_ORACLE_URL` privately to an
`oracle+oracledb://.../?service_name=FREEPDB1` connection for an **empty dedicated
test schema**. Keep API/workers for that test schema stopped while testing.
Do not point it at your application schema. The test exercises login, dataset
mapping, upload/indexing, chat, extraction, reviewed edits/export, and durable
job claims against real Oracle with deliberately synthetic model providers.
Only that test's owner records are removed; no tables are dropped.

## Implementation notes

`DATABASE_URL` remains supported and takes precedence. Oracle also accepts
`DATABASE_PROVIDER=oracle`, `ORACLE_HOST`, `ORACLE_PORT`, `ORACLE_SERVICE_NAME`,
`ORACLE_USER`, and `ORACLE_PASSWORD_FILE` (or an operator-provided
`ORACLE_PASSWORD`). The thin Python driver needs no Oracle Instant Client.

Oracle uses `BINARY_DOUBLE` for epoch timestamps. Empty-valued control columns
use a reversible reserved-character encoding so required strings do not become
NULL. SQLite/PostgreSQL retain their existing string representation.
Oracle's job claim selects a candidate without combining FETCH FIRST and FOR
UPDATE, then uses the existing conditional update/lease token to grant one lease.
Schema creation is serialized using the shared application-storage lock.
The dedicated `AEGIS` schema receives create-session/table/sequence privileges
and a 512 MB tablespace quota; the application never connects as SYS/SYSTEM.

Sources: [official Oracle Free container guide](https://container-registry.oracle.com/ords/ocr/ba/database/free),
[SQLAlchemy Oracle dialect](https://docs.sqlalchemy.org/en/21/dialects/oracle.html),
[Oracle Free resource limits](https://www.oracle.com/database/free/faq/).
