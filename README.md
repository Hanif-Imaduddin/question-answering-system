# OpenSearch QA System untuk Analisis Readmission Pasien Diabetes

Project ini mengembangkan **Question Answering System berbasis OpenSearch** untuk analytic case:

> Analisis Readmission Rate Pasien Diabetes

Dataset yang digunakan:

- `diabetic_data.csv`
- `IDS_mapping.csv`

Sumber dataset: **Diabetes 130-US Hospitals for Years 1999-2008** dari UCI Machine Learning Repository.

## Konsep Sistem

Data pasien diabetes di-index ke OpenSearch dengan konsep:

```text
1 encounter = 1 document
```

Index utama:

```text
diabetes_encounters
```

Setiap dokumen berisi data encounter pasien, field turunan, dan embedding vector dari `patient_summary_text`.

Field penting:

- `age`
- `gender`
- `admission_type`
- `discharge_disposition`
- `diagnosis_group`
- `number_inpatient`
- `number_outpatient`
- `number_emergency`
- `change`
- `diabetesMed`
- `readmission_status`
- `high_risk_flag`
- `patient_summary_text`
- `embedding`

Field turunan:

- `readmission_status`: nilai `<30`, `>30`, atau `NO`
- `readmitted_binary`: true jika `<30` atau `>30`
- `early_readmission_flag`: true jika `<30`
- `high_risk_flag`: flag risiko berdasarkan readmission cepat, riwayat inpatient/emergency, lama rawat, dan jumlah obat
- `diagnosis_group`: pengelompokan diagnosis dari kode ICD
- `patient_summary_text`: teks ringkasan pasien yang dipakai untuk embedding

## Fitur

- Load dataset diabetes ke OpenSearch.
- Decode ID admission/discharge/source menggunakan `IDS_mapping.csv`.
- Membuat field turunan untuk analisis readmission.
- Menyimpan embedding vector untuk semantic search.
- QA chatbot berbasis Gradio.
- Retrieval dokumen pasien relevan dari OpenSearch.
- Agregasi statistik OpenSearch untuk readmission rate, diagnosis group, age group, medication, medical specialty, dan high risk flag.
- Ringkasan jawaban menggunakan LLM melalui API DeepInfra/OpenAI-compatible.

## Struktur File

| File | Fungsi |
| --- | --- |
| `diabetic_data.csv` | Dataset utama diabetes readmission. |
| `IDS_mapping.csv` | Mapping ID admission type, discharge disposition, dan admission source. |
| `load_to_opensearch_with_embedding.py` | Membuat index `diabetes_encounters`, preprocessing data, membuat embedding, dan load data ke OpenSearch. |
| `export_opensearch.py` | Mengekspor index OpenSearch ke `opensearch_dump.json`. |
| `import_to_opensearch.py` | Mengimpor dump OpenSearch saat aplikasi dijalankan via Docker/deployment. |
| `rag_app.py` | Aplikasi QA/RAG dan GUI Gradio. |
| `docker-compose.yml` | Menjalankan OpenSearch dan aplikasi secara lokal. |
| `.env.example` | Contoh konfigurasi environment. |

## Environment Variable

Buat file `.env`:

```bash
cp .env.example .env
```

Isi konfigurasi:

```env
DEEPINFRA_API_TOKEN=isi_token_deepinfra_anda
DEEPINFRA_API_URL=https://api.deepinfra.com/v1/openai
EMBEDDING_MODEL=google/embeddinggemma-300m
MODEL=google/gemma-3-12b-it

OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200
OPENSEARCH_USER=admin
OPENSEARCH_PASSWORD=YourStrongPassword123!
OPENSEARCH_USE_SSL=true

PORT=7860

DIABETES_DATA_PATH=diabetic_data.csv
DIABETES_MAPPING_PATH=IDS_mapping.csv
DIABETES_LOAD_LIMIT=0
BULK_CHUNK_SIZE=250
```

Catatan:

- `DIABETES_LOAD_LIMIT=0` berarti memproses seluruh dataset.
- Untuk testing awal, gunakan nilai kecil seperti `DIABETES_LOAD_LIMIT=5000`.
- Pastikan model embedding menghasilkan vector berdimensi `768`.

## Step-by-Step Menjalankan Lokal

### 1. Jalankan OpenSearch

```bash
docker compose up opensearch
```

OpenSearch tersedia di:

```text
https://localhost:9200
```

Username/password:

```text
admin / YourStrongPassword123!
```

### 2. Install dependency Python

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Siapkan `.env`

```bash
cp .env.example .env
```

Isi API key DeepInfra dan model yang digunakan.

### 4. Load data diabetes ke OpenSearch

Untuk testing awal:

```bash
$env:DIABETES_LOAD_LIMIT="5000"
python load_to_opensearch_with_embedding.py
```

Untuk seluruh dataset:

```bash
$env:DIABETES_LOAD_LIMIT="0"
python load_to_opensearch_with_embedding.py
```

Script ini akan membuat index:

```text
diabetes_encounters
```

### 5. Export dump OpenSearch

```bash
python export_opensearch.py
```

Hasilnya:

```text
opensearch_dump.json
```

File dump ini dibutuhkan untuk Docker/deployment agar data bisa di-import otomatis.

### 6. Jalankan QA app

```bash
python rag_app.py
```

Buka:

```text
http://localhost:7860
```

## Menjalankan dengan Docker Compose

Setelah `opensearch_dump.json` sudah dibuat dari dataset diabetes:

```bash
docker compose up --build
```

Docker akan menjalankan:

- OpenSearch
- Import data dari `opensearch_dump.json`
- QA app Gradio

Aplikasi tersedia di:

```text
http://localhost:7860
```

## Contoh Pertanyaan

```text
Berapa distribusi pasien berdasarkan status readmission?
```

```text
Berapa readmission rate keseluruhan?
```

```text
Diagnosis group apa yang paling banyak mengalami readmission kurang dari 30 hari?
```

```text
Kelompok umur mana yang paling sering mengalami readmission <30?
```

```text
Apakah pasien dengan diabetesMed Yes lebih sering mengalami readmission?
```

```text
Tampilkan contoh pasien high risk untuk readmission.
```

```text
Medical specialty apa yang memiliki early readmission paling banyak?
```

## Catatan Penting

`opensearch_dump.json` lama dari project rumah sakit dummy tidak cocok untuk versi diabetes ini. Setelah mengganti dataset, jalankan:

```bash
python load_to_opensearch_with_embedding.py
python export_opensearch.py
```

agar dump berisi index `diabetes_encounters`.
