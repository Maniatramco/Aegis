# Aegis Assistant: expanded conversation and live answers

Verified 2026-10-11 against real Qwen3:4b/Ollama, the Docker frontend/API, and the isolated AEGIS_TEST Oracle schema. Fictional QA documents and accounts were used.

## Result

The Assistant fills the available viewport. A shorter top bar and page heading, smaller outside margins, and a wider message column provide more space while retaining 16px chat text. The composer stays visible; the conversation scrolls inside its panel. Submitted attachment cards remain with their question. Reading an earlier response disables automatic following; Latest message resumes it.

The frontend opts into deferred LangGraph replies. Planning accepts and saves the request before model execution. The reply endpoint sends actual decoded answer tokens as the model produces them, rather than replaying a finished answer. Qwen's control JSON, tool arguments and private reasoning are withheld. Final messages retain verified source metadata and existing Review actions. Proposed uploads/extractions remain pending until confirmation. Deterministic workflow receipts are returned when their result is known, without artificial typing.

Stop cancels the response, preserves the partial text in the saved plan and cleans up unfinished checkpoints. A failed response offers Retry request; attached bytes are retained for retry in the same browser session. After a reload, unavailable local attachment bytes must be selected again.

## Measured layout

| Viewport | Previous thread height | Updated thread height | Increase |
| --- | ---: | ---: | ---: |
| 938 × 668 | 305px | 380px | 25% |
| 1280 × 900 | 537px | 612px | 14% |
| 390 × 844 | 452px | 562px | 24% |
| 938 × 500 | 137px | 212px | 55% |

All four sizes had no outer vertical or horizontal overflow and a visible composer. The message textarea remained 16px. The readable desktop message width increased from 760px to up to 960px.

## Validation

- Backend regression: **661 passed, 4 skipped**, Linux container, 93.40 seconds. Skips remain environment-specific existing checks.
- Frontend unit checks: **107 passed**. Included deferred workflow attachment binding, scrolling behavior, and retry with the original bytes.
- Production Docker API, worker and frontend images built; Next compilation/type checking passed.
- Actual-model browser checks: progressive rendering, scrolling without jumping, Latest message, Stop with saved aborted text and no error alert, successful next turn, completed history after refresh, original-document citations, and pending upload confirmation all passed.
- Final frontend browser check: desktop/mobile/short-window layout and a controlled provider transport failure followed by retry with the retained file passed. The failure was deliberately injected; other model checks used actual Ollama inference.
- Browser JavaScript errors: none in these runs.

## Observed response timing

The final full-model run returned SSE headers in **1.12 seconds**, its first answer token in **31.83 seconds**, and its completed general answer in **38.76 seconds**. It emitted **298 answer delta events** and produced **284 visible progressive text updates**. The first, colder run took 164.58 seconds to first text and 171.24 seconds to completion. These are observations on this laptop while local runtimes were present, not speed guarantees.

A warm follow-up and history refresh passed in 6.43 seconds. The document citation check took 101.94 seconds (93.97 seconds to first text, 100.94 seconds to streamed completion); the upload proposal check took 6.52 seconds. Streaming exposes generated text sooner but does not eliminate classification, retrieval, prompt processing or model loading time. Ollama logs showed slow model loading/GPU discovery while the local runtimes were active. The isolated QA model was unloaded after testing to free its GPU allocation.

## Deployment and scope

Updated the existing Docker app at http://localhost:3003 using the same Oracle, file storage, model registrations and runtime configuration. Only API/worker/web containers were replaced; no database reset or model deletion was performed. Oracle jobs were idle before the update. After replacement, the frontend and auth status returned HTTP 200, API database/search readiness returned HTTP 200, and the running API/worker/web image IDs matched the latest built images. The selected source files and this report were synchronized to Aegis-finalized. No Git commit or push was made for this change.

These checks establish the requested chat behavior and relevant regressions. They do not establish factual correctness for every generated general-knowledge answer, validate every cloud model protocol against a live service, or constitute an Oracle Kubernetes deployment test.

Evidence: [model browser report](results/assistant-stream-2026-10-11/assistant-stream.json), [final layout/failure UI report](results/assistant-stream-2026-10-11/assistant-ui.json), [first model run](results/assistant-stream-2026-10-11/assistant-first-run.json), [backend log](results/assistant-stream-2026-10-11/backend-tests.log), [frontend log](results/assistant-stream-2026-10-11/frontend-tests.log).
