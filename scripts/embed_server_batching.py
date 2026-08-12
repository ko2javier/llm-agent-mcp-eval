"""
TEI-compatible embedding server with dynamic batching.

Collects concurrent requests in a time window (BATCH_WINDOW_MS) and sends
them to the GPU in a single model.encode() call — same behavior as TEI Docker.

Launch:
    HF_HOME=/workspace/hf_cache PORT=8081 python3 /workspace/embed_server_batching.py

Endpoints (same API as TEI and embed_server.py):
    GET  /health
    GET  /info
    POST /embed          {"inputs": "text" | ["t1","t2"]}  → [[...], [...]]
    POST /v1/embeddings  OpenAI-compatible
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Union

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MODEL_ID        = os.getenv("MODEL_ID",    "BAAI/bge-m3")
HF_HOME         = os.getenv("HF_HOME",     "/workspace/hf_cache")
PORT            = int(os.getenv("PORT",    "8081"))
BATCH_WINDOW_MS = int(os.getenv("BATCH_WINDOW_MS", "20"))   # collect window in ms
MAX_BATCH_SIZE  = int(os.getenv("MAX_BATCH_SIZE",  "128"))  # hard cap per forward pass

model: SentenceTransformer = None

# Each item: (texts: list[str], normalize: bool, future: asyncio.Future)
_queue: asyncio.Queue = None


async def _batch_worker():
    """Background loop: drain the queue every BATCH_WINDOW_MS ms."""
    loop = asyncio.get_event_loop()
    while True:
        # Wait for at least one request
        first = await _queue.get()
        batch = [first]

        # Collect more requests that arrive within the window
        deadline = loop.time() + BATCH_WINDOW_MS / 1000.0
        while len(batch) < MAX_BATCH_SIZE:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                item = await asyncio.wait_for(_queue.get(), timeout=remaining)
                batch.append(item)
            except asyncio.TimeoutError:
                break

        # Flatten all texts into one list, remembering slice boundaries
        all_texts   = []
        slices      = []
        normalizes  = []
        offset = 0
        for texts, normalize, _ in batch:
            all_texts.extend(texts)
            slices.append((offset, offset + len(texts)))
            normalizes.append(normalize)
            offset += len(texts)

        # Single GPU forward pass for the entire batch
        try:
            vecs = await loop.run_in_executor(
                None,
                lambda: model.encode(
                    all_texts,
                    normalize_embeddings=False,   # we normalise per-request below
                    convert_to_numpy=True,
                    batch_size=MAX_BATCH_SIZE,
                )
            )

            for (start, end), normalize, (_, _, fut) in zip(slices, normalizes, batch):
                chunk = vecs[start:end]
                if normalize:
                    norms = (chunk ** 2).sum(axis=1, keepdims=True) ** 0.5
                    chunk = chunk / norms
                fut.set_result(chunk.tolist())

        except Exception as exc:
            for _, _, fut in batch:
                if not fut.done():
                    fut.set_exception(exc)

        log.debug(f"batch processed: {len(all_texts)} texts from {len(batch)} requests")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model, _queue
    os.environ["HF_HOME"] = HF_HOME
    log.info(f"Loading {MODEL_ID} onto CUDA …")
    model = SentenceTransformer(MODEL_ID, device="cuda")
    model.half()
    log.info(f"Model ready. Batch window: {BATCH_WINDOW_MS}ms, max batch: {MAX_BATCH_SIZE}")

    _queue = asyncio.Queue()
    worker = asyncio.create_task(_batch_worker())
    yield
    worker.cancel()
    del model
    torch.cuda.empty_cache()


app = FastAPI(title="embed-server-batching", lifespan=lifespan)


class EmbedRequest(BaseModel):
    inputs: Union[str, list[str]]
    normalize: bool = True
    truncate: bool = True


class OAIEmbedRequest(BaseModel):
    input: Union[str, list[str]]
    model: str = MODEL_ID
    encoding_format: str = "float"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/info")
async def info():
    return {
        "model_id":         MODEL_ID,
        "model_dtype":      "float16",
        "batch_window_ms":  BATCH_WINDOW_MS,
        "max_batch_size":   MAX_BATCH_SIZE,
    }


@app.post("/embed")
async def embed(req: EmbedRequest):
    texts = [req.inputs] if isinstance(req.inputs, str) else req.inputs
    if not texts:
        raise HTTPException(status_code=400, detail="Empty inputs")

    loop = asyncio.get_event_loop()
    fut  = loop.create_future()
    await _queue.put((texts, req.normalize, fut))
    return await fut


@app.post("/v1/embeddings")
async def oai_embed(req: OAIEmbedRequest):
    texts = [req.input] if isinstance(req.input, str) else req.input
    loop  = asyncio.get_event_loop()
    fut   = loop.create_future()
    await _queue.put((texts, True, fut))
    vecs  = await fut
    return {
        "object": "list",
        "data":   [{"object": "embedding", "index": i, "embedding": v}
                   for i, v in enumerate(vecs)],
        "model":  MODEL_ID,
        "usage":  {"prompt_tokens": 0, "total_tokens": 0},
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")