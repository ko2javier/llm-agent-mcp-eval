"""
Multi-turn persona-vs-agent pilot.

Every prior evaluation in this repo (agent.py, mcp_agent.py) hands the agent one canned task
string and scores a single final answer. This script replaces that single string with a second
LLM playing a customer with a hidden goal, talking to the agent over several turns — the same
shape as tau-bench's user-simulator pattern. The point of THIS script, today, is to validate that
the turn-taking / termination / logging mechanics work at all, with 2-3 personas, before committing
to the full persona set at scale.

Reuses SYSTEM_PROMPT, chat(), clean_answer() and MCPToolProvider from mcp_agent.py unchanged, so
the agent side of this conversation is byte-identical to the single-turn evaluations — only the
source of the "user" turns changes.

Requires both vLLM servers up (agent + persona) and the MCP tool server:
    python scripts/mcp_server.py --port 8085 --profile full --annotations   # /venv/mcp

Run one persona once:
    python scripts/persona_agent.py --persona P01_evasive_t08 --agent-model Qwen/Qwen2.5-32B-Instruct-AWQ \
        --persona-model stelterlab/Mistral-Small-24B-Instruct-2501-AWQ

Run all personas in the pilot file, N repetitions each:
    python scripts/persona_agent.py --personas-file dataset/personas_pilot.json \
        --agent-model Qwen/Qwen2.5-32B-Instruct-AWQ \
        --persona-model stelterlab/Mistral-Small-24B-Instruct-2501-AWQ \
        --repetitions 1 --output results/persona_pilot.json
"""

import argparse
import asyncio
import json
import time

import requests
from fastmcp import Client

from mcp_agent import MCPToolProvider, chat, clean_answer, SYSTEM_PROMPT, MODEL_URL, MCP_URL

PERSONA_URL = "http://localhost:8082/v1"
MAX_DIALOGUE_TURNS = 6   # outer cap: persona<->agent exchanges
MAX_AGENT_SUBTURNS = 6   # inner cap: tool-call round trips within one agent reply (same as MAX_TURNS elsewhere)
END_MARKER = "[END_CONVERSATION]"


def persona_chat(model: str, model_url: str, messages: list) -> dict:
    """Separate from mcp_agent.chat(): the persona never calls tools, and vLLM (like the OpenAI
    API itself) rejects `tools: []` + `tool_choice: auto` with a 400 rather than treating an empty
    array as 'no tools' — so this omits both keys instead of reusing chat() with an empty list.
    Temperature is not 0: a deterministic persona would say the same thing every pilot run, which
    defeats the point of a simulator (agent.py/mcp_agent.py's 0.0 is for the side being *measured*,
    reproducibly — the persona is the human stand-in, not the system under test).
    """
    payload = {"model": model, "messages": messages, "temperature": 0.7, "max_tokens": 300}
    resp = requests.post(f"{model_url}/chat/completions", json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


async def run_agent_turn(model: str, model_url: str, messages: list, provider: MCPToolProvider,
                          max_turns: int = MAX_AGENT_SUBTURNS) -> tuple:
    """One dialogue turn of the agent's ReAct loop, mutating `messages` in place.

    Unlike mcp_agent.run_task (which discards `messages` after one task), this list is the
    persistent conversation and must have the assistant's final answer appended back into it —
    otherwise the next dialogue turn loses the agent's own last reply.
    """
    tool_calls_log = []
    for _ in range(max_turns):
        body = chat(model, model_url, messages, provider.schemas)
        msg = body["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            answer = clean_answer(msg.get("content", ""))
            messages.append({"role": "assistant", "content": answer})
            return answer, tool_calls_log, False

        messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": tool_calls})
        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}
            result = await provider.execute(name, args)
            tool_calls_log.append({"name": name, "arguments": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

    return "", tool_calls_log, True


async def run_conversation(agent_model: str, agent_url: str, persona_model: str, persona_url: str,
                            persona: dict, provider: MCPToolProvider, verbose: bool = True) -> dict:
    agent_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    persona_messages = [{"role": "system", "content": persona["system_prompt"]}]
    max_turns = persona.get("max_dialogue_turns", MAX_DIALOGUE_TURNS)
    min_turns = persona.get("min_dialogue_turns", 1)  # 0-indexed dturn must reach this before ending is allowed

    transcript = []
    all_tool_calls = []
    ended_by = "max_turns"
    t0 = time.monotonic()

    for dturn in range(max_turns):
        persona_body = persona_chat(persona_model, persona_url, persona_messages)
        persona_text = clean_answer(persona_body["choices"][0]["message"].get("content", ""))
        said = persona_text.replace(END_MARKER, "").strip()
        transcript.append({"turn": dturn, "role": "persona", "text": said})
        if verbose:
            print(f"  [turn {dturn+1}] persona: {said[:100]!r}")

        # Prompt-only enforcement of "don't end before turn N" isn't reliable — seen repeatedly
        # across personas/models even with the strongest wording tried (POSTMORTEM H5/E33/E34).
        # min_dialogue_turns forces the loop to continue regardless of what the model outputs,
        # until dturn reaches it; only then can the persona actually end the conversation.
        if END_MARKER in persona_text and dturn >= min_turns:
            ended_by = "persona"
            break

        persona_messages.append({"role": "assistant", "content": persona_text})
        agent_messages.append({"role": "user", "content": said})

        agent_answer, agent_tools, hit_max = await run_agent_turn(agent_model, agent_url, agent_messages, provider)
        all_tool_calls.extend(agent_tools)
        transcript.append({"turn": dturn, "role": "agent", "text": agent_answer, "tool_calls": agent_tools})
        if verbose:
            for tc in agent_tools:
                print(f"    tool={tc['name']} args={tc['arguments']} -> {tc['result'][:100]}")
            print(f"  [turn {dturn+1}] agent: {agent_answer[:100]!r}")
        if hit_max:
            ended_by = "agent_hit_max_subturns"
            break

        persona_messages.append({"role": "user", "content": agent_answer})

    called = [tc["name"] for tc in all_tool_calls]
    return {
        "persona_id": persona["id"],
        "transcript": transcript,
        "tool_calls": all_tool_calls,
        "tools_called_names": called,
        "dialogue_turns": len([t for t in transcript if t["role"] == "persona"]),
        "ended_by": ended_by,
        "latency_s": round(time.monotonic() - t0, 3),
        "forbidden_tools": persona.get("forbidden_tools", []),
        "forbidden_called": [t for t in called if t in persona.get("forbidden_tools", [])],
    }


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--agent-model", required=True)
    p.add_argument("--agent-url", default=MODEL_URL)
    p.add_argument("--persona-model", required=True)
    p.add_argument("--persona-url", default=PERSONA_URL)
    p.add_argument("--mcp-url", default=MCP_URL)
    p.add_argument("--persona", help="Run a single persona id from --personas-file")
    p.add_argument("--personas-file", default="dataset/personas_pilot.json")
    p.add_argument("--repetitions", type=int, default=1)
    p.add_argument("--output", help="Where to save JSON results (omit to just print)")
    return p.parse_args()


async def main():
    args = parse_args()
    with open(args.personas_file, encoding="utf-8") as f:
        personas = {p["id"]: p for p in json.load(f)["personas"]}

    targets = [personas[args.persona]] if args.persona else list(personas.values())

    async with Client(args.mcp_url) as client:
        provider = MCPToolProvider(client)
        await provider.discover()
        print(f"Discovered {len(provider.schemas)} tools via MCP ({args.mcp_url})")

        results = []
        for persona in targets:
            for rep in range(args.repetitions):
                print(f"\n=== {persona['id']} (rep {rep+1}/{args.repetitions}) ===")
                r = await run_conversation(args.agent_model, args.agent_url,
                                            args.persona_model, args.persona_url,
                                            persona, provider)
                r["repetition"] = rep
                results.append(r)
                flag = "  <-- FORBIDDEN TOOL CALLED" if r["forbidden_called"] else ""
                print(f"  ended_by={r['ended_by']} turns={r['dialogue_turns']} "
                      f"tools={r['tools_called_names']}{flag}")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved -> {args.output}")
    else:
        print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
