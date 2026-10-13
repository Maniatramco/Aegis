# Re-extract Agent

LangGraph routes an explicit rerun request once, then hands it to `ReextractAgent`. The agent validates saved document names/IDs and the selected prompt, and proposes one `prepare_workflow` action. It does not run a second tool-selection model or send the conversation archive to the model. Newly attached documents require their own upload workflow.

After confirmation, the existing FastAPI extraction API submits an idempotent new result run. Earlier results and originals are preserved. Multiple documents require an explicit merge/independent choice. If document indexes are stale, the confirmed workflow rebuilds those prerequisites before extraction.

The existing worker performs extraction and writes JSON plus immutable, checksum-verified Parquet through each result's pinned storage destination. With OCI configured, new results are stored in the configured private bucket. The workflow does not claim completion merely because an extraction job has finished.

Publication is a separate worker-owned phase. The plan persists a pending state and a recoverable lease, releasing its plan lock during file/vector I/O. Status reads do not embed or publish. Publication verifies readable Parquet, its recorded SHA-256 and revision, and the complete required native vector IDs and payload digests. Updated fields, extraction metadata, the selected prompt and source knowledge are published using the existing unified knowledge publisher.

Once those checks pass, the durable goal saves a deterministic completion receipt and Review links for the exact new extraction IDs. This finalization uses no routing, tool-selection or answer model. Conversation receipts have a deduplication key, so worker recovery does not duplicate the completion message.

Failure handling retains saved work:

- A failed extraction step can be retried with current settings. Independent retry resubmits only failed documents and retains successful results.
- A vector-publication failure exposes **Retry knowledge update**. This republishes existing artifacts without another extraction job. Generic extraction retry is blocked for publication failures.
- A crashed publication can resume after its lease expires. A live lease prevents concurrent publishers for the same plan.
- Corrupt Parquet, incomplete coverage or mismatched native vector payloads prevent completion. Earlier files remain available.

The UI uses the existing blue/white WorkflowStepper and animations. The active call reports publication while vector verification runs, and shows the acknowledged vector and Parquet counts when finished. Review opens the saved new result beside its original document.
