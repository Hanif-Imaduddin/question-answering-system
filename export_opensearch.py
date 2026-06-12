"""
Export index diabetes_encounters dari OpenSearch ke opensearch_dump.json.
Jalankan setelah load_to_opensearch_with_embedding.py selesai.

Usage:
    python export_opensearch.py
"""

import json
import os

from dotenv import load_dotenv
from opensearchpy import OpenSearch

load_dotenv()

INDICES = ["diabetes_encounters"]

client = OpenSearch(
    hosts=[{"host": os.getenv("OPENSEARCH_HOST", "localhost"), "port": int(os.getenv("OPENSEARCH_PORT", "9200"))}],
    http_auth=(
        os.getenv("OPENSEARCH_USER", "admin"),
        os.getenv("OPENSEARCH_PASSWORD", "YourStrongPassword123!"),
    ),
    use_ssl=os.getenv("OPENSEARCH_USE_SSL", "true").lower() == "true",
    verify_certs=False,
    ssl_assert_hostname=False,
    ssl_show_warn=False,
)

print("Terhubung ke OpenSearch:", client.info()["version"]["number"])

dump = {"version": "2.0", "case": "diabetes_readmission", "indices": {}}

for index in INDICES:
    if not client.indices.exists(index=index):
        raise SystemExit(f"Index '{index}' belum ada. Jalankan load_to_opensearch_with_embedding.py dulu.")

    print(f"Mengekspor {index}...", end=" ", flush=True)
    mapping_resp = client.indices.get_mapping(index=index)
    mapping = mapping_resp[index]["mappings"]

    docs = []
    resp = client.search(index=index, body={"query": {"match_all": {}}}, size=500, scroll="5m")
    scroll_id = resp["_scroll_id"]
    hits = resp["hits"]["hits"]

    while hits:
        for hit in hits:
            docs.append({"_id": hit["_id"], "_source": hit["_source"]})
        resp = client.scroll(scroll_id=scroll_id, scroll="5m")
        scroll_id = resp["_scroll_id"]
        hits = resp["hits"]["hits"]

    client.clear_scroll(scroll_id=scroll_id)
    dump["indices"][index] = {"mapping": mapping, "docs": docs}
    print(f"{len(docs)} dokumen")

output_path = os.getenv("DUMP_PATH", "opensearch_dump.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(dump, f, ensure_ascii=False)

size_mb = os.path.getsize(output_path) / (1024 * 1024)
print(f"Selesai menyimpan {output_path} ({size_mb:.1f} MB)")
