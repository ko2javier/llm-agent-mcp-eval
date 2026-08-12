"""
ReAct-style agent loop against a vLLM OpenAI-compatible server with native tool calling
(--enable-auto-tool-choice --tool-call-parser <parser>).

State (message history, tool results) is managed entirely in this script — the LLM
itself has no memory between calls, each turn re-sends the full message list.

Run a single task:
    python scripts/agent.py --model QuantTrio/gemma-4-31B-it-AWQ --task "..." --tool-call-parser gemma4

Run the golden set:
    python scripts/agent.py --model QuantTrio/gemma-4-31B-it-AWQ --tasks-file dataset/agent_tasks.json \
        --output results/gemma4_31b_agent.json --gpu-hourly-rate 0.7493
"""

import argparse
import json
import re
import time

import requests

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from tools import TOOLS_SCHEMA, execute_tool

MODEL_URL = "http://localhost:8081/v1"
HTTP_TIMEOUT = 60
MAX_TURNS = 6  # hard cap on tool-call round trips, avoids infinite loops on a stuck model

# Gemma 4's chat template sometimes leaks its internal "thought" channel marker
# into the visible content instead of the parser stripping it. Strip it here.
_CHANNEL_RE = re.compile(r"<\|channel>.*?<channel\|>\s*", re.DOTALL)


def clean_answer(text: str) -> str:
    return _CHANNEL_RE.sub("", text or "").strip()

SYSTEM_PROMPT = (
    "You are a NexusPay support agent. You have tools to look up documentation, check "
    "transaction status, calculate fees, get exchange rates, and issue refunds. "
    "Use tools when you need real data — do not guess transaction details, fees, or rates. "
    "Call as many tools as needed, in sequence, before giving your final answer. "
    "When you have enough information, answer the user directly in plain text."
)


def chat(model: str, model_url: str, messages: list) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "tools": TOOLS_SCHEMA,
        "tool_choice": "auto",
        "temperature": 0.0,
        "max_tokens": 512,
    }
    resp = requests.post(f"{model_url}/chat/completions", json=payload, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def run_task(model: str, model_url: str, task: str, verbose: bool = True) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]
    tool_calls_log = []
    t0 = time.monotonic()
    total_prompt_tokens = 0
    total_completion_tokens = 0

    for turn in range(MAX_TURNS):
        body = chat(model, model_url, messages)
        usage = body.get("usage", {})
        total_prompt_tokens += usage.get("prompt_tokens", 0)
        total_completion_tokens += usage.get("completion_tokens", 0)

        choice = body["choices"][0]
        msg = choice["message"]
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            latency_s = round(time.monotonic() - t0, 3)
            answer = clean_answer(msg.get("content", ""))
            if verbose:
                print(f"  [turn {turn+1}] final answer ({latency_s:.2f}s): {answer[:100]!r}")
            return {
                "task": task,
                "final_answer": answer,
                "tool_calls": tool_calls_log,
                "turns": turn + 1,
                "latency_s": latency_s,
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "hit_max_turns": False,
            }

        messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": tool_calls})
        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}
            result = execute_tool(name, args)
            tool_calls_log.append({"name": name, "arguments": args, "result": result})
            if verbose:
                print(f"  [turn {turn+1}] tool={name} args={args} -> {result[:100]}")
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

    latency_s = round(time.monotonic() - t0, 3)
    if verbose:
        print(f"  [HIT MAX_TURNS={MAX_TURNS}]")
    return {
        "task": task,
        "final_answer": "",
        "tool_calls": tool_calls_log,
        "turns": MAX_TURNS,
        "latency_s": latency_s,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "hit_max_turns": True,
    }


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--model-url", default=MODEL_URL)
    p.add_argument("--task", help="Run a single ad-hoc task instead of a tasks file")
    p.add_argument("--tasks-file", help="JSON file: list of {id, task, expected_tools}")
    p.add_argument("--output", help="Where to save the JSON results (required with --tasks-file)")
    p.add_argument("--gpu-hourly-rate", type=float, default=0.7493)
    return p.parse_args()


def main():
    args = parse_args()

    if args.task:
        result = run_task(args.model, args.model_url, args.task)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if not args.tasks_file or not args.output:
        raise SystemExit("Need --task, or both --tasks-file and --output")

    with open(args.tasks_file, encoding="utf-8") as f:
        tasks = json.load(f)

    results = []
    for i, item in enumerate(tasks, 1):
        print(f"\n[{i}/{len(tasks)}] {item['id']}: {item['task'][:80]}")
        r = run_task(args.model, args.model_url, item["task"])
        called = [tc["name"] for tc in r["tool_calls"]]
        expected = item.get("expected_tools", [])
        r["id"] = item["id"]
        r["expected_tools"] = expected
        r["tools_called_names"] = called
        r["expected_tools_all_called"] = all(t in called for t in expected)
        r["cost_usd"] = round((r["latency_s"] / 3600) * args.gpu_hourly_rate, 8)
        results.append(r)
        print(f"  expected={expected} called={called} match={r['expected_tools_all_called']}")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    n_match = sum(r["expected_tools_all_called"] for r in results)
    n_max_turns = sum(r["hit_max_turns"] for r in results)
    print(f"\n{n_match}/{len(results)} tasks called all expected tools. "
          f"{n_max_turns}/{len(results)} hit MAX_TURNS without a final answer.")
    print(f"Results saved -> {args.output}")


if __name__ == "__main__":
    main()
