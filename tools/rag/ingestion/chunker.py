from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any, Dict, List

from tools.rag.config import ChunkingConfig
from tools.rag.core.models import Chunk, RawDocument


class DocumentChunker:
    PORTO_FILTER_KEYS = {
        "kelas_id", "matkul_id", "prodi_id", "fakultas_id",
        "dosen_id", "tipe_konten", "tahun_ajaran", "semester",
    }
    WISUDAWAN_FILTER_KEYS = {
        "responden_id", "strata", "kode_fak", "kode_prodi",
        "periode_ijazah", "section",
    }

    def __init__(self, config: ChunkingConfig):
        self.config = config

    def chunk_document(self, doc: RawDocument) -> List[Chunk]:
        """Chunk a single RawDocument into a list of Chunks."""
        if not doc.text or not doc.text.strip():
            return []

        # Choose sizing based on content type
        is_short = doc.metadata.get("is_short_text", False)
        chunk_size = (
            self.config.short_text_chunk_size
            if is_short
            else self.config.chunk_size
        )
        overlap = (
            self.config.short_text_overlap
            if is_short
            else self.config.chunk_overlap
        )

        sentences = self._split_sentences(doc.text)
        raw_chunks = self._create_chunks(sentences, chunk_size, overlap)

        chunks = []
        for idx, text in enumerate(raw_chunks):
            if len(text.strip()) < self.config.min_chunk_size:
                continue
            chunk_id = self._make_chunk_id(doc.doc_id, idx)
            chunk = Chunk(
                chunk_id=chunk_id,
                doc_id=doc.doc_id,
                text=text.strip(),
                metadata={
                    **doc.metadata,
                    "chunk_index": idx,
                    "total_chunks": len(raw_chunks),
                    "char_length": len(text),
                },
                domain=doc.domain,
            )
            chunks.append(chunk)
        return chunks

    def chunk_documents(self, docs: List[RawDocument]) -> List[Chunk]:
        all_chunks = []
        for doc in docs:
            all_chunks.extend(self.chunk_document(doc))
        return all_chunks

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        # Normalise whitespace
        text = re.sub(r"\s+", " ", text).strip()
        # Split on . ! ? followed by space+capital, or newlines
        pattern = r"(?<=[.!?])\s+(?=[A-ZA-Z\u00C0-\u024F])|(?<=\n)"
        parts = re.split(pattern, text)
        # Remove empties
        return [p.strip() for p in parts if p.strip()]

    def _create_chunks(
        self, sentences: List[str], chunk_size: int, overlap: int
    ) -> List[str]:
        char_limit = chunk_size * 4
        overlap_chars = overlap * 4

        chunks: List[str] = []
        current: List[str] = []
        current_len = 0

        for sent in sentences:
            sent_len = len(sent)
            if current_len + sent_len > char_limit and current:
                chunks.append(" ".join(current))
                # Keep overlap window
                overlap_text = " ".join(current)[-overlap_chars:]
                current = [overlap_text] if overlap_text else []
                current_len = len(overlap_text)
            current.append(sent)
            current_len += sent_len + 1

        if current:
            chunks.append(" ".join(current))

        return chunks

    @staticmethod
    def _make_chunk_id(doc_id: str, idx: int) -> str:
        raw = f"{doc_id}::{idx}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

class PortoDocumentFactory:
    @staticmethod
    def from_teks_row(row: Dict[str, Any]) -> RawDocument:
        """
        row keys :
          teks_id, kelas_id, matkul_id, prodi_id, fakultas_id,
          tipe_konten, konten, tahun_ajaran, semester, kode_mk,
          nama_mk, dosen_names (list[str])
        """
        doc_id = str(row["teks_id"])
        header = (
            f"[{row.get('tipe_konten', '')}] "
            f"MK: {row.get('kode_mk', '')} - {row.get('nama_mk', '')} | "
            f"Prodi: {row.get('kode_prodi', '')} | "
            f"TA: {row.get('tahun_ajaran', '')} Sem-{row.get('semester', '')}"
        )
        text = f"{header}\n{row.get('konten', '')}"
        metadata = {
            "kelas_id": str(row.get("kelas_id", "")),
            "matkul_id": str(row.get("matkul_id", "")),
            "prodi_id": str(row.get("prodi_id", "")),
            "fakultas_id": str(row.get("fakultas_id", "")),
            "tipe_konten": row.get("tipe_konten", ""),
            "tahun_ajaran": row.get("tahun_ajaran", ""),
            "semester": row.get("semester", ""),
            "kode_mk": row.get("kode_mk", ""),
            "nama_mk": row.get("nama_mk", ""),
            "dosen_names": row.get("dosen_names", []),
            "is_short_text": False,
            "source_table": "teks_portofolio",
        }
        return RawDocument(doc_id=doc_id, text=text, metadata=metadata, domain="porto")

    @staticmethod
    def from_komentar_row(row: Dict[str, Any]) -> RawDocument:
        """
        row keys: 
            komentar_id, kelas_id, matkul_id, prodi_id,
            teks_komentar, tahun_ajaran, semester, kode_mk
        """
        doc_id = str(row["komentar_id"])
        header = (
            f"[komentar_mahasiswa] MK: {row.get('kode_mk', '')} | "
            f"TA: {row.get('tahun_ajaran', '')} Sem-{row.get('semester', '')}"
        )
        text = f"{header}\n{row.get('teks_komentar', '')}"
        metadata = {
            "kelas_id": str(row.get("kelas_id", "")),
            "matkul_id": str(row.get("matkul_id", "")),
            "prodi_id": str(row.get("prodi_id", "")),
            "fakultas_id": str(row.get("fakultas_id", "")),
            "tahun_ajaran": row.get("tahun_ajaran", ""),
            "semester": row.get("semester", ""),
            "kode_mk": row.get("kode_mk", ""),
            "is_short_text": True,        
            "source_table": "komentar_mahasiswa",
        }
        return RawDocument(doc_id=doc_id, text=text, metadata=metadata, domain="porto")


class WisudawanDocumentFactory:
    OPEN_TEXT_FIELDS = {
        "kebiasaan_belajar": "Kebiasaan Belajar",
        "kesan_prestasi": "Kesan & Prestasi Belajar",
        "pengalaman_berkesan": "Pengalaman Berkesan",
        "aktivitas_kemahasiswaan": "Aktivitas Kemahasiswaan",
        "cita_karier": "Cita-cita Karier",
        "cita_hidup": "Cita-cita Hidup",
        "motto": "Motto",
        "sifat_khas": "Sifat Khas Diri",
        "suka_duka": "Suka Duka ITB",
        "segi_positif": "Segi Positif ITB",
        "segi_negatif": "Segi Negatif ITB",
        "saran_itb": "Saran untuk ITB",
        "saran_mhs_lain": "Saran untuk Mahasiswa Lain",
        "catatan_lain": "Catatan/Komentar Lain",
    }

    @staticmethod
    def from_responden_row(row: Dict[str, Any]) -> List[RawDocument]:
        docs = []
        responden_id = str(row.get("responden_id", uuid.uuid4()))
        base_meta = {
            "responden_id": responden_id,
            "strata": row.get("strata", ""),
            "kode_fak": row.get("kode_fak", ""),
            "kode_prodi": row.get("kode_prodi", ""),
            "periode_ijazah": row.get("periode_ijazah", ""),
            "is_short_text": True,
        }

        for field_name, label in WisudawanDocumentFactory.OPEN_TEXT_FIELDS.items():
            text = row.get(field_name, "")
            if not text or not str(text).strip():
                continue
            doc_id = f"{responden_id}::{field_name}"
            header = (
                f"[{label}] "
                f"Strata: {row.get('strata', '')} | "
                f"Fakultas: {row.get('kode_fak', '')} | "
                f"Prodi: {row.get('kode_prodi', '')} | "
                f"Periode: {row.get('periode_ijazah', '')}"
            )
            full_text = f"{header}\n{str(text).strip()}"
            meta = {**base_meta, "section": field_name, "section_label": label}
            docs.append(
                RawDocument(
                    doc_id=doc_id,
                    text=full_text,
                    metadata=meta,
                    domain="wisudawan",
                )
            )
        return docs