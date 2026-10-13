# Direct @Upload / @Extract shortcuts — 13 October 2026

Implemented and deployed to the existing application.

- Removed the welcome note about published knowledge and choosing a dataset.
- Typing a leading `@` in the composer offers exactly `@Upload` and `@Extract`. Click, Arrow Up/Down, Enter and Escape are supported; existing `#` document selection remains available. The popup uses the existing compact picker styling and the placeholder exposes both triggers.
- The request carries an explicit `agent_operation` enum. A leading complete, case-insensitive user command also resolves this enum server-side. Conflicting/unknown enum choices are rejected. Email addresses, quoted tokens, inline references, document names, content and archived text cannot select a direct route.
- LangGraph calls the existing Onboard & Extract Agent with the selected operation, without classification or a second planning inference. These are two explicit entry points into the existing workflow agent. The operation is recorded in routing audit and shown as Routing to Upload/Extract Agent. Normal questions retain semantic routing.
- Existing dataset/document/model/template authorization, prompt validation, confirmation and durable workflow processing remain. Extraction itself still uses its configured extraction model; composing a completed result summary may also use the answer model. Newly attached extraction files retain the required upload/index prerequisite.
- Explicit commands do not inherit unfinished calls/files from an older unconfirmed proposal.

## Verification

- Seven new backend tests passed: both directives over synchronous/streaming transport, zero routing inference, confirmation rejection, confirmed upload/index/knowledge publication, confirmed extraction with saved-result completion, foreign-document rejection and valid directive boundaries. Worker/model outputs in these automated pipeline tests use the existing isolated mock fixture; they are not real-model accuracy measurements.
- 26 existing Chat Agent/onboarding handoff checks passed. The 27 streaming/latency checks passed in the initial combined run; its three new test failures were corrected fixture/endpoint expectations, with all seven direct-command cases passing afterward.
- Seven frontend command/document-selection checks passed. TypeScript and production API/worker/web builds passed.
- Browser as Mani: fresh welcome showed no removed note. `@` opened both options. Clicking Upload and keyboard-selecting Extract produced the matching workflow forms with confirmation disabled for missing inputs. Live server readback verified explicit routing, zero model calls/empty classification attempts, exactly one requested tool and no submitted jobs. Existing uploaded documents and extractions were not changed in browser QA. The two unconfirmed QA proposals remain recoverable in saved History; the current chat was cleared afterward.
- Popup bounds at 920×668: x=26.8–456.8, y=295–493.6. At 390×720: x=20.8–377.6, y=351–549.6, document width 390. Temporary viewport settings were restored after checks.

Evidence: `results/agent-commands-2026-10-13/picker.png`, `browser-proof.json`; live readback script: `verify_agent_commands.py`.
