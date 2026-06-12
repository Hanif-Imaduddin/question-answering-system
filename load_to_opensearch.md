# Load Data ke OpenSearch dengan Vector Embedding

Script `load_to_opensearch_with_embedding.py` membaca `hospital_data.json`, menghasilkan vector embedding untuk setiap dokumen, lalu menyimpannya ke 7 index di OpenSearch.

---

## 1. Koneksi ke OpenSearch

```python
client = OpenSearch(
    hosts=[{"host": "localhost", "port": 9200}],
    http_auth=("admin", "YourStrongPassword123!"),
    use_ssl=True,
    verify_certs=False,
)
```

Koneksi dibuat ke OpenSearch yang berjalan secara lokal. SSL diaktifkan tapi verifikasi sertifikat dimatikan karena menggunakan sertifikat self-signed.

---

## 2. Setup Embedding Client

```python
embed_client = OpenAI(
    api_key=DEEPINFRA_API_TOKEN,
    base_url=DEEPINFRA_API_URL,
)
VECTOR_DIM = 768
```

Embedding dihasilkan melalui DeepInfra API menggunakan OpenAI-compatible interface. Model yang dipakai menghasilkan vector 768 dimensi. Konfigurasi dibaca dari file `.env`.

```python
def embed(text: str) -> list[float]:
    response = embed_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding
```

Fungsi `embed()` menerima string teks dan mengembalikan list of float yang merepresentasikan makna semantik teks tersebut.

---

## 3. Load Data JSON

```python
with open("hospital_data.json", "r", encoding="utf-8") as f:
    data = json.load(f)
```

Seluruh data rumah sakit yang sudah digenerate sebelumnya dimuat ke memori sebagai dictionary Python.

---

## 4. Fungsi Bantu

```python
def recreate_index(index_name: str, mapping: dict):
    if client.indices.exists(index=index_name):
        client.indices.delete(index=index_name)
    client.indices.create(index=index_name, body=mapping)
```

Jika index sudah ada, index tersebut dihapus terlebih dahulu lalu dibuat ulang. Ini memastikan mapping selalu bersih saat script dijalankan ulang.

```python
def bulk_insert(index_name: str, actions: list):
    success, errors = helpers.bulk(client, actions, raise_on_error=False)
```

Dokumen dikirim ke OpenSearch secara bulk untuk efisiensi. Setiap dokumen yang sudah memiliki embedding dimasukkan dalam satu batch.

---

## 5. Proses per Index

Setiap index mengikuti pola yang sama: buat index dengan mapping KNN, generate teks kontekstual per dokumen, panggil `embed()`, lalu bulk insert.

### Mapping KNN

Semua index menggunakan konfigurasi berikut untuk field embedding:

```python
"embedding": {
    "type": "knn_vector",
    "dimension": VECTOR_DIM,
    "method": {
        "name": "hnsw",
        "space_type": "cosinesimil",
        "engine": "lucene"
    },
}
```

Algoritma HNSW (Hierarchical Navigable Small World) dipakai untuk approximate nearest neighbor search. `cosinesimil` mengukur kemiripan berdasarkan sudut antara dua vector, bukan jaraknya.

### Teks Kontekstual per Entity

Teks yang di-embed bukan sekadar nama field, melainkan kalimat deskriptif yang menyertakan relasi antar entitas. Ini meningkatkan kualitas semantic search.

**departments**
```python
text = f"Departemen rumah sakit: {rec['nama_departemen']}"
```

**medical_teams**
```python
text = f"Tim medis: {rec['nama_tim']}"
```

**doctors** - menyertakan nama departemen dan tim (lookup dari data)
```python
dept_name = dept_lookup.get(rec["department_id"], "")
team_name = team_lookup.get(rec["team_id"], "")
text = (f"Dokter bernama {rec['nama_dokter']} bekerja di departemen "
        f"{dept_name} dan tergabung dalam {team_name}.")
```

**patients**
```python
text = f"Pasien bernama {rec['nama_pasien']} dengan kategori {rec['kategori']}."
```

**patient_treatments** - menyertakan nama pasien dan tim
```python
text = (f"Pasien {pasien.get('nama_pasien','?')} menjalani operasi "
        f"oleh {tim} pada tanggal {rec['tanggal_operasi']}.")
```

**billings**
```python
text = (f"Tagihan sebesar Rp {rec['total_biaya']:,} dengan metode "
        f"{rec['metode_pembayaran']} ({rec['sub_metode']}), "
        f"status: {rec['status_pembayaran']}.")
```

**billing_items**
```python
covered = "ditanggung asuransi" if rec["is_covered_by_insurance"] else "tidak ditanggung asuransi"
text = (f"Item tagihan: {rec['deskripsi']}, biaya Rp {rec['biaya']:,}, "
        f"{covered}.")
```

---

## 6. Verifikasi Akhir

```python
for idx in ["departments", "medical_teams", "doctors", "patients",
            "patient_treatments", "billings", "billing_items"]:
    count = client.count(index=idx)["count"]
    print(f"  {idx:25s}: {count} dokumen")
```

Setelah semua index terisi, script menghitung jumlah dokumen di tiap index untuk memastikan tidak ada data yang hilang saat proses bulk insert.
