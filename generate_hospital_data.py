"""
Generator Data Dummy Rumah Sakit Sehat Selalu
Menggunakan Faker (Indonesia locale) — tanpa LLM, tanpa duplikat.

Instalasi:
    pip install faker opensearch-py

Jalankan:
    python generate_hospital_data.py
"""

import json
import random
from datetime import datetime, timedelta
from faker import Faker

fake = Faker("id_ID")  # locale Indonesia
random.seed(42)
Faker.seed(42)

# ──────────────────────────────────────────────
# Konfigurasi jumlah data
# ──────────────────────────────────────────────
N_DEPARTMENTS    = 10
N_MEDICAL_TEAMS  = 20
N_DOCTORS        = 80
N_PATIENTS       = 500
N_TREATMENTS     = 1000   # patient_treatments
# billing + billing_items di-generate otomatis dari treatments

# ──────────────────────────────────────────────
# Referensi domain data agar lebih realistis
# ──────────────────────────────────────────────
DEPARTMENT_NAMES = [
    "Penyakit Dalam", "Bedah Umum", "Anak", "Kebidanan & Kandungan",
    "Jantung & Pembuluh Darah", "Saraf", "Ortopedi", "THT",
    "Mata", "Kulit & Kelamin",
]

TEAM_SPECIALTIES = [
    "Tim Jantung", "Tim Bedah Saraf", "Tim Onkologi", "Tim Trauma",
    "Tim Neonatal", "Tim Rehabilitasi", "Tim Endoskopi", "Tim Urologi",
    "Tim Dermatologi", "Tim Imunologi", "Tim Respirologi",
    "Tim Gastroenterologi", "Tim Hematologi", "Tim Reumatologi",
    "Tim Endokrinologi", "Tim Geriatri", "Tim Psikiatri",
    "Tim Oftalmologi", "Tim Anestesi", "Tim Gizi Klinik",
]

PATIENT_CATEGORIES = ["Umum", "BPJS", "Asuransi Swasta", "VIP"]

PAYMENT_METHODS = ["Tunai", "Transfer Bank", "Kartu Debit",
                   "Kartu Kredit", "BPJS", "Asuransi"]

PAYMENT_SUB = {
    "Tunai": ["Cash"],
    "Transfer Bank": ["BCA", "BNI", "BRI", "Mandiri"],
    "Kartu Debit": ["BCA", "BNI", "Mandiri"],
    "Kartu Kredit": ["Visa", "Mastercard", "JCB"],
    "BPJS": ["BPJS Kesehatan"],
    "Asuransi": ["Prudential", "AXA", "Allianz", "Cigna", "Manulife"],
}

PAYMENT_STATUS = ["Lunas", "Belum Lunas", "Cicilan"]

BILLING_ITEM_DESCRIPTIONS = [
    "Konsultasi Dokter Spesialis",
    "Biaya Rawat Inap (per malam)",
    "Tindakan Operasi",
    "Obat-obatan",
    "Pemeriksaan Laboratorium",
    "Pemeriksaan Radiologi",
    "Fisioterapi",
    "Tindakan Anestesi",
    "Penggunaan Ruang ICU",
    "Pemeriksaan EKG",
    "Pemeriksaan USG",
    "Pemeriksaan CT-Scan",
    "Pemeriksaan MRI",
    "Tindakan Endoskopi",
    "Biaya Administrasi",
]

# ──────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────
def random_date(start_year=2022, end_year=2024):
    start = datetime(start_year, 1, 1)
    end   = datetime(end_year, 12, 31)
    delta = end - start
    return (start + timedelta(days=random.randint(0, delta.days))).isoformat()


# ──────────────────────────────────────────────
# 1. DEPARTMENTS
# ──────────────────────────────────────────────
departments = []
for i, name in enumerate(DEPARTMENT_NAMES[:N_DEPARTMENTS], start=1):
    departments.append({"_id": i, "nama_departemen": name})

# ──────────────────────────────────────────────
# 2. MEDICAL_TEAMS
# ──────────────────────────────────────────────
medical_teams = []
for i, name in enumerate(TEAM_SPECIALTIES[:N_MEDICAL_TEAMS], start=1):
    medical_teams.append({"_id": i, "nama_tim": name})

# ──────────────────────────────────────────────
# 3. DOCTORS
# ──────────────────────────────────────────────
# Pastikan setiap departemen punya minimal 1 dokter
dept_ids = [d["_id"] for d in departments]
team_ids = [t["_id"] for t in medical_teams]

doctors = []
used_names = set()

for i in range(1, N_DOCTORS + 1):
    # Buat nama unik
    while True:
        name = "Dr. " + fake.name()
        if name not in used_names:
            used_names.add(name)
            break

    doctors.append({
        "_id": i,
        "nama_dokter": name,
        "department_id": dept_ids[(i - 1) % len(dept_ids)],   # round-robin agar semua dept terisi
        "team_id": random.choice(team_ids),
    })

# ──────────────────────────────────────────────
# 4. PATIENTS
# ──────────────────────────────────────────────
patients = []
used_patient_names = set()

for i in range(1, N_PATIENTS + 1):
    while True:
        name = fake.name()
        if name not in used_patient_names:
            used_patient_names.add(name)
            break

    patients.append({
        "_id": i,
        "nama_pasien": name,
        "kategori": random.choice(PATIENT_CATEGORIES),
    })

# ──────────────────────────────────────────────
# 5. PATIENT_TREATMENTS
# ──────────────────────────────────────────────
patient_ids = [p["_id"] for p in patients]

patient_treatments = []
for i in range(1, N_TREATMENTS + 1):
    patient_treatments.append({
        "_id": i,
        "patient_id": random.choice(patient_ids),
        "team_id": random.choice(team_ids),
        "tanggal_operasi": random_date(),
    })

# ──────────────────────────────────────────────
# 6. BILLINGS  (1 billing per treatment)
# ──────────────────────────────────────────────
billings = []
for i, treatment in enumerate(patient_treatments, start=1):
    method = random.choice(PAYMENT_METHODS)
    sub    = random.choice(PAYMENT_SUB[method])
    billings.append({
        "_id": i,
        "treatment_id": treatment["_id"],
        "total_biaya": random.randint(100_000, 50_000_000),   # Rp 100rb – 50jt
        "metode_pembayaran": method,
        "sub_metode": sub,
        "status_pembayaran": random.choice(PAYMENT_STATUS),
    })

# ──────────────────────────────────────────────
# 7. BILLING_ITEMS  (1–5 item per billing)
# ──────────────────────────────────────────────
billing_items = []
item_id = 1
for billing in billings:
    n_items = random.randint(1, 5)
    # Pilih item descriptions unik untuk billing ini
    chosen_descs = random.sample(BILLING_ITEM_DESCRIPTIONS,
                                 min(n_items, len(BILLING_ITEM_DESCRIPTIONS)))
    for desc in chosen_descs:
        # Asuransi menanggung item tertentu
        covered = 1 if random.random() < 0.35 else 0
        billing_items.append({
            "_id": item_id,
            "billing_id": billing["_id"],
            "deskripsi": desc,
            "biaya": random.randint(20_000, 15_000_000),
            "is_covered_by_insurance": covered,
        })
        item_id += 1

# ──────────────────────────────────────────────
# Simpan ke JSON
# ──────────────────────────────────────────────
output = {
    "departments":        departments,
    "medical_teams":      medical_teams,
    "doctors":            doctors,
    "patients":           patients,
    "patient_treatments": patient_treatments,
    "billings":           billings,
    "billing_items":      billing_items,
}

with open("hospital_data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("✅ Data berhasil di-generate!")
print(f"   Departments     : {len(departments)}")
print(f"   Medical Teams   : {len(medical_teams)}")
print(f"   Doctors         : {len(doctors)}")
print(f"   Patients        : {len(patients)}")
print(f"   Treatments      : {len(patient_treatments)}")
print(f"   Billings        : {len(billings)}")
print(f"   Billing Items   : {len(billing_items)}")
print(f"   Total records   : {sum(len(v) for v in output.values())}")
print("\nFile disimpan ke: hospital_data.json")
