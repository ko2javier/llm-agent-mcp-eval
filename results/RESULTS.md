# Results — Gemma 4 31B agent loop, 15-task golden set (01 Aug 2026)

**Instance:** Vast.ai, 1× RTX 6000 Ada (48GB), $0.7493/h. vLLM 0.26.0, `--enable-auto-tool-choice --tool-call-parser gemma4` (native Gemma 4 tool-call syntax).

**Headline: 15/15 tasks completed with a correct, non-hallucinated final answer. 14/15 matched the golden set's exact expected tool sequence.**

| Metric | Value |
|---|---|
| Tasks | 15 |
| Strict tool-sequence match | 14/15 |
| Hit MAX_TURNS (6) without finishing | 0/15 |
| Mean latency | 3.92s |
| Mean turns (LLM round-trips) | 2.3 |
| Total GPU cost for all 15 tasks | $0.0122 |

## The one "mismatch" (A07) isn't really a failure

Task: *"Please refund transaction TX-7743."* Expected tool: `initiate_refund`. What the model actually did: called `check_transaction_status` first, saw `status: "failed"`, and replied explaining the transaction can't be refunded — **without ever calling `initiate_refund`**.

That's arguably better behavior than what the golden set expected: the model used available information to predict the call would fail and avoided it, rather than calling a tool it could reason would error. The strict "did it call the expected tool" metric doesn't capture that nuance — worth keeping in mind when grading agent tool-use benchmarks generally, not just here.

## Other notable behavior

- **A02, A12** both called `check_transaction_status` before `initiate_refund` even though the task didn't ask for a status check — the model checks state before acting on it by default. Good instinct for a tool that changes real (simulated) data.
- **A06, A09** called the same tool twice in one turn with different arguments (`calculate_fees` for payment vs payout; `rag_lookup` with a rephrased query) — correct behavior, not a bug, just the model splitting a compound question into separate tool calls.
- **A11, A15** both hit tools' business-rule error paths (refunding a payout, refunding an already-refunded transaction) and the model surfaced the error to the user correctly instead of pretending it succeeded.
- A chat-template artifact was found and fixed during the smoke test: Gemma 4's `<|channel>thought...<channel|>` internal marker was leaking into the visible `content` field instead of being filtered. Patched with a regex strip in `agent.py` (`clean_answer()`) — a real finding about this specific model/parser combination, not a generic vLLM issue.

## What this does and doesn't prove

Proves: native tool-calling works end-to-end against Gemma 4 31B AWQ via vLLM, the agent picks the right tool(s) for the task, chains multiple tools correctly in one turn or across turns, and handles tool-reported errors sensibly instead of hallucinating success.

Doesn't prove: model comparison (only one model was tested, by design — see README), robustness under adversarial/ambiguous phrasing, or behavior at higher `MAX_TURNS` / more complex multi-step plans than this 15-task set exercises.
