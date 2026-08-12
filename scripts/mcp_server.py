"""
MCP server exposing the NexusPay tools over HTTP (streamable-http transport).

Every tool body delegates to the implementations in `tools.py` / `tools_extended.py`, so the
logic, the error handling and the fee schedule stay there — the single source of truth. What
changes is *how* a client learns about the tools: instead of importing a hardcoded schema, it
asks this server via `tools/list` at runtime.

Catalogue profiles (--profile) exist to measure how tool-selection accuracy degrades as the
catalogue grows, which published evaluations put at roughly 10-15 tools:

    core    5 tools  — the original baseline; descriptions taken verbatim from TOOLS_SCHEMA
    medium  12 tools — around the reported threshold
    full    19 tools — past it, and including four deliberately confusable write tools
                       (initiate_refund / void_authorization / accept_dispute / cancel_subscription)

The `core` profile advertises byte-identical names, descriptions and parameter schemas to the
hardcoded `TOOLS_SCHEMA`, which is what makes the comparison against `agent.py` fair.

Run it:
    python scripts/mcp_server.py --port 8085 --profile core
    python scripts/mcp_server.py --port 8085 --profile full --annotations

Then point the agent at it:
    python scripts/mcp_agent.py --model <model> --mcp-url http://localhost:8085/mcp --task "..."
"""

import argparse
from typing import Annotated, Literal

from fastmcp import FastMCP
from fastmcp.tools import Tool
from pydantic import Field

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from tools import TOOLS_SCHEMA, execute_tool
import tools_extended

HOST = "127.0.0.1"
PORT = 8085
PATH = "/mcp"

# name -> description, lifted from the OpenAI-style schemas in tools.py so the MCP-advertised
# descriptions cannot drift from the hardcoded ones.
DESCRIPTIONS = {t["function"]["name"]: t["function"]["description"] for t in TOOLS_SCHEMA}


# --------------------------------------------------------------------------- core five
# Thin wrappers routed through execute_tool, which converts exceptions into {"error": ...}
# JSON exactly as the hardcoded agent sees them.

def rag_lookup(
    question: Annotated[str, Field(description="The question to search for")],
) -> str:
    return execute_tool("rag_lookup", {"question": question})


def check_transaction_status(
    transaction_id: Annotated[str, Field(description="e.g. 'TX-4521'")],
) -> str:
    return execute_tool("check_transaction_status", {"transaction_id": transaction_id})


def initiate_refund(
    transaction_id: str,
    amount: Annotated[
        float,
        Field(description="Amount to refund, in the transaction's currency major units (e.g. 50.00)"),
    ],
) -> str:
    return execute_tool("initiate_refund", {"transaction_id": transaction_id, "amount": amount})


def get_exchange_rate(base_currency: str, target_currency: str) -> str:
    return execute_tool(
        "get_exchange_rate",
        {"base_currency": base_currency, "target_currency": target_currency},
    )


def calculate_fees(amount: float, transaction_type: Literal["payment", "payout"]) -> str:
    return execute_tool("calculate_fees", {"amount": amount, "transaction_type": transaction_type})


CORE_WRAPPERS = {
    "rag_lookup": rag_lookup,
    "check_transaction_status": check_transaction_status,
    "initiate_refund": initiate_refund,
    "get_exchange_rate": get_exchange_rate,
    "calculate_fees": calculate_fees,
}


# --------------------------------------------------------------------------- assembly

def _annotations_for(name: str) -> dict:
    """MCP tool annotations — behavioural hints the hardcoded OpenAI schema has no place for.

    Whether a model actually respects destructiveHint is one of the things worth measuring,
    so these are opt-in via --annotations rather than always on.
    """
    if name in tools_extended.READ_ONLY_TOOLS:
        return {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True}
    return {
        "readOnlyHint": False,
        "destructiveHint": True,
        # every extended write takes an idempotency_key; the original refund does not
        "idempotentHint": name != "initiate_refund",
    }


def build_server(profile: str, annotations: bool = False) -> FastMCP:
    mcp = FastMCP("nexuspay-tools")
    for fn in tools_extended.PROFILES[profile]:
        name = fn.__name__
        # Core five keep their TOOLS_SCHEMA description and their execute_tool wrapper;
        # extended tools describe themselves through their docstring.
        impl = CORE_WRAPPERS.get(name, fn)
        mcp.add_tool(Tool.from_function(
            impl,
            name=name,
            description=DESCRIPTIONS.get(name),  # None -> FastMCP falls back to the docstring
            annotations=_annotations_for(name) if annotations else None,
        ))
    return mcp


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default=HOST)
    p.add_argument("--port", type=int, default=PORT)
    p.add_argument("--path", default=PATH, help="HTTP path the MCP endpoint is mounted on")
    p.add_argument("--profile", default="core", choices=sorted(tools_extended.PROFILES),
                   help="Which tool catalogue to expose (core=5, medium=12, full=19)")
    p.add_argument("--annotations", action="store_true",
                   help="Advertise MCP tool annotations (readOnlyHint/destructiveHint/idempotentHint)")
    return p.parse_args()


def main():
    args = parse_args()
    mcp = build_server(args.profile, args.annotations)
    names = [fn.__name__ for fn in tools_extended.PROFILES[args.profile]]
    print(f"MCP server 'nexuspay-tools' -> http://{args.host}:{args.port}{args.path}")
    print(f"Profile '{args.profile}': {len(names)} tools"
          f"{' (with annotations)' if args.annotations else ''}: {', '.join(names)}")
    mcp.run(transport="http", host=args.host, port=args.port, path=args.path)


if __name__ == "__main__":
    main()
