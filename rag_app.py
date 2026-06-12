"""
OpenSearch Question Answering System — Diabetes Readmission
===========================================================
Requires: pip install gradio opensearch-py openai python-dotenv
Run: python rag_app.py
"""

import os
import re
from typing import Any

import gradio as gr
from dotenv import load_dotenv
from openai import OpenAI
from opensearchpy import OpenSearch

load_dotenv()

DEEPINFRA_API_TOKEN = os.getenv("DEEPINFRA_API_TOKEN")
DEEPINFRA_API_URL = os.getenv("DEEPINFRA_API_URL")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")
MODEL = os.getenv("MODEL")

INDEX_NAME = "diabetes_encounters"
VECTOR_DIM = 768
TOP_K_TOTAL = 10

SYSTEM_PROMPT = (
    "Kamu adalah asisten analisis readmission pasien diabetes. "
    "Jawab pertanyaan pengguna berdasarkan konteks dokumen pasien dan statistik dari OpenSearch. "
    "Jika pertanyaan meminta angka, gunakan hasil agregasi OpenSearch. "
    "Jika informasi tidak tersedia dalam konteks, katakan bahwa data tidak tersedia. "
    "Gunakan Bahasa Indonesia yang jelas, ringkas, dan sertakan angka penting jika tersedia."
)

os_client = OpenSearch(
    hosts=[{
        "host": os.getenv("OPENSEARCH_HOST", "localhost"),
        "port": int(os.getenv("OPENSEARCH_PORT", "9200")),
    }],
    http_auth=(
        os.getenv("OPENSEARCH_USER", "admin"),
        os.getenv("OPENSEARCH_PASSWORD", "YourStrongPassword123!"),
    ),
    use_ssl=os.getenv("OPENSEARCH_USE_SSL", "true").lower() == "true",
    verify_certs=False,
    ssl_assert_hostname=False,
    ssl_show_warn=False,
)

ai_client = OpenAI(
    api_key=DEEPINFRA_API_TOKEN,
    base_url=DEEPINFRA_API_URL,
)


def embed(text: str) -> list[float]:
    resp = ai_client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return resp.data[0].embedding


def format_bool(value: Any) -> str:
    return "Ya" if value is True else "Tidak" if value is False else str(value)


def build_filters(query: str, include_readmission: bool = True) -> list[dict]:
    q = query.lower()
    filters = []

    if include_readmission:
        if "<30" in q or "kurang dari 30" in q or "di bawah 30" in q:
            filters.append({"term": {"readmission_status": "<30"}})
        elif ">30" in q or "lebih dari 30" in q:
            filters.append({"term": {"readmission_status": ">30"}})
        elif re.search(r"\bno\b", q) or "tidak readmitted" in q or "tidak kembali" in q:
            filters.append({"term": {"readmission_status": "NO"}})

    age_match = re.search(r"(\d{1,2})\s*[- sampai]+\s*(\d{1,3})", q)
    if age_match:
        filters.append({"term": {"age": f"[{age_match.group(1)}-{age_match.group(2)})"}})

    if "high risk" in q or "risiko tinggi" in q:
        filters.append({"term": {"high_risk_flag": True}})

    if "diabetesmed yes" in q or "diabetes med yes" in q or "obat diabetes" in q:
        filters.append({"term": {"diabetesMed": "Yes"}})
    elif "diabetesmed no" in q or "diabetes med no" in q:
        filters.append({"term": {"diabetesMed": "No"}})

    diagnosis_aliases = {
        "diabetes": "Diabetes",
        "circulatory": "Circulatory",
        "sirkulasi": "Circulatory",
        "jantung": "Circulatory",
        "respiratory": "Respiratory",
        "pernapasan": "Respiratory",
        "digestive": "Digestive",
        "pencernaan": "Digestive",
        "genitourinary": "Genitourinary",
        "musculoskeletal": "Musculoskeletal",
        "neoplasms": "Neoplasms",
        "injury": "Injury",
        "cedera": "Injury",
    }
    for token, group in diagnosis_aliases.items():
        if token in q:
            filters.append({"term": {"diagnosis_group": group}})
            break

    return filters


def retrieve_documents(query: str) -> list[dict]:
    vec = embed(query)
    filters = build_filters(query)
    knn_query: dict[str, Any] = {
        "knn": {
            "embedding": {
                "vector": vec,
                "k": TOP_K_TOTAL,
            }
        }
    }

    if filters:
        search_query = {
            "bool": {
                "must": [knn_query],
                "filter": filters,
            }
        }
    else:
        search_query = knn_query

    resp = os_client.search(
        index=INDEX_NAME,
        body={
            "size": TOP_K_TOTAL,
            "query": search_query,
            "_source": {"excludes": ["embedding"]},
        },
    )

    return [
        {
            "score": hit["_score"],
            "id": hit["_id"],
            "data": hit["_source"],
        }
        for hit in resp["hits"]["hits"]
    ]


def get_readmission_stats(query: str) -> dict:
    filters = build_filters(query, include_readmission=False)
    body = {
        "size": 0,
        "query": {"bool": {"filter": filters}} if filters else {"match_all": {}},
        "aggs": {
            "readmission_status": {"terms": {"field": "readmission_status", "size": 5}},
            "age_distribution": {"terms": {"field": "age", "size": 10}},
            "diagnosis_distribution": {"terms": {"field": "diagnosis_group", "size": 10}},
            "diabetes_med_distribution": {"terms": {"field": "diabetesMed", "size": 5}},
            "medication_change_distribution": {"terms": {"field": "change", "size": 5}},
            "high_risk": {"terms": {"field": "high_risk_flag", "size": 2}},
            "early_readmission_by_diagnosis": {
                "filter": {"term": {"readmission_status": "<30"}},
                "aggs": {
                    "groups": {"terms": {"field": "diagnosis_group", "size": 10}}
                },
            },
            "early_readmission_by_age": {
                "filter": {"term": {"readmission_status": "<30"}},
                "aggs": {
                    "ages": {"terms": {"field": "age", "size": 10}}
                },
            },
            "early_readmission_by_specialty": {
                "filter": {"term": {"readmission_status": "<30"}},
                "aggs": {
                    "specialties": {"terms": {"field": "medical_specialty", "size": 10}}
                },
            },
            "early_readmission_count": {"filter": {"term": {"readmission_status": "<30"}}},
            "readmitted_count": {"filter": {"terms": {"readmission_status": ["<30", ">30"]}}},
        },
    }
    return os_client.search(index=INDEX_NAME, body=body)


def buckets_to_lines(title: str, buckets: list[dict]) -> list[str]:
    lines = [title]
    if not buckets:
        lines.append("  (tidak ada data)")
        return lines
    for bucket in buckets:
        lines.append(f"  - {bucket['key']}: {bucket['doc_count']}")
    return lines


def format_stats(stats: dict) -> str:
    total = stats["hits"]["total"]["value"] if isinstance(stats["hits"]["total"], dict) else stats["hits"]["total"]
    aggs = stats["aggregations"]
    readmitted = aggs["readmitted_count"]["doc_count"]
    early = aggs["early_readmission_count"]["doc_count"]
    readmission_rate = (readmitted / total * 100) if total else 0
    early_rate = (early / total * 100) if total else 0

    lines = [
        "STATISTIK OPENSEARCH",
        f"Total encounter sesuai filter: {total}",
        f"Readmitted (<30 atau >30): {readmitted} ({readmission_rate:.2f}%)",
        f"Early readmission (<30): {early} ({early_rate:.2f}%)",
        "",
    ]
    lines.extend(buckets_to_lines("Distribusi readmission:", aggs["readmission_status"]["buckets"]))
    lines.append("")
    lines.extend(buckets_to_lines("Diagnosis group terbanyak:", aggs["diagnosis_distribution"]["buckets"]))
    lines.append("")
    lines.extend(buckets_to_lines("Diagnosis group dengan readmission <30:", aggs["early_readmission_by_diagnosis"]["groups"]["buckets"]))
    lines.append("")
    lines.extend(buckets_to_lines("Kelompok umur dengan readmission <30:", aggs["early_readmission_by_age"]["ages"]["buckets"]))
    lines.append("")
    lines.extend(buckets_to_lines("Medical specialty dengan readmission <30:", aggs["early_readmission_by_specialty"]["specialties"]["buckets"]))
    lines.append("")
    lines.extend(buckets_to_lines("Distribusi diabetesMed:", aggs["diabetes_med_distribution"]["buckets"]))
    lines.append("")
    lines.extend(buckets_to_lines("Distribusi medication change:", aggs["medication_change_distribution"]["buckets"]))
    lines.append("")
    lines.extend(buckets_to_lines("High risk flag:", aggs["high_risk"]["buckets"]))
    return "\n".join(lines)


def format_documents(results: list[dict]) -> str:
    if not results:
        return "(tidak ada dokumen pasien yang relevan)"

    parts = []
    for i, r in enumerate(results, 1):
        data = r["data"]
        parts.append(f"[{i}] ENCOUNTER {data.get('encounter_id')} (skor: {r['score']:.4f})")
        parts.append(f"  patient_nbr: {data.get('patient_nbr')}")
        parts.append(f"  age/gender/race: {data.get('age')} / {data.get('gender')} / {data.get('race')}")
        parts.append(f"  diagnosis_group: {data.get('diagnosis_group')} | diag_1: {data.get('diag_1')}")
        parts.append(f"  admission_type: {data.get('admission_type')}")
        parts.append(f"  discharge_disposition: {data.get('discharge_disposition')}")
        parts.append(f"  outpatient/emergency/inpatient: {data.get('number_outpatient')}/{data.get('number_emergency')}/{data.get('number_inpatient')}")
        parts.append(f"  diabetesMed/change: {data.get('diabetesMed')} / {data.get('change')}")
        parts.append(f"  readmission_status: {data.get('readmission_status')}")
        parts.append(f"  high_risk_flag: {format_bool(data.get('high_risk_flag'))}")
        parts.append("")
    return "\n".join(parts).strip()


def build_llm_context(stats_text: str, docs_text: str) -> str:
    return (
        "Berikut adalah statistik agregasi dari OpenSearch:\n"
        f"{stats_text}\n\n"
        "Berikut adalah dokumen encounter pasien yang relevan dari OpenSearch:\n"
        f"{docs_text}"
    )


def respond(message: str, chat_history: list):
    if not message.strip():
        yield chat_history, "", ""
        return

    try:
        stats = get_readmission_stats(message)
        results = retrieve_documents(message)
    except Exception as exc:
        err = f"Terjadi error saat mengambil data dari OpenSearch: {exc}"
        new_history = chat_history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": err},
        ]
        yield new_history, err, ""
        return

    stats_text = format_stats(stats)
    docs_text = format_documents(results)
    ctx_disp = f"{stats_text}\n\nDOKUMEN RELEVAN\n{docs_text}"
    ctx_text = build_llm_context(stats_text, docs_text)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in chat_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({
        "role": "user",
        "content": f"{ctx_text}\n\nPertanyaan: {message}",
    })

    stream = ai_client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.2,
        stream=True,
    )

    partial = ""
    new_history = chat_history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": ""},
    ]
    yield new_history, ctx_disp, ""

    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        partial += delta
        new_history[-1]["content"] = partial
        yield new_history, ctx_disp, ""


with gr.Blocks(title="QA Readmission Diabetes") as demo:
    gr.Markdown("## QA System Analisis Readmission Rate Pasien Diabetes")
    gr.Markdown(
        f"Model: `{MODEL}` &nbsp;|&nbsp; "
        f"Embedding: `{EMBEDDING_MODEL}` &nbsp;|&nbsp; "
        "Database: OpenSearch (`diabetes_encounters`)"
    )

    chatbot = gr.Chatbot(label="Percakapan", height=560)
    with gr.Row():
        msg_box = gr.Textbox(
            placeholder="Contoh: Diagnosis apa yang memiliki readmission <30 paling tinggi?",
            show_label=False,
            scale=5,
            lines=1,
        )
        send_btn = gr.Button("Kirim", variant="primary", scale=1)
    clear_btn = gr.Button("Hapus Percakapan", size="sm")

    with gr.Accordion("Konteks dan statistik dari OpenSearch", open=False):
        ctx_box = gr.Textbox(
            label="Hasil retrieval dan agregasi",
            placeholder="Konteks dan statistik akan muncul setelah pertanyaan dikirim.",
            lines=20,
            max_lines=28,
            interactive=False,
        )

    send_btn.click(respond, inputs=[msg_box, chatbot], outputs=[chatbot, ctx_box, msg_box])
    msg_box.submit(respond, inputs=[msg_box, chatbot], outputs=[chatbot, ctx_box, msg_box])
    clear_btn.click(lambda: ([], "", ""), outputs=[chatbot, ctx_box, msg_box])

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", "7860")),
    )
