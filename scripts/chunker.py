import os
import json

DOCS_DIR = "docs"
OUTPUT_FILE = "output/chunks.json"
MIN_CHUNK_LEN = 50

os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

chunks = []
chunk_id = 0

for root, dirs, files in os.walk(DOCS_DIR):
    for filename in files:
        if not filename.endswith(".md"):
            continue
        filepath = os.path.join(root, filename)
        rel_path = os.path.relpath(filepath, DOCS_DIR)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        for paragraph in content.split("\n\n"):
            text = paragraph.strip()
            if len(text) < MIN_CHUNK_LEN:
                continue
            chunks.append({
                "chunk_id": chunk_id,
                "source_file": rel_path,
                "chunk_text": text,
            })
            chunk_id += 1

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(chunks, f, ensure_ascii=False, indent=2)

print(f"Total chunks: {len(chunks)}")
