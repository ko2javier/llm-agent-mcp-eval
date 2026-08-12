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
dataset/agent_tasks.json        # new — 15-task golden set
sql/setup_api_facts.sql, setup_mock_transactions.sql
results/                        # agent run outputs
```

## Future work

- **A second model** — dropped for budget reasons this phase. Without it there's no way to tell whether T08 (the one harmful-write failure) and the flat accuracy-vs-catalogue-size curve are properties of Gemma 4 specifically or of the tool design itself.
- **Server-side guard for T08** — `initiate_refund` should refuse when the transaction has an open dispute, the same way it already refuses on a `failed` payment. `results/RESULTADOS_MCP.md` / [`POSTMORTEM.md`](POSTMORTEM.md) (H2) show that warning about it in the prompt (via MCP annotations) buys +26% tokens and zero safety — the fix has to live in the tool, not the description.
- **Multi-server MCP** — a second MCP server running at the same time, with tool-name collisions and dynamic discovery, hasn't been tested.

## Author

K. Jabier O'Reilly — [cv.ko2-oreilly.com](https://cv.ko2-oreilly.com) — [@ko2javier](https://github.com/ko2javier)
