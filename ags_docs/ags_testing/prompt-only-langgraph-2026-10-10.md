# Prompt-only upload loop correction — 2026-10-10

An actual saved application trace showed `can you upload it` after a JSON prompt
save receipt. The graph called `prepare_workflow(upload)` seven times, although
each authoritative tool response said the prompt was already validated/saved.
It then returned the tool-step-limit message. The template save itself succeeded.

The graph now acknowledges a verified prompt save when semantic intent resolves
to prompt information or prompt-only upload. If the model still calls the upload
tool, the tool returns a typed `prompt_saved` completed event and the graph ends
with the server's exact filename/version acknowledgement. The response is not
delegated back to a model that can repeat the completed action. This change uses
verified application state and structured intent/events, not extra phrase rules.
Other prompt questions and prompt-plus-document extraction continue through the
normal graph. Uploading documents and running extraction still need confirmation.

## Verification

- 19 graph tests passed, including prompt-only action classification, fallback
  tool calls that previously looped, and prompt-plus-document extraction.
- API/worker rebuilt and restarted in the current Docker stack.
- Real Chromium browser on the running app: attach valid JSON, choose Prompt
  template, confirm the preview, send **can you upload it**.
- Acknowledged `prompt-only-upload.json`, version 1, in the QA dataset; two model
  decisions, no workflow calls, no tool-limit response. Request took 13.23 seconds.
- Composer cleared; submitted filename appeared in the chat; the template was
  found in the separate Prompt templates screen.

[Browser report](../../ags_runtime/ags_archive/ags_cleanup_2026_10_14/ags_docs/ags_testing/prompt-only-langgraph-browser.json) ·
[Browser screenshot](../../ags_runtime/ags_archive/ags_cleanup_2026_10_14/ags_docs/ags_testing/prompt-only-langgraph-confirmed.png)

This used a fictional QA template. Existing saved user templates/results were
retained. The user's attached export was not accessible through the file surface;
diagnosis used the actual application's stored conversation/tool trace instead.
