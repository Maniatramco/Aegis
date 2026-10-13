# Compact Home and Agent setup latency — 13 October 2026

## Implemented

- Home removes the descriptive sentence, duplicate dataset heading/count, persistent search row, outer panel padding and redundant footer note. Search is an accessible icon next to Refresh. It opens a focused search popup; Escape, Close and outside clicks reset filtering. Existing dataset cards/actions remain available.
- Execution snapshots batch mapped-model records in one SQL read, memoize configuration/profile authorization reads only for the current snapshot, and discard that state afterward. New requests still validate current ownership, mappings, capabilities, activity, model/profile versions and installed embedding digest. No answer knowledge or authentication decision is cached across requests.
- Agent plan preparation no longer builds a redundant global model snapshot before a dataset snapshot. The deferred reply validates configuration inside the accepted SSE stream and reports Checking agent configuration as the first real timed stage. A configuration failure is persisted and cannot trigger inference or duplicate replay. Saved conversation and workflow timings retain this stage.
- Local Ollama now defaults to a 30-minute keep-alive instead of five minutes. The one-loaded-model/one-parallel-request memory constraints remain. Explicit operator/model overrides still take precedence. Qwen was warmed using an empty load request; no document/history was supplied. Runtime confirmed qwen3:4b, 8192 allocated context, 3.9 GB, 100% GPU, about 30 minutes remaining. The registered model context limit was not changed.

## Live evidence

The same read-only OCI setup probe before/after showed dataset configuration resolution falling from 4.736 seconds/31 SQL round trips to 1.418 seconds/13 round trips (about 70% lower measured setup time). Published knowledge setup was 2.279 seconds before and 1.572 seconds afterward. These are single setup probes, not overall throughput or accuracy percentages.

Browser tests as Mani used the fictional Resume Agent Verification dataset and real Qwen/OCI vectors. The first document-count question encountered a cold model load: its classifier stage took 37.306 seconds and its reported workflow steps totaled 44.004 seconds. The identical warm question returned the same correct one-document count with a citation in 5.929 seconds of reported steps. After applying the 30-minute setting and warming Qwen, a named saved-result summary returned Maya Rao, B.Tech, eight years and the eight saved skills with a citation and Review action in 11.728 seconds of reported steps. Configuration took 1.7–1.9 seconds in these browser requests. Timing badges sum reported steps and exclude plan submission/network and unreported checkpoint gaps; these values are not full click-to-finish measurements. Cold startup after service restart and eviction by embedding/OCR remain possible.

Home browser checks verified name filtering, no-match state, Clear search, Escape and both desktop/narrow/phone sizing. At 390×720, the final popup bounds were x=34.4–374.4, and document width remained 390. Temporary viewport overrides were reset.

## Validation

- 95 model-routing, dataset-access, Chat Agent and graph regressions passed.
- 27 streaming/latency regressions passed, including changed/disabled model rejection before inference and persistence of the real setup stage.
- The two relevant stream cases passed again after the final plan-lookup reuse edit.
- TypeScript, production API/worker/web builds and git diff whitespace checks passed.
- Existing dataset documents/results were preserved. Only ordinary QA conversation turns were added.

Probe: `profile_agent_setup.py`. Browser readback: `verify_agent_latency.py`. Evidence under `results/home-compact-2026-10-13`: `agent-setup-before.json`, `agent-setup-after.json`, `browser-agent-proof.json`, `home.png`, `agent-summary.png`.
