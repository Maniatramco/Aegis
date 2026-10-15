# Aegis runtime settings

Edit **`ags_backend/ags_app/ags_config/runtime.toml`**. This is the single source for operational values, comments, units, ranges, and local/OCI profiles.

The file covers chat context/output/evidence budgets, retrieval/chunking, extraction context and compact quotes, model-registration defaults, upload size, OCR, reranker execution, and worker/goal retry and lease settings. It contains no API keys, passwords, model credentials, database connection strings or endpoint allowlists. Those stay in the existing credential/configuration systems.

## See the values

From the repository root, using the backend Python environment:

```powershell
$env:PYTHONPATH = 'ags_backend'
python -m ags_app.runtime_config --profile oci
```

This validates the complete configuration and prints the selected file, profile, effective values and any explicit environment overrides. Administrators can also read `GET /api/runtime-config` after signing in. No credential values are returned.

## Apply to the existing OCI deployment

```powershell
python ags_deploy/ags_oke/ags_runtime_config.py --profile oci
python ags_deploy/ags_oke/ags_runtime_config.py --profile oci --apply
```

The first command validates without changing the cluster. The second updates the `aegis-runtime-config` ConfigMap, removes duplicate managed settings from the old `aegis-config`, and changes a checksum on the existing API/worker pod template to reload both processes. No image rebuild is needed for later **value changes**. Wait for deployment `aegis-api-worker` to become ready before testing. Finish active processing before applying an operational change. Infrastructure settings, mounted secrets, model mappings, originals and results are retained.

`AEGIS_CONFIG_FILE` selects an alternative file and `AEGIS_CONFIG_PROFILE` selects `oci`, `local`, or `default`. Existing environment overrides still work for compatibility and are listed by the inspection command. Remove a listed override if you want its file value to take effect. The OCI apply command handles that migration for all centrally managed keys.

For local Docker, the compose files mount the same TOML file read-only; restart API and worker after editing it. The Oracle compose file selects `local`; generic compose uses `default`.

## Registered models and saved jobs

Saved model registrations remain authoritative for model-specific context, output, timeout and provider parameters. The file's `[models]` section supplies server defaults and the Model Registration form defaults; it does not rewrite existing registrations. Continue editing a model through Model Registration, then Test Connection and Save.

Chat uses the smaller of its application limit and the selected registration's limit. A 1,000,000-byte evidence cap does not enlarge a model's context window. Access checks, hybrid retrieval, reranking, full-evidence guards and citation/schema validation remain active. Accepted jobs keep their pinned model/profile settings; changes apply to new runs. Operational worker settings reload on restart.

Do not edit a generated Kubernetes JSON manifest or the retired two-key chat-budget patch. Change the TOML file and run the apply command above.
