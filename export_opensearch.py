"""
Export semua indeks OpenSearch (termasuk embedding vectors) ke opensearch_dump.json.
Jalankan SEKALI di lokal sebelum deploy ke Railway.

Usage: python export_opensearch.py
"""

import json
import os
from opensearchpy import OpenSearch

INDICES = [
    "departments",
    "medical_teams",
    "doctors",
    "patients",
    "patient_treatments",
    "billings",
    "billing_items",
]

client = OpenSearch(
    hosts=[{"host": "localhost", "port": 9200}],
    http_auth=("admin", "YourStrongPassword123!"),
    use_ssl=True,
    verify_certs=False,
    ssl_assert_hostname=False,
    ssl_show_warn=False,
)

print("Terhubung ke OpenSearch:", client.info()["version"]["number"])

dump = {"version": "1.0", "indices": {}}

for index in INDICES:
    print(f"Mengekspor {index}...", end=" ", flush=True)

    mapping_resp = client.indices.get_mapping(index=index)
    mapping = mapping_resp[index]["mappings"]

    docs = []
    resp = client.search(
        index=index,
        body={"query": {"match_all": {}}},
        size=500,
        scroll="5m",
    )
    scroll_id = resp["_scroll_id"]
    hits = resp["hits"]["hits"]

    while hits:
        for hit in hits:
            docs.append({"_id": hit["_id"], "_source": hit["_source"]})
        resp = client.scroll(scroll_id=scroll_id, scroll="5m")
        scroll_id = resp["_scroll_id"]
        hits = resp["hits"]["hits"]

    client.clear_scroll(scroll_id=scroll_id)

    dump["indices"][index] = {
        "mapping": mapping,
        "docs": docs,
    }
    print(f"{len(docs)} dokumen")

output_path = "opensearch_dump.json"
print(f"\nMenyimpan ke {output_path}...", end=" ", flush=True)
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(dump, f, ensure_ascii=False)
print("Selesai!")

size_mb = os.path.getsize(output_path) / (1024 * 1024)
print(f"Ukuran file: {size_mb:.1f} MB")
print("\nSelanjutnya: deploy ke Railway lalu jalankan 'railway up'")
