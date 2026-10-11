# Aegis workflow display standard

Approved by the user on 11 October 2026; updated at their request to blue/white with agent animation. This is the fixed visual standard for all Aegis workflow steppers.

Layout reference: [approved design](design/workflow-stepper-reference.png).
Implementation: `frontend/app/workflow-stepper.tsx` and `frontend/app/horizontal-workflow-stepper.css`.

Use `WorkflowStepper` for prompt saving, assistant tool execution, document upload/indexing, extraction, re-extraction, review and background job progress. Do not introduce separate workflow marker or connector implementations.

- Compact horizontal connected markers on a pale blue background (#f6f9fe), following the user's [latest data journey reference](design/aegis-data-journey-reference.html).
- Completed: blue (#2563eb) marker and white check. Connections between completed stages are solid blue (#2a62b4). A brief check appearance animation marks completion.
- Active: pale blue marker with a library icon and dark navy (#0b316f / #123c8c) rotating ring. Only the incoming connection from a completed stage has flowing particles. Future connectors remain solid and non-animated. Knowledge → AI Chat cannot animate until Knowledge completes and AI Chat is actually active. Stop animation on completion/failure; honor prefers-reduced-motion.
- Pending: white marker, grey outline/icon or dot, and grey connector. Failures use the accessible red attention state.
- Primary label is the actual workflow step name, never a generic “Step 1”. Secondary label describes the actual state; batch counts may appear below it.
- State comes from validated prompt phases, the server plan or job stages. Do not simulate completion, invent percentages or replace a saved receipt with a save failure when only the subsequent request failed.
- Compact product sizing: 38px markers (32px on narrow or short screens), 2px connectors, 88px minimum tracks (78px on narrow/short screens), and maximum width 665px. Real names may wrap. Longer workflows scroll only inside the stepper and bring the active stage into view. Never overflow the page.
- Expose an ordered list, text status, aria-current="step" on active steps, keyboard scrolling and a visible focus ring. Retain failure details, retries, confirmations and real progress counts around the stepper.

Current consumers: AgentPromptProgress, BatchProgress, JobProgress (all job kinds), and AgentV2 assistant tool plans. Tool cards retain their controls beneath the standard stepper.

Answering uses `AgentAnswerWorkflow`, collapsed by default beneath the reply. Its blue/white summary shows the actual active operation, an animated AgentLogo and that operation's elapsed time. Expand Details to show the shared horizontal WorkflowStepper and time spent per operation. Completed, stopped and failed replies retain their timings and stop animating.

Answer phases come from server progress events around actual workspace reads, classification, tools, response generation and saving. Only operations that ran appear. Client submission/connection phases describe the real request handoff and are replaced by server progress when received. Do not expose model reasoning, tool arguments or invented future steps. Persist final timings with the reply so reopening the conversation retains them.

Change this standard only following an explicit user design request. Use the shared component for future workflows and verify desktop/mobile layout and real processing states after changes.

Document processing groups real transitions into Document (upload and reading/OCR), Knowledge (indexing), and AI Chat (server readiness). Keep detailed operation/error text beneath the compact journey; readiness requires confirmed completion. Extraction and answer workflows retain their actual phases using the same component.

Restart workflow is available for a failed confirmed agent run. It rereads all retained originals, rebuilds knowledge, and automatically reruns each requested extraction in order. Earlier results and parsed versions are retained. Restart uses current approved settings, prevents concurrent or uncertain duplicate submissions, and retains prior attempt records. A failed document workflow also restarts reading and indexing from its retained original. Scoped retry remains available as an explicitly named alternative.
