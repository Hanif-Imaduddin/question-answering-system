# Question Answering System Rumah Sakit dengan OpenSearch

Project ini adalah implementasi tugas akhir untuk membangun **Question Answering System** di atas **OpenSearch** sebagai vector database. Studi kasus yang digunakan adalah data Rumah Sakit Sehat Selalu.

## Pilihan Pendekatan

Project ini mengambil **pilihan 1** dari deskripsi tugas:

> Mentransformasi semua data studi kasus Rumah Sakit Sehat Selalu ke dalam format OpenSearch, lalu membuat QA module di atas OpenSearch.

Data rumah sakit dibuat dalam format JSON, dimasukkan ke beberapa index OpenSearch, lalu setiap dokumen diberi vector embedding agar bisa dicari menggunakan semantic search / k-NN. Hasil pencarian dari OpenSearch dipakai sebagai konteks untuk LLM dalam menjawab pertanyaan pengguna.

## Fitur

- Generate data dummy Rumah Sakit Sehat Selalu.
- Load data ke OpenSearch dalam bentuk index terpisah.
- Menyimpan embedding vector di setiap dokumen.
- Retrieval menggunakan k-NN vector search OpenSearch.
- QA/RAG menggunakan model LLM melalui API DeepInfra yang kompatibel dengan OpenAI SDK.
- GUI berbasis Gradio.
- Bisa dijalankan lokal atau dengan Docker Compose.

## Struktur File

| File | Fungsi |
| --- | --- |
| `generate_hospital_data.py` | Membuat data dummy rumah sakit ke `hospital_data.json`. |
| `hospital_data.json` | Data mentah rumah sakit. |
| `load_to_opensearch_with_embedding.py` | Membuat index, membuat embedding, dan memasukkan data ke OpenSearch. |
| `export_opensearch.py` | Mengekspor index OpenSearch ke `opensearch_dump.json`. |
| `opensearch_dump.json` | Dump data OpenSearch yang sudah berisi embedding. |
| `import_to_opensearch.py` | Mengimpor dump ke OpenSearch. Dipakai saat Docker startup. |
| `rag_app.py` | Aplikasi QA/RAG dan GUI Gradio. |
| `Dockerfile` | Image Docker untuk aplikasi Gradio. |
| `docker-compose.yml` | Menjalankan OpenSearch dan aplikasi sekaligus. |
| `.env.example` | Contoh konfigurasi environment. |

## Data yang Digunakan

Dataset dummy berisi:

- 10 departments
- 20 medical teams
- 80 doctors
- 500 patients
- 1000 patient treatments
- 1000 billings
- 2999 billing items

Total data: 5609 records.

## Environment Variable

Buat file `.env` dari contoh:

```bash
cp .env.example .env
```

Lalu isi nilai berikut:

```env
DEEPINFRA_API_TOKEN=isi_token_deepinfra_anda
DEEPINFRA_API_URL=https://api.deepinfra.com/v1/openai
EMBEDDING_MODEL=google/embeddinggemma-300m
MODEL=meta-llama/Meta-Llama-3.1-8B-Instruct

OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200
OPENSEARCH_USER=admin
OPENSEARCH_PASSWORD=YourStrongPassword123!
OPENSEARCH_USE_SSL=true

PORT=7860
```

Catatan:

- Jangan commit file `.env`.
- Pastikan `EMBEDDING_MODEL` menghasilkan dimensi vector yang sama dengan `VECTOR_DIM` di script, yaitu `768`.

## Cara Menjalankan dengan Docker

Cara ini paling praktis untuk demo karena OpenSearch dan aplikasi dijalankan bersama.

### 1. Siapkan `.env`

```bash
cp .env.example .env
```

Isi `DEEPINFRA_API_TOKEN`, `DEEPINFRA_API_URL`, `EMBEDDING_MODEL`, dan `MODEL`.

### 2. Jalankan service

```bash
docker compose up --build
```

Docker Compose akan menjalankan:

- OpenSearch di `https://localhost:9200`
- Aplikasi Gradio di `http://localhost:7860`

Saat container aplikasi berjalan, `start.sh` akan menjalankan:

```bash
python import_to_opensearch.py
python rag_app.py
```

Script import akan memasukkan data dari `opensearch_dump.json` ke OpenSearch jika index belum berisi data.

### 3. Buka aplikasi

Buka browser:

```text
http://localhost:7860
```

### 4. Menghentikan service

```bash
docker compose down
```

Jika ingin menghapus data OpenSearch juga:

```bash
docker compose down -v
```

## Cara Menjalankan Lokal

Cara lokal cocok jika ingin debugging script Python satu per satu. OpenSearch tetap paling mudah dijalankan via Docker.

### 1. Jalankan OpenSearch saja

```bash
docker compose up opensearch
```

Tunggu sampai OpenSearch siap di:

```text
https://localhost:9200
```

Default user/password:

```text
admin / YourStrongPassword123!
```

### 2. Buat virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Siapkan `.env`

```bash
cp .env.example .env
```

Isi API token dan model.

### 4. Import data ke OpenSearch

Cara cepat, gunakan dump yang sudah ada:

```bash
python import_to_opensearch.py
```

Alternatif jika ingin membuat data dan embedding dari awal:

```bash
python generate_hospital_data.py
python load_to_opensearch_with_embedding.py
python export_opensearch.py
```

### 5. Jalankan aplikasi

```bash
python rag_app.py
```

Buka:

```text
http://localhost:7860
```

## Alur Sistem

1. User mengetik pertanyaan di GUI Gradio.
2. Pertanyaan diubah menjadi embedding.
3. Aplikasi mencari dokumen relevan ke beberapa index OpenSearch:
   - `departments`
   - `medical_teams`
   - `doctors`
   - `patients`
   - `patient_treatments`
   - `billings`
   - `billing_items`
4. OpenSearch mengembalikan dokumen dengan skor relevansi tertinggi.
5. Dokumen hasil retrieval disusun menjadi konteks.
6. LLM menjawab pertanyaan berdasarkan konteks tersebut.
7. GUI menampilkan jawaban dan konteks yang dipakai.

## Contoh Pertanyaan

- Siapa saja pasien yang termasuk kategori BPJS?
- Dokter siapa yang bekerja di departemen Anak?
- Berapa total biaya tagihan yang belum lunas?
- Pasien siapa yang menjalani operasi oleh Tim Jantung?
- Item tagihan apa saja yang ditanggung asuransi?
