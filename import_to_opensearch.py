"""
Import opensearch_dump.json ke OpenSearch.
Dijalankan otomatis oleh start.sh saat container pertama kali startup.

Usage: python import_to_opensearch.py
"""

import json
import os
import time
from opensearchpy import OpenSearch, helpers

INDICES = [
    "departments",
    "medical_teams",
    "doctors",
    "patients",
    "patient_treatments",
    "billings",
    "billing_items",
]

os_host = os.getenv("OPENSEARCH_HOST", "localhost")
os_port = int(os.getenv("OPENSEARCH_PORT", "9200"))
os_user = os.getenv("OPENSEARCH_USER", "admin")
os_pass = os.getenv("OPENSEARCH_PASSWORD", "YourStrongPassword123!")
os_ssl  = os.getenv("OPENSEARCH_USE_SSL", "true").lower() == "true"


def make_client() -> OpenSearch:
    return OpenSearch(
        hosts=[{"host": os_host, "port": os_port}],
        http_auth=(os_user, os_pass) if os_ssl else None,
        use_ssl=os_ssl,
        verify_certs=False,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
    )


# Tunggu OpenSearch siap (max 5 menit)
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
    print("OpenSearch tidak dapat dijangkau setelah 5 menit. Abort.")
    raise SystemExit(1)

# Cek apakah data sudah ada (idempoten)
if client.indices.exists(index="departments"):
    count = client.count(index="departments")["count"]
    if count > 0:
        print(f"Data sudah ada ({count} dokumen di 'departments'). Skip import.")
        raise SystemExit(0)

# Baca dump
dump_path = os.getenv("DUMP_PATH", "opensearch_dump.json")
print(f"Membaca {dump_path}...", flush=True)
with open(dump_path, "r", encoding="utf-8") as f:
    dump = json.load(f)

# Import tiap indeks
for index in INDICES:
    if index not in dump["indices"]:
        print(f"  {index}: tidak ada di dump, skip")
        continue

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

# Verifikasi
print("\nVerifikasi:")
for index in INDICES:
    count = client.count(index=index)["count"]
    print(f"  {index:25s}: {count} dokumen")

print("\nImport selesai!")
