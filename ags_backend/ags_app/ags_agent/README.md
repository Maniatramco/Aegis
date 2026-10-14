# Aegis Agent

This package owns Agent orchestration, semantic routing, confirmed workflows,
grounded answers, citations, context budgets, streaming and token accounting.

- `agent_graph.py`: the conversational graph and saved reply.
- `agent_workspace.py`, `agent_goals.py`: durable plan and goal lifecycle.
- `agent_tools.py`: authorized tool contracts and execution.
- `chat_agent.py`, `chat_retrieval.py`, `chat_policy.py`, `chat_knowledge.py`:
  scoped hybrid retrieval, reranking, evidence and answer validation.
- `agent_model.py`, `agent_stream.py`, `agent_context.py`: Agent tool-call
  serialization, incremental answers and context packing.
- `token_usage.py`: isolated provider-reported usage for one answer turn.
- `onboard_extract_agent.py`, `extractor_agent.py`, `reextract_agent.py`:
  the existing processing-agent contracts.

Model connection implementations live in the sibling `ags_models` package.
Legacy `ags_app.agent_*` and chat imports remain aliases to these modules;
there is only one implementation and one set of module state.

Keep the root `AGENTS.md` workflow requirement: access and dataset scope,
hybrid retrieval, reranking, generation, then answer/citation validation.
Do not alter processing agents to implement a chat-only feature.
