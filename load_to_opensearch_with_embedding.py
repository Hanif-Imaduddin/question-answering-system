"""
Load Diabetes Readmission Data ke OpenSearch + Vector Embedding
===============================================================
Dataset:
    diabetic_data.csv
    IDS_mapping.csv

Konsep:
    1 encounter = 1 dokumen OpenSearch

Jalankan:
    python load_to_opensearch_with_embedding.py

Opsional:
    DIABETES_LOAD_LIMIT=10000 python load_to_opensearch_with_embedding.py
    Jika DIABETES_LOAD_LIMIT kosong/0, seluruh data akan diproses.
"""

import csv
import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from opensearchpy import OpenSearch, helpers
from tqdm import tqdm

load_dotenv()

INDEX_NAME = "diabetes_encounters"
VECTOR_DIM = 768
DATA_PATH = os.getenv("DIABETES_DATA_PATH", "diabetic_data.csv")
MAPPING_PATH = os.getenv("DIABETES_MAPPING_PATH", "IDS_mapping.csv")
LOAD_LIMIT = int(os.getenv("DIABETES_LOAD_LIMIT", "0") or "0")
BULK_CHUNK_SIZE = int(os.getenv("BULK_CHUNK_SIZE", "250"))


def clean_value(value: Any, default: str = "Unknown") -> str:
    if value is None:
        return default
    text = str(value).strip()
    if text in ("", "?"):
        return default
    return text


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default


def load_id_mappings(path: str) -> dict[str, dict[str, str]]:
    sections = {
        "admission_type_id": {},
        "discharge_disposition_id": {},
        "admission_source_id": {},
    }
    current_section = None

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or not row[0].strip():
                continue

            key = row[0].strip()
            if key in sections:
                current_section = key
                continue

            if key == "description" or current_section is None:
                continue

            if len(row) >= 2:
                sections[current_section][key] = clean_value(row[1], "Unknown")

    return sections


def diagnosis_group(code: str) -> str:
    code = clean_value(code, "Unknown")
    if code == "Unknown":
        return "Unknown"
    if code.startswith(("V", "E")):
        return "Supplemental"

    try:
        num = float(code)
    except Exception:
        return "Other"

    if 250 <= num < 251:
        return "Diabetes"
    if (390 <= num <= 459) or int(num) == 785:
        return "Circulatory"
    if (460 <= num <= 519) or int(num) == 786:
        return "Respiratory"
    if (520 <= num <= 579) or int(num) == 787:
        return "Digestive"
    if 580 <= num <= 629 or int(num) == 788:
        return "Genitourinary"
    if 140 <= num <= 239:
        return "Neoplasms"
    if 710 <= num <= 739:
        return "Musculoskeletal"
    if 800 <= num <= 999:
        return "Injury"
    return "Other"


def build_document(row: dict[str, str], mappings: dict[str, dict[str, str]]) -> dict:
    admission_type = mappings["admission_type_id"].get(row["admission_type_id"], "Unknown")
    discharge_disposition = mappings["discharge_disposition_id"].get(
        row["discharge_disposition_id"], "Unknown"
    )
    admission_source = mappings["admission_source_id"].get(row["admission_source_id"], "Unknown")

    readmission_status = clean_value(row["readmitted"], "NO")
    primary_group = diagnosis_group(row["diag_1"])
    secondary_group = diagnosis_group(row["diag_2"])
    tertiary_group = diagnosis_group(row["diag_3"])

    number_inpatient = safe_int(row["number_inpatient"])
    number_outpatient = safe_int(row["number_outpatient"])
    number_emergency = safe_int(row["number_emergency"])
    time_in_hospital = safe_int(row["time_in_hospital"])
    num_medications = safe_int(row["num_medications"])

    high_risk_flag = (
        readmission_status == "<30"
        or number_inpatient >= 2
        or number_emergency >= 2
        or time_in_hospital >= 7
        or num_medications >= 20
    )

    patient_summary_text = (
        f"Encounter {row['encounter_id']} pasien diabetes dengan gender "
        f"{clean_value(row['gender'])}, ras {clean_value(row['race'])}, usia {clean_value(row['age'])}. "
        f"Admission type: {admission_type}; admission source: {admission_source}; "
        f"discharge disposition: {discharge_disposition}; medical specialty: "
        f"{clean_value(row['medical_specialty'])}. Diagnosis utama {clean_value(row['diag_1'])} "
        f"({primary_group}), diagnosis kedua {clean_value(row['diag_2'])} ({secondary_group}), "
        f"diagnosis ketiga {clean_value(row['diag_3'])} ({tertiary_group}). "
        f"Riwayat kunjungan outpatient {number_outpatient}, emergency {number_emergency}, "
        f"inpatient {number_inpatient}. Lama rawat {time_in_hospital} hari, jumlah obat "
        f"{num_medications}, medication change {clean_value(row['change'])}, diabetesMed "
        f"{clean_value(row['diabetesMed'])}. Status readmission: {readmission_status}. "
        f"High risk flag: {high_risk_flag}."
    )

    return {
        "encounter_id": clean_value(row["encounter_id"]),
        "patient_nbr": clean_value(row["patient_nbr"]),
        "race": clean_value(row["race"]),
        "gender": clean_value(row["gender"]),
        "age": clean_value(row["age"]),
        "weight": clean_value(row["weight"]),
        "admission_type_id": safe_int(row["admission_type_id"]),
        "admission_type": admission_type,
        "discharge_disposition_id": safe_int(row["discharge_disposition_id"]),
        "discharge_disposition": discharge_disposition,
        "admission_source_id": safe_int(row["admission_source_id"]),
        "admission_source": admission_source,
        "time_in_hospital": time_in_hospital,
        "payer_code": clean_value(row["payer_code"]),
        "medical_specialty": clean_value(row["medical_specialty"]),
        "num_lab_procedures": safe_int(row["num_lab_procedures"]),
        "num_procedures": safe_int(row["num_procedures"]),
        "num_medications": num_medications,
        "number_outpatient": number_outpatient,
        "number_emergency": number_emergency,
        "number_inpatient": number_inpatient,
        "diag_1": clean_value(row["diag_1"]),
        "diag_2": clean_value(row["diag_2"]),
        "diag_3": clean_value(row["diag_3"]),
        "diagnosis_group": primary_group,
        "diagnosis_group_2": secondary_group,
        "diagnosis_group_3": tertiary_group,
        "number_diagnoses": safe_int(row["number_diagnoses"]),
        "max_glu_serum": clean_value(row["max_glu_serum"]),
        "A1Cresult": clean_value(row["A1Cresult"]),
        "change": clean_value(row["change"]),
        "diabetesMed": clean_value(row["diabetesMed"]),
        "readmitted": readmission_status,
        "readmission_status": readmission_status,
        "readmitted_binary": readmission_status in ("<30", ">30"),
        "early_readmission_flag": readmission_status == "<30",
        "high_risk_flag": high_risk_flag,
        "patient_summary_text": patient_summary_text,
    }


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

embed_client = OpenAI(
    api_key=os.getenv("DEEPINFRA_API_TOKEN"),
    base_url=os.getenv("DEEPINFRA_API_URL"),
)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")
print(f"Embedding model: {EMBEDDING_MODEL} ({VECTOR_DIM} dim)")


def embed(text: str) -> list[float]:
    response = embed_client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def recreate_index():
    if client.indices.exists(index=INDEX_NAME):
        client.indices.delete(index=INDEX_NAME)
        print(f"Index lama '{INDEX_NAME}' dihapus")

    mapping = {
        "settings": {"index": {"knn": True}},
        "mappings": {
            "properties": {
                "encounter_id": {"type": "keyword"},
                "patient_nbr": {"type": "keyword"},
                "race": {"type": "keyword"},
                "gender": {"type": "keyword"},
                "age": {"type": "keyword"},
                "weight": {"type": "keyword"},
                "admission_type_id": {"type": "integer"},
                "admission_type": {"type": "keyword"},
                "discharge_disposition_id": {"type": "integer"},
                "discharge_disposition": {"type": "keyword"},
                "admission_source_id": {"type": "integer"},
                "admission_source": {"type": "keyword"},
                "time_in_hospital": {"type": "integer"},
                "payer_code": {"type": "keyword"},
                "medical_specialty": {"type": "keyword"},
                "num_lab_procedures": {"type": "integer"},
                "num_procedures": {"type": "integer"},
                "num_medications": {"type": "integer"},
                "number_outpatient": {"type": "integer"},
                "number_emergency": {"type": "integer"},
                "number_inpatient": {"type": "integer"},
                "diag_1": {"type": "keyword"},
                "diag_2": {"type": "keyword"},
                "diag_3": {"type": "keyword"},
                "diagnosis_group": {"type": "keyword"},
                "diagnosis_group_2": {"type": "keyword"},
                "diagnosis_group_3": {"type": "keyword"},
                "number_diagnoses": {"type": "integer"},
                "max_glu_serum": {"type": "keyword"},
                "A1Cresult": {"type": "keyword"},
                "change": {"type": "keyword"},
                "diabetesMed": {"type": "keyword"},
                "readmitted": {"type": "keyword"},
                "readmission_status": {"type": "keyword"},
                "readmitted_binary": {"type": "boolean"},
                "early_readmission_flag": {"type": "boolean"},
                "high_risk_flag": {"type": "boolean"},
                "patient_summary_text": {"type": "text"},
                "embedding": {
                    "type": "knn_vector",
                    "dimension": VECTOR_DIM,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "lucene",
                    },
                },
            }
        },
    }
    client.indices.create(index=INDEX_NAME, body=mapping)
    print(f"Index '{INDEX_NAME}' dibuat")


def iter_rows():
    with open(DATA_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 1):
            if LOAD_LIMIT and i > LOAD_LIMIT:
                break
            yield row


def main():
    mappings = load_id_mappings(MAPPING_PATH)
    recreate_index()

    rows = list(iter_rows())
    print(f"Memproses {len(rows)} encounter dari {DATA_PATH}")

    actions = []
    for row in tqdm(rows, desc="Embedding encounter"):
        doc = build_document(row, mappings)
        doc["embedding"] = embed(doc["patient_summary_text"])
        actions.append({
            "_index": INDEX_NAME,
            "_id": doc["encounter_id"],
            "_source": doc,
        })

        if len(actions) >= BULK_CHUNK_SIZE:
            success, errors = helpers.bulk(client, actions, raise_on_error=False)
            if errors:
                print(f"  {len(errors)} error bulk:", errors[:2])
            actions.clear()

    if actions:
        success, errors = helpers.bulk(client, actions, raise_on_error=False)
        if errors:
            print(f"  {len(errors)} error bulk:", errors[:2])

    count = client.count(index=INDEX_NAME)["count"]
    print(f"Selesai. Total dokumen di '{INDEX_NAME}': {count}")


if __name__ == "__main__":
    main()
