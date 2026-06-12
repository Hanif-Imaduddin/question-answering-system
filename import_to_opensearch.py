"""
Import opensearch_dump.json ke OpenSearch untuk kasus Diabetes Readmission.
Dijalankan otomatis oleh Dockerfile sebelum rag_app.py.

Usage:
    python import_to_opensearch.py
"""

import json
import os
import time

from opensearchpy import OpenSearch, helpers

INDICES = ["diabetes_encounters"]

os_host = os.getenv("OPENSEARCH_HOST", "localhost")
os_port = int(os.getenv("OPENSEARCH_PORT", "9200"))
os_user = os.getenv("OPENSEARCH_USER", "admin")
os_pass = os.getenv("OPENSEARCH_PASSWORD", "YourStrongPassword123!")
os_ssl = os.getenv("OPENSEARCH_USE_SSL", "true").lower() == "true"


def make_client() -> OpenSearch:
    return OpenSearch(
        hosts=[{"host": os_host, "port": os_port}],
        http_auth=(os_user, os_pass) if os_ssl else None,
        use_ssl=os_ssl,
        verify_certs=False,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
    )


print("Menunggu OpenSearch siap...", flush=True)
client = None
for attempt in range(60):
    try:
        client = make_client()
        version = client.info()["version"]["number"]
        print(f"OpenSearch {version} siap.")
        break
    except Exception as exc:
        print(f"  Percobaan {attempt + 1}/60: {exc}", flush=True)
        time.sleep(5)

if client is None:
    raise SystemExit("OpenSearch tidak dapat dijangkau setelah 5 menit. Abort.")

if client.indices.exists(index="diabetes_encounters"):
    count = client.count(index="diabetes_encounters")["count"]
    if count > 0:
        print(f"Data sudah ada ({count} dokumen di 'diabetes_encounters'). Skip import.")
        raise SystemExit(0)

dump_path = os.getenv("DUMP_PATH", "opensearch_dump.json")
print(f"Membaca {dump_path}...", flush=True)
with open(dump_path, "r", encoding="utf-8") as f:
    dump = json.load(f)

missing = [index for index in INDICES if index not in dump.get("indices", {})]
if missing:
    raise SystemExit(
        "Dump OpenSearch belum berisi index diabetes. "
        "Jalankan load_to_opensearch_with_embedding.py lalu export_opensearch.py. "
        f"Index hilang: {', '.join(missing)}"
    )

for index in INDICES:
    entry = dump["indices"][index]

    if client.indices.exists(index=index):
        client.indices.delete(index=index)

    client.indices.create(index=index, body={
        "settings": {"index": {"knn": True}},
        "mappings": entry["mapping"],
    })

    actions = [
        {"_index": index, "_id": doc["_id"], "_source": doc["_source"]}
        for doc in entry["docs"]
    ]
    success, errors = helpers.bulk(client, actions, raise_on_error=False)
    print(f"  {index}: {success} dokumen diimpor", flush=True)
    if errors:
        print(f"    {len(errors)} error: {errors[:2]}")

print("\nVerifikasi:")
for index in INDICES:
    count = client.count(index=index)["count"]
    print(f"  {index:25s}: {count} dokumen")

print("\nImport selesai!")
