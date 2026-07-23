import json
import re
from pathlib import Path

def process_file(filepath):
    with open(filepath, 'r') as f:
        data = json.load(f)
        
    for case in data.get("cases", []):
        # 1. Fix expected tables
        if "expected_grounding" in case and "expected_tables" in case["expected_grounding"]:
            tables = case["expected_grounding"]["expected_tables"]
            new_tables = []
            for t in tables:
                if t == "v_akademik_portofolio" or t == "v_akademik_komponen_evaluasi_kelas":
                    new_tables.append("analitik.v_akademik_kelas")
                else:
                    new_tables.append(t)
            case["expected_grounding"]["expected_tables"] = list(set(new_tables))
            
        # 2. Fix must_include patterns
        if "expected_sql_behavior" in case and "must_include_sql_patterns" in case["expected_sql_behavior"]:
            patterns = case["expected_sql_behavior"]["must_include_sql_patterns"]
            new_patterns = []
            for p in patterns:
                p = p.replace("v_akademik_portofolio", "v_akademik_kelas")
                p = p.replace("v_akademik_komponen_evaluasi_kelas", "v_akademik_kelas")
                p = p.replace("kode_pertanyaan", "skor_q21")
                new_patterns.append(p)
            case["expected_sql_behavior"]["must_include_sql_patterns"] = new_patterns
            
        # 3. Fix gold SQL
        if "expected_sql_behavior" in case and "gold_sql" in case["expected_sql_behavior"]:
            sql = case["expected_sql_behavior"]["gold_sql"]
            
            # Simple replacements
            sql = sql.replace("v_akademik_portofolio p", "analitik.v_akademik_kelas p")
            sql = sql.replace("v_akademik_portofolio", "analitik.v_akademik_kelas")
            sql = sql.replace("rata_rata_evaluasi", "avg_skor_overall")
            sql = sql.replace("nama_matkul", "nama_matkul_id")
            
            # Fix JOINs
            if "JOIN v_info_umum" in sql:
                sql = re.sub(r' JOIN v_info_umum_kelas_matkul [a-z] ON [a-zA-Z._= ]+', '', sql)
                sql = re.sub(r' JOIN v_info_umum_dosen [a-z] ON [a-zA-Z._= ]+', '', sql)
                sql = sql.replace("d.nama_dosen", "array_to_string(p.semua_dosen_nama_gelar, ', ') AS nama_dosen")
                sql = sql.replace("k.nama_fakultas", "p.kode_fakultas AS nama_fakultas")
            
            # Fix semester format
            # e.g., semester = '2023-2' -> tahun = 2023 AND semester = 2
            sql = re.sub(r"semester = '(\d{4})-(\d)'", r"tahun = \1 AND semester = \2", sql)
            
            # Fix QMETA
            if "v_akademik_komponen_evaluasi_kelas" in sql:
                sql = sql.replace("v_akademik_komponen_evaluasi_kelas", "analitik.v_akademik_kelas")
                sql = re.sub(r"SELECT (.*?)kode_pertanyaan, pertanyaan, skor(.*?)" , r"SELECT \1skor_q21 AS skor_kejelasan_materi\2", sql)
                sql = re.sub(r" AND pertanyaan ILIKE '%[^%]+%'", "", sql)
                
            case["expected_sql_behavior"]["gold_sql"] = sql

    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

base = Path("evals/datasets/experiments")
process_file(base / "sql_grounding_cases.json")
print("Fixed sql_grounding_cases.json")
