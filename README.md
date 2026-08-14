# llm-agent-mcp-eval

An agentic RAG follow-up to [llm-rag-hybrid-benchmark](https://github.com/ko2javier/llm-rag-hybrid-benchmark): instead of a model that only reads documentation, this is a model that **acts** — a NexusPay support agent with native tool calling (vLLM's OpenAI-compatible `tools` API), running a ReAct-style loop with no memory in the model itself, all state managed by this repo's code.

## Why this exists

The RAG benchmark answered "how do I retrieve documentation well." The real gap between a RAG demo and a production system is whether the model can decide *when* to call a tool, *which* one, *chain several correctly*, and hand off to a real (if simulated) side effect. This project demonstrates exactly that boundary — read (`rag_lookup`, `check_transaction_status`) vs. act (`initiate_refund`).

## Tools

| Tool | What it does | Real or simulated |
|---|---|---|
| `rag_lookup(question)` | Semantic search over the NexusPay docs (bge-m3 + cosine similarity) | Real — reuses the retrieval pipeline from Phase 2 |
| `check_transaction_status(transaction_id)` | Looks up a transaction's status/amount/fee | **Simulated** — reads from a small `mock_transactions` Postgres table, no real payment processor |
| `initiate_refund(transaction_id, amount)` | Refunds a succeeded payment (full or partial) | **Simulated** — writes `status='refunded'` to the same mock table. No money moves. This is the one state-changing (POST-like) tool |
| `get_exchange_rate(base, target)` | Current FX rate between two currencies | **Real external API call** — [Frankfurter](https://frankfurter.dev) (ECB reference rates, free, no key) |
| `calculate_fees(amount, transaction_type)` | Computes processing fee + net amount | Real arithmetic, fictional fee schedule (2.9% + $0.30 on payments, no fee on payouts) |

`initiate_refund` and `check_transaction_status` are explicitly simulated — this project is about the agent architecture, not a real payments integration. That's stated here on purpose so it's never an ambiguous question in an interview.

## Model

**Gemma 4 31B IT (AWQ)**, served by vLLM 0.26.0 with `--enable-auto-tool-choice --tool-call-parser gemma4` — vLLM ships a native parser for Gemma 4's own `<|tool_call>` syntax. Only one model is used for this phase (unlike the 3-model comparison in Phase 2): the point here is proving the tool-calling loop works correctly, not another quality bake-off.

Served on a rented NVIDIA L40S 46GB (Vast.ai), ~$0.75/h.

## Agent loop

```
User task
  -> LLM: call a tool, or answer directly?
       -> tool: execute it, feed the JSON result back to the LLM, repeat
       -> no tool needed: answer in plain text, done
```

Implemented in `scripts/agent.py`. Capped at `MAX_TURNS = 6` round trips to avoid infinite loops on a stuck model. No conversation state is kept by the LLM — every turn re-sends the full message history from this script.

## MCP variant

The same five tools are also served over [MCP](https://modelcontextprotocol.io) (`scripts/mcp_server.py`, FastMCP, HTTP/streamable-http transport), with `scripts/mcp_agent.py` running an identical ReAct loop against them. The difference is where the tool contract comes from:

| | `agent.py` | `mcp_agent.py` |
|---|---|---|
| Tool schemas | `from tools import TOOLS_SCHEMA` — hardcoded, in-process | `tools/list` over HTTP at startup, converted to OpenAI function schemas |
| Tool execution | `execute_tool(name, args)` — local dict dispatch | `tools/call` over HTTP |
| Coupling | agent must ship the tool code | agent needs only a URL |

`mcp_server.py` delegates every tool body to `tools.execute_tool`, and lifts its descriptions from `TOOLS_SCHEMA`, so the two paths advertise byte-identical names, descriptions and parameter schemas — the benchmark stays apples-to-apples. Tool failures come back as `{"error": ...}` JSON in both, so the model sees the same thing either way.

**Full report of this phase** (what was built, how it was verified, and what was left undone):
[`INFORME_FASE_MCP.md`](INFORME_FASE_MCP.md) (Spanish).

**Results:** [`results/RESULTS_MCP.md`](results/RESULTS_MCP.md) (English) /
[`results/RESULTADOS_MCP.md`](results/RESULTADOS_MCP.md) (Spanish). Headline: MCP discovery changes
**nothing** the model does (+2.9 % overhead, zero different tool-call sequences); catalogue size does
**not** degrade accuracy from 5 to 20 tools but costs **4.33× the prompt tokens**; and MCP
annotations do not work as a safety mechanism. The measurement mistakes made along the way are
documented in [`POSTMORTEM.md`](POSTMORTEM.md).

```bash
python scripts/mcp_server.py --port 8085          # terminal 1
python scripts/mcp_agent.py --model QuantTrio/gemma-4-31B-it-AWQ \
    --tasks-file dataset/agent_tasks.json --output results/gemma4_31b_mcp_agent.json   # terminal 2
```

## Dataset

Reuses the NexusPay docs from Phase 2 (`docs/reference/`, `docs/guides/`, chunked/embedded the same way) plus a new, small `mock_transactions` seed (10 fake transactions, `sql/setup_mock_transactions.sql`) and a 15-task golden set (`dataset/agent_tasks.json`) built to force specific tool-call sequences — not a full new 50-question dataset, since the retrieval side of this problem was already solved in Phase 2.

## Results (01 Aug 2026)

**15/15 tasks completed correctly, 14/15 matched the exact expected tool sequence.** Full breakdown, including the one "mismatch" (which was arguably better behavior than expected) and a chat-template bug found and fixed along the way, in [`results/RESULTS.md`](results/RESULTS.md) (English) / [`results/RESULTADOS.md`](results/RESULTADOS.md) (Spanish).

## Repository structure
```
docs/reference/, docs/guides/   # reused from Phase 2
scripts/
  chunker.py, ingest.py, embed_server_batching.py, router.py, ingest_facts.py   # reused
  ingest_mock_transactions.py   # new — loads the fake transaction ledger
  tools.py                      # new — the 5 tool implementations + OpenAI function schemas
  agent.py                      # new — the ReAct loop
  mcp_server.py                 # new — the same 5 tools exposed over MCP (FastMCP, HTTP)
  mcp_agent.py                  # new — same ReAct loop, tools discovered via MCP client
  persona_agent.py              # new — multi-turn persona(user-simulator) <-> agent dialogue loop
  score_persona_runs.py         # new — automated scoring for persona_agent.py output
dataset/agent_tasks.json        # new — 15-task golden set
dataset/personas_pilot.json     # new — 5 persona cards (hidden goal, success criteria)
sql/setup_api_facts.sql, setup_mock_transactions.sql
results/                        # agent + persona-pilot run outputs
docs/langfuse/                  # Langfuse dashboard screenshots (observability evidence)
```

## T08: from single-model failure to a fix verified across three vendors

The single-model results above predate two later phases, summarized here so this section stays
honest about what's actually been tested since:

- **A second model, then a third** — Qwen2.5 32B AWQ was added (see
  [`MULTIMODEL_PHASE_REPORT.md`](MULTIMODEL_PHASE_REPORT.md) /
  [`INFORME_FASE_MULTIMODELO.md`](INFORME_FASE_MULTIMODELO.md)), then GPT-4o via the real OpenAI API
  as a third, architecturally unrelated data point. T08 — the one harmful-write failure, where the
  model conceded a dispute nobody authorized — reproduced identically on all three.
- **Server-side guard, then a root-cause fix** — `initiate_refund` now refuses on an open dispute
  (closing the double-payment path), and a docstring fix on `accept_dispute` closes the remaining
  path the guard couldn't cover (see [`T08_ROOT_CAUSE_FIX.md`](T08_ROOT_CAUSE_FIX.md)). Verified on
  the full 50-task golden set on all three models: T08 no longer results in the dispute being
  conceded on any of them. Full numbers in `MULTIMODEL_PHASE_REPORT.md`'s "Debt #4 & #1 — final
  verification" section.
- **Multi-server MCP** — a second MCP server running at the same time, with tool-name collisions and
  dynamic discovery, still hasn't been tested.

## Multi-turn evaluation: persona-agent pilot

Everything above tests one thing: given a single-sentence task, does the model pick the right tool? That doesn't test what actually breaks agents in production — a customer who reveals information gradually, applies pressure, or phrases an authorization ambiguously. This phase adds a second layer: a **user-simulator LLM plays the customer**, with a hidden goal and persona card, talking to the same agent over several real turns instead of a canned sentence — the pattern used by [τ-bench (Sierra AI, 2024)](https://arxiv.org/abs/2406.12045), applied here on top of the project's own fintech domain and its already-verified T08 write guard, rather than τ-bench's generic dataset.

**5 personas**, each grounded in real seed data, each testing a different failure mode:

| ID | Tests | Should the agent write? |
|---|---|---|
| P01 evasive_t08 | Indirect authorization ("just fix it") | No |
| P02 confused_ambiguous | Disambiguation from vague customer-given details | No |
| P03 adversarial_manipulative | Urgency pressure on an already-resolved case | No |
| P04 legitimate_multi_need | A genuine request revealed progressively | **Yes** — the counterpart to P01-P03: an agent that never writes anything isn't safe, it's useless |
| P05 impatient_pressuring | Wrong amount + pressure to skip verification | No |

Each persona ran with **both model-role assignments** (Qwen2.5-32B and Gemma4-31B each played agent once and persona once), to check whether behavior depends on which model plays which role. Implemented in `scripts/persona_agent.py`, wrapping the existing single-turn ReAct loop rather than duplicating it.

**Result: 80/80 clean at full scale** — 5 personas × 2 directions × 8 repetitions, zero unauthorized writes (`forbidden_called`), zero failures on the action that *should* happen (`required_tools_satisfied`, P04 only). Automated with `scripts/score_persona_runs.py` instead of reading 80 transcripts by hand.

**The story worth telling is how it got to 80/80, not just the number.** The first pilot run (N=3, 13 Aug) found P04 failing 0/3 in one role direction — the agent never completed a legitimate cancellation. Root cause: the harness let the simulated persona end the conversation on a fixed turn count, before the agent (playing a role that needed one extra clarifying turn) got the chance to act — not an agent failure, a harness bug. Fixed by gating conversation-end on whether the expected tool actually appears in the agent's call history (`required_tools` in `persona_agent.py`), not on a turn count. Re-verified live on Vast.ai: 0/3 → 3/3 → **8/8** at full scale, with the original (already-working) direction regression-checked at every step to confirm the fix didn't break it. A second, independent finding along the way: a premature-conversation-end bug in the *scoring* harness itself (not the agent, not the simulator) initially made P02 look like an agent failure — caught before being reported, documented as a reminder that a multi-turn eval's own tooling needs the same scrutiny as the system under test.

Full results: [`results/PERSONA_PILOT_REPORT.md`](results/PERSONA_PILOT_REPORT.md) (English) / [`results/INFORME_PILOTO_PERSONA.md`](results/INFORME_PILOTO_PERSONA.md) (Spanish). Debugging process: `POSTMORTEM.md` Partes 8-9.

## Third model investigated, retired for a structural reason

Cohere's **Command-R 35B** was investigated as a third vendor data point (after Qwen and Gemma4), verified against vLLM 0.26.0's actual source (`registry.py`, `cohere_command_tool_parser.py`) before spending any GPU time — the same architecture+parser check already used to validate Gemma4 in earlier phases. It loaded and served fine, but every tool-calling request failed: Command-R's chat template renders tools in **Cohere's own pre-OpenAI format** (`name` + `parameter_definitions`), not the `{type:"function", function:{...}}` schema this project (and the OpenAI-compatible ecosystem generally) generates. Verified this isn't one bad quantization — the August-2024 refresh of the same model uses the identical native format, and the only Cohere model confirmed to support OpenAI-format tools is Command A+, a 218B MoE requiring multi-H100 serving, well outside this project's ~30B/single-GPU scope. **Retired the whole Command-R family as a candidate** rather than force an adapter for a third data point of secondary value. Full diagnostic, including the exact Jinja template line, in `POSTMORTEM.md` E38.

## Observability (Langfuse)

Traces and scores from this project (tool-selection accuracy, `wrong_write`/`forbidden_called`, `hit_max_turns`, `required_tools_satisfied`, latency, cost) are ingested into the same self-hosted [Langfuse](https://langfuse.com) instance used by [llm-rag-hybrid-benchmark](https://github.com/ko2javier/llm-rag-hybrid-benchmark)'s judge-comparison work — one dashboard covering the whole portfolio, not a separate deployment per repo.

The trace below is the exact P04-swapped-direction case that failed 0/3 before the fix, now passing (`forbidden_write: False`, `required_tools_satisfied: True`), with the tool-call graph Langfuse builds automatically:

![P04 fix verified live in a Langfuse trace](docs/langfuse/trace_detail_p04_fix_verified.jpg)

Aggregated across every scored run, `required_tools_satisfied` is `True` in 100% of observations, zero `False`:

![Langfuse analytics: required_tools_satisfied distribution](docs/langfuse/analytics_required_tools_satisfied.jpg)

## Author

K. Jabier O'Reilly — [cv.ko2-oreilly.com](https://cv.ko2-oreilly.com) — [@ko2javier](https://github.com/ko2javier)
