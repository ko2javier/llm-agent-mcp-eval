import re


def normalize(query: str) -> str:
    """Lowercase, turn hyphens/underscores into word breaks, strip remaining punctuation."""
    q = re.sub(r"[-_]", " ", query.lower())
    return re.sub(r"[^\w\s]", "", q)


def classify(query: str) -> dict:
    """
    Returns:
      {"type": "deterministic", "fact_type": str, "keywords": list[str]}
      or
      {"type": "rag"}
    """
    q = normalize(query)
    words = set(q.split())

    # ── Rule 1: version ──────────────────────────────────────────────────────
    version_triggers = {"version", "v1", "v2", "sunset", "deprecated", "release"}
    if words & version_triggers:
        if {"v1", "sunset", "deprecated"} & words:
            keywords = ["v1", "sunset", "deprecated"]
        else:
            keywords = ["api", "version", "current"]
        return {"type": "deterministic", "fact_type": "version", "keywords": keywords}

    # ── Rule 2: error_code ───────────────────────────────────────────────────
    error_phrase_triggers = {"error code", "error when", "status code", "what error"}
    error_token_triggers = {"429", "404", "401", "422"}
    has_error_phrase = any(p in q for p in error_phrase_triggers)
    has_error_token = bool(words & error_token_triggers)
    if has_error_phrase or has_error_token:
        keywords = []
        if "429" in words or "rate" in words:
            keywords = ["rate", "limit", "exceeded", "429"]
        elif "401" in words or "revoked" in words:
            keywords = ["revoked", "api", "key"]
        elif "refund" in words:
            keywords = ["refund", "window", "expired"]
        elif "capture" in words:
            keywords = ["capture", "window", "expired"]
        elif "404" in words or "not found" in q:
            keywords = ["not", "found", "404"]
        else:
            keywords = ["rate", "limit", "exceeded", "429"]
        return {"type": "deterministic", "fact_type": "error_code", "keywords": keywords}

    # ── Rule 3: rate_limit ───────────────────────────────────────────────────
    rate_phrases = {"rate limit", "requests per", "requests/min", "how many requests"}
    rate_tokens = {"concurrent", "ratelimit", "burst"}
    webhook_with_plan = "webhook endpoint" in q and bool(
        {"free", "starter", "pro", "enterprise"} & words
    )
    has_rate_phrase = any(p in q for p in rate_phrases)
    has_rate_token = bool(words & rate_tokens)
    if has_rate_phrase or has_rate_token or webhook_with_plan:
        plan_kw = next(
            (p for p in ("enterprise", "pro", "starter", "free") if p in words), None
        )
        keywords = []
        if plan_kw:
            if "concurrent" in words:
                keywords = [plan_kw, "concurrent", "connections"]
            elif "burst" in words:
                keywords = [plan_kw, "burst", "limit"]
            elif "webhook" in words:
                keywords = [plan_kw, "webhook", "endpoints"]
            elif "day" in words:
                keywords = [plan_kw, "requests", "day"]
            else:
                keywords = [plan_kw, "requests", "minute"]
        elif "ip" in words:
            keywords = ["ip", "limit", "requests", "minute"]
        else:
            keywords = ["requests", "minute"]
        return {"type": "deterministic", "fact_type": "rate_limit", "keywords": keywords}

    # ── Rule 4: constraint ───────────────────────────────────────────────────
    constraint_triggers = {
        "maximum", "minimum", "how many", "limit", "how long",
        "within how many", "up to", "currencies", "currency",
    }
    has_constraint = any(p in q for p in constraint_triggers)
    if has_constraint:
        subject_map = [
            ({"idempotency"},                      ["idempotency", "key", "expiration"]),
            ({"pagination"},                        ["pagination", "limit", "maximum"]),
            ({"page"},                              ["pagination", "limit", "maximum"]),
            ({"metadata"},                          ["metadata", "maximum", "keys"]),
            ({"trial"},                             ["trial", "maximum", "days", "subscription"]),
            ({"currency", "currencies"},            ["currency", "supported"]),
            ({"capture"},                           ["capture", "window", "days"]),
            ({"partial"},                           ["partial", "refund", "minimum", "amount"]),
            ({"refund", "days"},                    ["refund", "days", "window"]),
            ({"refunds", "days"},                   ["refund", "days", "window"]),
            ({"refund"},                            ["refund", "maximum", "payment"]),
            ({"refunds"},                           ["refund", "maximum", "payment"]),
            ({"description"},                       ["description", "maximum", "characters", "payment"]),
            ({"webhook", "url"},                    ["webhook", "url", "maximum", "length"]),
            ({"webhook", "retry"},                  ["webhook", "retry", "failed", "delivery"]),
            ({"webhook"},                           ["webhook", "url", "maximum", "length"]),
        ]
        for subject_set, keywords in subject_map:
            if subject_set <= words:
                return {"type": "deterministic", "fact_type": "constraint", "keywords": keywords}
        # fallback: pick first matching single keyword
        for subject_set, keywords in subject_map:
            if words & subject_set:
                return {"type": "deterministic", "fact_type": "constraint", "keywords": keywords}

    # ── Default: RAG ─────────────────────────────────────────────────────────
    return {"type": "rag"}


if __name__ == "__main__":
    test_queries = [
        # version (2)
        "What is the current API version?",
        "When is v1 being sunset and deprecated?",
        # error_code (2)
        "What error code do I get when the rate limit is exceeded?",
        "What is the status code 404 for?",
        # rate_limit (3)
        "How many requests per minute does the free plan allow?",
        "What is the rate limit for the pro plan per day?",
        "How many concurrent connections can pro plan use?",
        # constraint (3)
        "What is the maximum number of refunds per payment?",
        "How long is the capture window?",
        "What is the idempotency key expiration?",
        # rag (2)
        "How do I authenticate with OAuth?",
        "Can you explain how webhooks work in general?",
    ]

    for query in test_queries:
        result = classify(query)
        print(f"Q: {query!r}")
        print(f"   → {result}\n")
