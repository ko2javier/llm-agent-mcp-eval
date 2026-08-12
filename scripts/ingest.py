"""
Ingest chunks.json into PostgreSQL with pgvector embeddings.

Run from the project root:
    python scripts/ingest.py
"""

import json
import os
import time

import psycopg2
import psycopg2.extras
import requests

# ── Configuration ─────────────────────────────────────────────────────────────

CHUNKS_FILE   = "output/chunks.json"
EMBEDDING_URL = "http://localhost:8083/embed"   # TEI endpoint

DB_HOST     = "localhost"
DB_PORT     = 5432
DB_NAME     = "nexuspay_rag"
DB_USER     = "postgres"
DB_PASSWORD = "postgres"

BATCH_SIZE   = 32   # chunks per embedding request
HTTP_TIMEOUT = 30   # seconds

# ── DDL ───────────────────────────────────────────────────────────────────────

DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id          SERIAL PRIMARY KEY,
    chunk_id    INTEGER,
    source_file TEXT,
    chunk_text  TEXT,
    embedding   vector(1024)
);

CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def embed_batch(texts: list[str]) -> list[list[float]] | None:
    """
    POST a batch of texts to TEI.
    TEI accepts {"inputs": [str, ...]} and returns [[float, ...], ...].
    Returns None on error.
    """
    try:
        resp = requests.post(
            EMBEDDING_URL,
            json={"inputs": texts},
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        # Normalise: TEI may return a nested list or a flat list for batch=1
        if isinstance(data[0], float):
            return [data]
        return data
    except Exception as exc:
        print(f"  [embed error] {exc}")
        return None


def existing_chunk_ids(cur) -> set[int]:
    cur.execute("SELECT chunk_id FROM chunks;")
    return {row[0] for row in cur.fetchall()}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    t_start = time.monotonic()

    # ── Load chunks ───────────────────────────────────────────────────────────
    print(f"Loading {CHUNKS_FILE} …")
    chunks = load_json(CHUNKS_FILE)
    print(f"  {len(chunks)} chunks loaded.")

    # ── Connect ───────────────────────────────────────────────────────────────
    print(f"Connecting to PostgreSQL {DB_HOST}:{DB_PORT}/{DB_NAME} …")
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT,
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
    )
    conn.autocommit = False
    cur = conn.cursor()

    # ── Create table and index ────────────────────────────────────────────────
    print("Applying DDL …")
    cur.execute(DDL)
    conn.commit()

    # ── Skip already-ingested chunks ─────────────────────────────────────────
    done_ids = existing_chunk_ids(cur)
    pending  = [c for c in chunks if c["chunk_id"] not in done_ids]
    print(f"  {len(done_ids)} already in DB, {len(pending)} to ingest.")

    if not pending:
        print("Nothing to do.")
        cur.close()
        conn.close()
        return

    # ── Batch-embed and insert ────────────────────────────────────────────────
    inserted = 0
    total    = len(pending)

    for batch_start in range(0, total, BATCH_SIZE):
        batch = pending[batch_start : batch_start + BATCH_SIZE]
        texts = [c["chunk_text"] for c in batch]

        embeddings = embed_batch(texts)
        if embeddings is None:
            print(f"  [skip] embedding failed for batch starting at {batch_start}")
            continue

        if len(embeddings) != len(batch):
            print(f"  [skip] expected {len(batch)} embeddings, got {len(embeddings)}")
            continue

        rows = [
            (c["chunk_id"], c["source_file"], c["chunk_text"], emb)
            for c, emb in zip(batch, embeddings)
        ]

        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO chunks (chunk_id, source_file, chunk_text, embedding)
            VALUES %s
            """,
            rows,
            template="(%s, %s, %s, %s::vector)",
        )
        conn.commit()

        inserted += len(rows)
        print(f"  Inserted {inserted}/{total} chunks")

    # ── Done ──────────────────────────────────────────────────────────────────
    elapsed = time.monotonic() - t_start
    print(f"\nDone. {inserted} chunks inserted in {elapsed:.1f}s.")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
