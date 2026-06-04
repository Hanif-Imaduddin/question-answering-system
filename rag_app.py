"""
RAG Question-Answering System — Hospital Data
=============================================
Requires: pip install gradio opensearch-py openai python-dotenv
Run: python rag_app.py
"""

import os
import gradio as gr
from dotenv import load_dotenv
from openai import OpenAI
from opensearchpy import OpenSearch

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
DEEPINFRA_API_TOKEN = os.getenv("DEEPINFRA_API_TOKEN")
DEEPINFRA_API_URL   = os.getenv("DEEPINFRA_API_URL")
EMBEDDING_MODEL     = os.getenv("EMBEDDING_MODEL")
MODEL               = os.getenv("MODEL")
VECTOR_DIM          = 768
TOP_K_PER_INDEX     = 3
TOP_K_TOTAL         = 10

INDICES = [
    "departments",
    "medical_teams",
    "doctors",
    "patients",
    "patient_treatments",
    "billings",
    "billing_items",
]

SYSTEM_PROMPT = (
    "Kamu adalah asisten data rumah sakit. "
    "Jawab pertanyaan pengguna berdasarkan data konteks yang diberikan. "
    "Jika informasi tidak ada dalam konteks, katakan bahwa data tidak tersedia. "
    "Gunakan Bahasa Indonesia yang jelas dan sopan."
)

# ── Clients ───────────────────────────────────────────────────────────────────
_os_host = os.getenv("OPENSEARCH_HOST", "localhost")
_os_port = int(os.getenv("OPENSEARCH_PORT", "9200"))
_os_user = os.getenv("OPENSEARCH_USER", "admin")
_os_pass = os.getenv("OPENSEARCH_PASSWORD", "YourStrongPassword123!")
_os_ssl  = os.getenv("OPENSEARCH_USE_SSL", "true").lower() == "true"

os_client = OpenSearch(
    hosts=[{"host": _os_host, "port": _os_port}],
    http_auth=(_os_user, _os_pass) if _os_ssl else None,
    use_ssl=_os_ssl,
    verify_certs=False,
    ssl_assert_hostname=False,
    ssl_show_warn=False,
)

ai_client = OpenAI(
    api_key=DEEPINFRA_API_TOKEN,
    base_url=DEEPINFRA_API_URL,
)

# ── Embedding ─────────────────────────────────────────────────────────────────
def embed(text: str) -> list[float]:
    resp = ai_client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return resp.data[0].embedding

# ── Retrieval ─────────────────────────────────────────────────────────────────
def retrieve(query: str) -> list[dict]:
    vec = embed(query)
    results = []
    for index in INDICES:
        try:
            resp = os_client.search(
                index=index,
                body={
                    "size": TOP_K_PER_INDEX,
                    "query": {
                        "knn": {
                            "embedding": {"vector": vec, "k": TOP_K_PER_INDEX}
                        }
                    },
                    "_source": {"excludes": ["embedding"]},
                },
            )
            for hit in resp["hits"]["hits"]:
                results.append({
                    "index": index,
                    "score": hit["_score"],
                    "id":    hit["_id"],
                    "data":  hit["_source"],
                })
        except Exception as exc:
            print(f"[retrieve] {index}: {exc}")

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:TOP_K_TOTAL]

# ── Format helpers ────────────────────────────────────────────────────────────
def _fmt_rupiah(v) -> str:
    try:
        return f"Rp {int(v):,}".replace(",", ".")
    except Exception:
        return str(v)

def format_context_display(results: list[dict]) -> str:
    if not results:
        return "(tidak ada data yang relevan)"
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(f"[{i}] {r['index'].upper()}  (skor: {r['score']:.4f})")
        for k, v in r["data"].items():
            if k in ("total_biaya", "biaya"):
                v = _fmt_rupiah(v)
            parts.append(f"  {k}: {v}")
        parts.append("")
    return "\n".join(parts).strip()

def build_llm_context(results: list[dict]) -> str:
    if not results:
        return "Tidak ada data relevan ditemukan."
    lines = ["Data dari database rumah sakit:"]
    for r in results:
        lines.append(f"\n[{r['index']}]")
        for k, v in r["data"].items():
            if k in ("total_biaya", "biaya"):
                v = _fmt_rupiah(v)
            lines.append(f"  {k}: {v}")
    return "\n".join(lines)

# ── Chat handler (streaming) ──────────────────────────────────────────────────
def respond(message: str, chat_history: list):
    if not message.strip():
        yield chat_history, "", ""
        return

    results  = retrieve(message)
    ctx_text = build_llm_context(results)
    ctx_disp = format_context_display(results)

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
        temperature=0.3,
        stream=True,
    )

    partial = ""
    new_history = chat_history + [
        {"role": "user",      "content": message},
        {"role": "assistant", "content": ""},
    ]
    yield new_history, ctx_disp, ""

    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        partial += delta
        new_history[-1]["content"] = partial
        yield new_history, ctx_disp, ""

# ── Gradio UI ─────────────────────────────────────────────────────────────────
with gr.Blocks(title="RAG Rumah Sakit") as demo:
    gr.Markdown("## Sistem Tanya Jawab Data Rumah Sakit")
    gr.Markdown(
        f"Model: `{MODEL}` &nbsp;|&nbsp; "
        f"Embedding: `{EMBEDDING_MODEL}` &nbsp;|&nbsp; "
        "Database: OpenSearch"
    )

    chatbot = gr.Chatbot(
        label="Percakapan",
        height=560,
    )
    with gr.Row():
        msg_box = gr.Textbox(
            placeholder="Ketik pertanyaan Anda...",
            show_label=False,
            scale=5,
            lines=1,
        )
        send_btn = gr.Button("Kirim", variant="primary", scale=1)
    clear_btn = gr.Button("Hapus Percakapan", size="sm")

    with gr.Accordion("Konteks dari OpenSearch", open=False):
        ctx_box = gr.Textbox(
            label="Dokumen relevan hasil retrieval",
            placeholder="Konteks akan muncul setelah pertanyaan dikirim.",
            lines=16,
            max_lines=20,
            interactive=False,
        )

    send_btn.click(
        respond,
        inputs=[msg_box, chatbot],
        outputs=[chatbot, ctx_box, msg_box],
    )
    msg_box.submit(
        respond,
        inputs=[msg_box, chatbot],
        outputs=[chatbot, ctx_box, msg_box],
    )
    clear_btn.click(
        lambda: ([], "", ""),
        outputs=[chatbot, ctx_box, msg_box],
    )

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", "7860")),
    )
