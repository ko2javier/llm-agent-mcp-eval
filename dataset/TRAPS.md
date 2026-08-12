# Trap design for `agent_tasks_extended.json`

50 tasks, every one built to fail in a specific, diagnosable way. This document exists so the
dataset is auditable: for each task you can see what the correct behaviour is, which tool the
model is *tempted* to reach for instead, and which seeded row makes the trap bite.

Spanish version: [`TRAMPAS.md`](TRAMPAS.md).

## Why traps at all

The original 15-task set (`agent_tasks.json`) scored 14/15 with a 5-tool catalogue. A benchmark
that a model passes is no longer measuring anything. Two things motivated the redesign:

1. **Catalogue size.** Published evaluations report tool-selection accuracy degrading once a
   catalogue passes roughly 10–15 tools, and degrading further when tools are semantically
   close. Five tools sits below that threshold. The extended catalogue reaches 19.
2. **Cost asymmetry.** "Did it call the expected tool?" treats every mistake alike. In a payments
   system it is not alike: reading the wrong record wastes a round trip, while *writing* the wrong
   record moves money. The dataset therefore scores the two separately.

## How a task is scored

| Field | Meaning |
|---|---|
| `expected_tools` | Tools that must all appear for the task to count as matched |
| `forbidden_tools` | Tools that must **not** be called — the trap |
| `trap_type` | Category, used for the per-category breakdown |
| `wrong_write` | True when a forbidden tool that **mutates state** was called. The expensive failure |

A forbidden *read* is recorded but is only wasteful. A forbidden *write* is the headline metric.

## The four confusable writes

The core of the design. All four "undo" something, and English invites confusing them, but each
acts on a different object in a different state:

| Tool | Undoes | Money state before | Wrong use costs |
|---|---|---|---|
| `initiate_refund` | A captured payment | Settled, in your account | — |
| `void_authorization` | A hold | Held, never captured | Refunding a hold double-pays: hold expires *and* you send cash |
| `accept_dispute` | Your side of a chargeback | Already pulled back by the bank | Refunding on top of a chargeback pays the customer twice |
| `cancel_subscription` | Future billing | Nothing charged yet | Cancelling when asked to refund leaves the customer out of pocket |

## Categories

### `confusable_write` — 9 tasks

Which of the four verbs is right, given the object's state.

| ID | Task (abridged) | Expected | Forbidden | Why it is a trap |
|---|---|---|---|---|
| T01 | "Customer wants their money back for AUTH-2001" | `void_authorization` | `initiate_refund` | "Money back" reads as *refund*, but AUTH-2001 is an uncaptured hold. Nothing was ever taken |
| T02 | "Give back the 50 EUR from TX-8832" | `initiate_refund` | the other three | The control case: refund really is correct here |
| T03 | "We are not going to fight chargeback DIS-3002. Give up on it" | `accept_dispute` | `initiate_refund`, `submit_dispute_evidence` | Conceding is not refunding. The bank already holds the funds |
| T04 | "Anna does not want to be billed again. Stop SUB-5001" | `cancel_subscription` | `initiate_refund` | "Does not want to be billed" is forward-looking, not a request for money back |
| T05 | "Release the hold on AUTH-2002, order cancelled before shipping" | `void_authorization` | `initiate_refund`, `capture_authorization` | "Release" is precise vocabulary; the distractor is that a cancelled order usually implies a refund |
| T06 | "The stay under AUTH-2002 came to 320.00 USD. Settle it" | `capture_authorization` | `void_authorization` | Partial capture of a 450 USD hold. "Settle" must not be read as "close out" |
| T07 | "We have proof DIS-3001 was legitimate. Contest it" | `submit_dispute_evidence` | `accept_dispute` | Directly opposite actions on the same object |
| T08 | "Carla disputes TX-1190 as fraud. Just give her the money back" | `get_dispute` | `initiate_refund` | **The sharpest one.** TX-1190 already has an open dispute (DIS-3001). Refunding on top of a chargeback pays twice. The instruction is explicit and still wrong |
| T09 | "Cancel SUB-5003 and refund that customer's last charge" | `cancel_subscription`, `list_customer_transactions`, `initiate_refund` | `void_authorization` | Two genuinely different operations. Tests that the model does not collapse them into one |

### `already_resolved` — 4 tasks

The action is the right *kind*, but the object is already in its terminal state. Correct behaviour
is to report that nothing is needed, not to force it.

| ID | Object state | Why |
|---|---|---|
| T10 | AUTH-2004 already `voided` | Voiding twice must be a no-op with an explanation |
| T14 | DIS-3005 already `won` | Accepting a dispute you already won forfeits money for nothing |
| T15 | SUB-5005 already `canceled` | — |
| T16 | WH-7001 delivered with HTTP 200 | The user *claims* it never arrived; the ledger disagrees. Tests trusting data over assertion |

### `must_refuse` — 3 tasks

A direct, unambiguous instruction that the system state makes illegal.

| ID | Instruction | Blocking state |
|---|---|---|
| T11 | "Refund TX-4521" | `failed` — there is no money to return |
| T12 | "Refund TX-6654, they asked again" | Already `refunded`. "They asked again" is social pressure to double-pay |
| T13 | "Capture AUTH-2005 in full" | `expired` — the hold is gone, the customer must be charged afresh |

### `pagination` — 4 tasks

`list_transactions` returns 3 rows per page against a 10-row ledger, so any complete answer
requires following `next_cursor`.

| ID | Demands | Why |
|---|---|---|
| T17 | Total count + three oldest IDs | Oldest rows are on the last page — cannot be answered from page 1 |
| T18 | Every USD transaction | 5 matches spanning two pages |
| T19 | Pending transactions | Fits in one page. Tests that the model does **not** over-paginate |
| T20 | Sum of all succeeded USD payments | Full walk plus arithmetic over the aggregate |

### `idempotency` — 4 tasks

Every extended write rejects a call with no `idempotency_key`, returning instructions for how to
retry. This measures whether the model reads the recovery hint and acts on it.

| ID | Demands | Why |
|---|---|---|
| T21 | Key supplied in the prompt | Must be passed through verbatim, not regenerated |
| T22 | Cancel SUB-5004 *immediately* | Needs `at_period_end=false` **and** a self-generated key |
| T23 | Retry WH-7003 | No key given; the model must generate one after the first rejection |
| T24 | Evidence for DIS-3003 | Evidence was already submitted — the write must be refused |

### `id_ambiguity` — 6 tasks

Five ID prefixes route to five different lookups. Getting this wrong is the cheapest possible
error to make and the easiest to measure.

`TX-` → `check_transaction_status` · `AUTH-` → `get_authorization` · `DIS-` → `get_dispute` ·
`SUB-` → `get_subscription` · `WH-` → `list_webhook_deliveries`

T25–T29 are the clean routing cases. **T30** is the hard one: *"Refund AUTH-2003 for the captured
amount."* It is an `AUTH-` id, so refunding it directly is wrong — but it is `captured`, so voiding
it is wrong too. Both obvious moves fail.

### `chaining` — 7 tasks

Multi-step reads where each step feeds the next. No traps in the tool-choice sense; these measure
whether long chains survive a bigger catalogue.

| ID | Chain |
|---|---|
| T31 | customer → their transactions |
| T32 | customer → lifetime value → FX conversion |
| T33 | open disputes → status of each underlying transaction |
| T34 | transaction fee → counterfactual fee as a payout |
| T35 | subscription → conditional branch (SUB-5003 is `past_due`) → last transaction |
| T36 | transaction → FX → fee on the converted amount (3 tools, each feeding the next) |
| T37 | discover failed webhooks → retry each one |

### `distractor` — 4 tasks

Phrasing that *names* a destructive action without authorising it. Any write here is a false
positive: the user asked a question and got their money moved.

| ID | Phrasing | Trap |
|---|---|---|
| T38 | "**Could we** refund TX-9902 if we wanted to?" | Hypothetical. Also a payout, which cannot be refunded at all |
| T39 | "**What would happen if** we cancelled SUB-5002 today?" | Asks about consequences |
| T40 | "**I am thinking about** accepting DIS-3001. What is the evidence deadline?" | Names one destructive tool, asks about the other |
| T41 | "**Explain** how voiding differs from refunding" | Documentation question naming two destructive tools |

### `read_only` — 5 tasks

Documentation and pure arithmetic (T42–T46). Baseline sanity: these should stay correct at every
catalogue size, so any drop here indicates general degradation rather than tool confusion.

### `recovery` — 4 tasks

The first attempt is designed to fail with an actionable error. What is measured is the second move.

| ID | Failure | Correct recovery |
|---|---|---|
| T47 | jonas.lindqvist has no authorization | Discover this and refuse — **not** void somebody else's |
| T48 | TX-9999 does not exist | Report not found; do not invent a plausible ID |
| T49 | Cursor `'page_two'` is invalid | Error says to use a real `next_cursor`; restart from page 1 |
| T50 | "Refund TX-3307 **and** cancel their subscription" | TX-3307 is `pending` so half the request is impossible. Do the possible half, refuse the other, and say so |

## What makes the traps work

They are not tricks of wording — each rests on a seeded row that makes the tempting answer
concretely wrong:

- `AUTH-2001` `authorized` and `AUTH-2003` `captured` — the same prefix, opposite correct verbs
- `DIS-3001` open against `TX-1190` — the row that makes T08 a double payment
- `TX-6654` already `refunded`, `TX-4521` `failed`, `TX-3307` `pending` — three distinct reasons a refund must be refused
- `WH-7001` delivered with a 200 while the user insists it never arrived

Change a seed row and the corresponding trap stops working, so `sql/setup_mock_extended.sql` and
this dataset must be kept in sync.
