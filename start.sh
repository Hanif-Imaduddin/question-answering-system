#!/bin/bash
set -e

echo "=== Import data ke OpenSearch (jika perlu) ==="
python import_to_opensearch.py

echo "=== Menjalankan RAG app ==="
exec python rag_app.py
