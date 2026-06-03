"""
Load Data Rumah Sakit ke OpenSearch + Vector Embedding
========================================================
Instalasi:
    pip install opensearch-py openai python-dotenv tqdm

Model embedding yang dipakai:
    Qwen/Qwen3-Embedding-8B via DeepInfra API
    -> 4096 dimensi, support Bahasa Indonesia

Jalankan SETELAH generate_hospital_data.py:
    python load_to_opensearch_with_embedding.py
"""

import json
import os
from dotenv import load_dotenv
from openai import OpenAI
from opensearchpy import OpenSearch, helpers
from tqdm import tqdm  # pip install tqdm  (progress bar)

load_dotenv()

# ----------------------------------------------
# 1. Koneksi OpenSearch
# ----------------------------------------------
client = OpenSearch(
    hosts=[{"host": "localhost", "port": 9200}],
    http_auth=("admin", "YourStrongPassword123!"),
    use_ssl=True,
    verify_certs=False,
    ssl_assert_hostname=False,
    ssl_show_warn=False,
)
print("Terhubung ke OpenSearch:", client.info()["version"]["number"])

# ----------------------------------------------
# 2. Setup embedding client (DeepInfra)
# ----------------------------------------------
DEEPINFRA_API_TOKEN = os.getenv("DEEPINFRA_API_TOKEN")
DEEPINFRA_API_URL   = os.getenv("DEEPINFRA_API_URL")
EMBEDDING_MODEL     = os.getenv("EMBEDDING_MODEL")

embed_client = OpenAI(
    api_key=DEEPINFRA_API_TOKEN,
    base_url=DEEPINFRA_API_URL,
)
VECTOR_DIM = 768  # dimensi output google/embeddinggemma-300m
print(f"Embedding model: {EMBEDDING_MODEL} ({VECTOR_DIM} dim)")

def embed(text: str) -> list[float]:
    """Ubah teks menjadi vector float via DeepInfra API."""
    response = embed_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding

# ----------------------------------------------
# 3. Load hospital_data.json
# ----------------------------------------------
with open("hospital_data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# ----------------------------------------------
# 4. Fungsi bantu: buat index + bulk insert
# ----------------------------------------------
def recreate_index(index_name: str, mapping: dict):
    if client.indices.exists(index=index_name):
        client.indices.delete(index=index_name)
        print(f"  Index lama '{index_name}' dihapus")
    client.indices.create(index=index_name, body=mapping)
    print(f"  Index '{index_name}' dibuat")

def bulk_insert(index_name: str, actions: list):
    success, errors = helpers.bulk(client, actions, raise_on_error=False)
    print(f"  {success} dokumen -> '{index_name}'")
    if errors:
        print(f"  {len(errors)} error:", errors[:2])

# ----------------------------------------------------------------------
# 5. Tiap index: definisikan teks yang akan di-embed, buat mapping,
#    lalu generate vector per dokumen
# ----------------------------------------------------------------------

# -- 5a. DEPARTMENTS ---------------------------------------------------
print("\n-- DEPARTMENTS --")
recreate_index("departments", {
    "settings": {"index": {"knn": True}},
    "mappings": {
        "properties": {
            "nama_departemen": {"type": "keyword"},
            "embedding": {
                "type": "knn_vector",
                "dimension": VECTOR_DIM,
                "method": {"name": "hnsw", "space_type": "cosinesimil",
                           "engine": "lucene"},
            },
        }
    },
})
actions = []
for rec in tqdm(data["departments"], desc="  embed"):
    text = f"Departemen rumah sakit: {rec['nama_departemen']}"
    actions.append({
        "_index": "departments",
        "_id": rec["_id"],
        "_source": {"nama_departemen": rec["nama_departemen"], "embedding": embed(text)},
    })
bulk_insert("departments", actions)

# -- 5b. MEDICAL_TEAMS -------------------------------------------------
print("\n-- MEDICAL_TEAMS --")
recreate_index("medical_teams", {
    "settings": {"index": {"knn": True}},
    "mappings": {
        "properties": {
            "nama_tim": {"type": "keyword"},
            "embedding": {
                "type": "knn_vector",
                "dimension": VECTOR_DIM,
                "method": {"name": "hnsw", "space_type": "cosinesimil",
                           "engine": "lucene"},
            },
        }
    },
})
actions = []
for rec in tqdm(data["medical_teams"], desc="  embed"):
    text = f"Tim medis: {rec['nama_tim']}"
    actions.append({
        "_index": "medical_teams",
        "_id": rec["_id"],
        "_source": {"nama_tim": rec["nama_tim"], "embedding": embed(text)},
    })
bulk_insert("medical_teams", actions)

# -- 5c. DOCTORS -------------------------------------------------------
print("\n-- DOCTORS --")

# Buat lookup cepat untuk nama departemen & tim
dept_lookup = {d["_id"]: d["nama_departemen"] for d in data["departments"]}
team_lookup = {t["_id"]: t["nama_tim"] for t in data["medical_teams"]}

recreate_index("doctors", {
    "settings": {"index": {"knn": True}},
    "mappings": {
        "properties": {
            "nama_dokter":   {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "department_id": {"type": "integer"},
            "team_id":       {"type": "integer"},
            "nama_departemen": {"type": "keyword"},   # denormalized
            "nama_tim":        {"type": "keyword"},   # denormalized
            "embedding": {
                "type": "knn_vector",
                "dimension": VECTOR_DIM,
                "method": {"name": "hnsw", "space_type": "cosinesimil",
                           "engine": "lucene"},
            },
        }
    },
})
actions = []
for rec in tqdm(data["doctors"], desc="  embed"):
    dept_name = dept_lookup.get(rec["department_id"], "")
    team_name = team_lookup.get(rec["team_id"], "")
    text = (f"Dokter bernama {rec['nama_dokter']} bekerja di departemen "
            f"{dept_name} dan tergabung dalam {team_name}.")
    actions.append({
        "_index": "doctors",
        "_id": rec["_id"],
        "_source": {
            "nama_dokter":     rec["nama_dokter"],
            "department_id":   rec["department_id"],
            "team_id":         rec["team_id"],
            "nama_departemen": dept_name,
            "nama_tim":        team_name,
            "embedding":       embed(text),
        },
    })
bulk_insert("doctors", actions)

# -- 5d. PATIENTS ------------------------------------------------------
print("\n-- PATIENTS --")
recreate_index("patients", {
    "settings": {"index": {"knn": True}},
    "mappings": {
        "properties": {
            "nama_pasien": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "kategori":    {"type": "keyword"},
            "embedding": {
                "type": "knn_vector",
                "dimension": VECTOR_DIM,
                "method": {"name": "hnsw", "space_type": "cosinesimil",
                           "engine": "lucene"},
            },
        }
    },
})
actions = []
for rec in tqdm(data["patients"], desc="  embed"):
    text = f"Pasien bernama {rec['nama_pasien']} dengan kategori {rec['kategori']}."
    actions.append({
        "_index": "patients",
        "_id": rec["_id"],
        "_source": {
            "nama_pasien": rec["nama_pasien"],
            "kategori":    rec["kategori"],
            "embedding":   embed(text),
        },
    })
bulk_insert("patients", actions)

# -- 5e. PATIENT_TREATMENTS --------------------------------------------
print("\n-- PATIENT_TREATMENTS --")

# Lookup nama pasien untuk denormalisasi
patient_lookup = {p["_id"]: p for p in data["patients"]}

recreate_index("patient_treatments", {
    "settings": {"index": {"knn": True}},
    "mappings": {
        "properties": {
            "patient_id":      {"type": "integer"},
            "team_id":         {"type": "integer"},
            "tanggal_operasi": {"type": "date"},
            "nama_pasien":     {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "nama_tim":        {"type": "keyword"},
            "embedding": {
                "type": "knn_vector",
                "dimension": VECTOR_DIM,
                "method": {"name": "hnsw", "space_type": "cosinesimil",
                           "engine": "lucene"},
            },
        }
    },
})
actions = []
for rec in tqdm(data["patient_treatments"], desc="  embed"):
    pasien  = patient_lookup.get(rec["patient_id"], {})
    tim     = team_lookup.get(rec["team_id"], "")
    text = (f"Pasien {pasien.get('nama_pasien','?')} menjalani operasi "
            f"oleh {tim} pada tanggal {rec['tanggal_operasi']}.")
    actions.append({
        "_index": "patient_treatments",
        "_id": rec["_id"],
        "_source": {
            "patient_id":      rec["patient_id"],
            "team_id":         rec["team_id"],
            "tanggal_operasi": rec["tanggal_operasi"],
            "nama_pasien":     pasien.get("nama_pasien", ""),
            "nama_tim":        tim,
            "embedding":       embed(text),
        },
    })
bulk_insert("patient_treatments", actions)

# -- 5f. BILLINGS ------------------------------------------------------
print("\n-- BILLINGS --")
recreate_index("billings", {
    "settings": {"index": {"knn": True}},
    "mappings": {
        "properties": {
            "treatment_id":      {"type": "integer"},
            "total_biaya":       {"type": "long"},
            "metode_pembayaran": {"type": "keyword"},
            "sub_metode":        {"type": "keyword"},
            "status_pembayaran": {"type": "keyword"},
            "embedding": {
                "type": "knn_vector",
                "dimension": VECTOR_DIM,
                "method": {"name": "hnsw", "space_type": "cosinesimil",
                           "engine": "lucene"},
            },
        }
    },
})
actions = []
for rec in tqdm(data["billings"], desc="  embed"):
    text = (f"Tagihan sebesar Rp {rec['total_biaya']:,} dengan metode "
            f"{rec['metode_pembayaran']} ({rec['sub_metode']}), "
            f"status: {rec['status_pembayaran']}.")
    actions.append({
        "_index": "billings",
        "_id": rec["_id"],
        "_source": {
            "treatment_id":      rec["treatment_id"],
            "total_biaya":       rec["total_biaya"],
            "metode_pembayaran": rec["metode_pembayaran"],
            "sub_metode":        rec["sub_metode"],
            "status_pembayaran": rec["status_pembayaran"],
            "embedding":         embed(text),
        },
    })
bulk_insert("billings", actions)

# -- 5g. BILLING_ITEMS -------------------------------------------------
print("\n-- BILLING_ITEMS --")
recreate_index("billing_items", {
    "settings": {"index": {"knn": True}},
    "mappings": {
        "properties": {
            "billing_id":              {"type": "integer"},
            "deskripsi":               {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "biaya":                   {"type": "long"},
            "is_covered_by_insurance": {"type": "integer"},
            "embedding": {
                "type": "knn_vector",
                "dimension": VECTOR_DIM,
                "method": {"name": "hnsw", "space_type": "cosinesimil",
                           "engine": "lucene"},
            },
        }
    },
})
actions = []
for rec in tqdm(data["billing_items"], desc="  embed"):
    covered = "ditanggung asuransi" if rec["is_covered_by_insurance"] else "tidak ditanggung asuransi"
    text = (f"Item tagihan: {rec['deskripsi']}, biaya Rp {rec['biaya']:,}, "
            f"{covered}.")
    actions.append({
        "_index": "billing_items",
        "_id": rec["_id"],
        "_source": {
            "billing_id":              rec["billing_id"],
            "deskripsi":               rec["deskripsi"],
            "biaya":                   rec["biaya"],
            "is_covered_by_insurance": rec["is_covered_by_insurance"],
            "embedding":               embed(text),
        },
    })
bulk_insert("billing_items", actions)

# ----------------------------------------------
# 6. Verifikasi akhir
# ----------------------------------------------
print("\n-- VERIFIKASI --")
for idx in ["departments","medical_teams","doctors","patients",
            "patient_treatments","billings","billing_items"]:
    count = client.count(index=idx)["count"]
    print(f"  {idx:25s}: {count} dokumen")

print("\nSelesai! Semua data + embedding sudah masuk OpenSearch.")
