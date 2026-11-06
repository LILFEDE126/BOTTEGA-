#!/usr/bin/env python3
"""Layer 2 (THE): PostgreSQL + pgvector persistence, PDF/document extraction, safe transactional
context manager, deterministic local L2 embedding fallback and in-memory cloud archive fallback."""

from contextlib import contextmanager
import hashlib
import io
import re
from typing import Any, Dict, List, Optional, Tuple
import psycopg2
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector
from pypdf import PdfReader
from pypdf.errors import PyPdfError
import requests

from config import (
    EMBED_DIM,
    OLLAMA_EMBED_MODEL,
    OLLAMA_EMBED_URL,
    get_db_config,
)
from logging_bottega import log, log_exception
from geometria_semaforo import (
    costruisci_testo_ancorato,
    fondi_rrf,
    normalizza_l2,
    similitudine_coseno,
    valuta_semaforo,
)
from grounding_numerico import arrotonda_esatto_el_x8
from presidio_concorrenza import SEGRETARIO_THE

_ARCHIVIO_MEMORIA_RAM: List[Dict[str, Any]] = []

TERMINI_ECONOMICI_AFFINI = {
    "costi",
    "costo",
    "prezzo",
    "prezzi",
    "preventivo",
    "preventivi",
    "budget",
    "investimento",
    "investimenti",
    "spesa",
    "spese",
    "euro",
    "eur",
    "bando",
    "bandi",
    "voucher",
    "contributo",
    "agevolazione",
    "finanziamento",
    "sito",
    "brochure",
    "packaging",
    "marketing",
    "business",
}


def conta_frammenti_archivio_ram(titolo: Optional[str] = None) -> int:
    """Returns the number of indexed fragments currently stored in the in-memory RAM archive."""
    if titolo is None:
        return len(_ARCHIVIO_MEMORIA_RAM)
    return sum(1 for item in _ARCHIVIO_MEMORIA_RAM if item.get("titolo") == titolo)


def normalizza_spazi_testo_pdf(testo: str) -> str:
    """Repairs missing spaces between glued words, numbers, currencies, and punctuation in justified PDFs."""
    if not testo:
        return ""
    t = re.sub(r"([a-zàèéìòùáéíóúñ])([A-ZÀÈÉÌÒÙ])", r"\1 \2", testo)
    t = re.sub(r"([a-zA-Zàèéìòùáéíóúñ]{2,})(\d)", r"\1 \2", t)
    t = re.sub(r"(\d)(€)", r"\1 \2", t)
    t = re.sub(r"(€)(\d)", r"\1 \2", t)
    t = re.sub(r"(\d|%|€)([a-zA-Zàèéìòùáéíóúñ]{2,})", r"\1 \2", t)
    t = re.sub(r"\b(euro)([a-zA-Zàèéìòùáéíóúñ]+)", r"\1 \2", t, flags=re.IGNORECASE)
    t = re.sub(r"([,:;])([a-zA-Zàèéìòùáéíóúñ€])", r"\1 \2", t)
    t = re.sub(r"([a-zA-Z0-9àèéìòùáéíóúñ])\(", r"\1 (", t)
    t = re.sub(r"\)([a-zA-Z0-9àèéìòùáéíóúñ])", r") \1", t)
    return t


def _suddividi_testo_in_blocchi(testo: str, prefisso: str, max_caratteri: int = 2000) -> List[Tuple[str, str]]:
    """Splits a page or document text into clean semantic paragraphs bounded by max_caratteri."""
    testo = normalizza_spazi_testo_pdf(testo)
    paragrafi_grezzi = [p.strip() for p in re.split(r"\n\s*\n", testo) if p.strip()]
    if not paragrafi_grezzi and testo.strip():
        paragrafi_grezzi = [testo.strip()]

    blocchi: List[Tuple[str, str]] = []
    buffer_corrente = ""
    indice_parte = 1

    for p in paragrafi_grezzi:
        if len(buffer_corrente) + len(p) + 2 <= max_caratteri:
            buffer_corrente = f"{buffer_corrente}\n{p}".strip() if buffer_corrente else p
        else:
            if buffer_corrente:
                etichetta = f"{prefisso}" if indice_parte == 1 and len(paragrafi_grezzi) == 1 else f"{prefisso}.{indice_parte}"
                blocchi.append((etichetta, buffer_corrente))
                indice_parte += 1
            if len(p) <= max_caratteri:
                buffer_corrente = p
            else:
                for pos in range(0, len(p), max_caratteri):
                    fetta = p[pos:pos + max_caratteri].strip()
                    if fetta:
                        blocchi.append((f"{prefisso}.{indice_parte}", fetta))
                        indice_parte += 1
                buffer_corrente = ""

    if buffer_corrente:
        etichetta = f"{prefisso}" if indice_parte == 1 else f"{prefisso}.{indice_parte}"
        blocchi.append((etichetta, buffer_corrente))

    return blocchi


def estrai_blocchi_documento(nome_file: str, contenuto_bytes: bytes) -> List[Tuple[str, str]]:
    """Extracts structured (section, text) tuples from PDF files (.pdf) or plain-text files (.txt, .md, .csv, .py)."""
    if not contenuto_bytes:
        return []

    if nome_file.strip().lower().endswith(".pdf"):
        lettore = PdfReader(io.BytesIO(contenuto_bytes))
        blocchi_pdf: List[Tuple[str, str]] = []
        for idx, pagina in enumerate(lettore.pages, start=1):
            try:
                testo_pag = (pagina.extract_text() or "").strip()
            except (PyPdfError, ValueError, KeyError, TypeError):
                testo_pag = ""
            if testo_pag:
                blocchi_pdf.extend(_suddividi_testo_in_blocchi(testo_pag, f"Page {idx}"))
        return blocchi_pdf

    testo_doc = contenuto_bytes.decode("utf-8", errors="replace")
    paragrafi = [p.strip() for p in re.split(r"\n\s*\n", testo_doc) if p.strip()]
    if not paragrafi and testo_doc.strip():
        return _suddividi_testo_in_blocchi(testo_doc.strip(), "Paragraph 1")
    return [(f"Paragraph {i}", p) for i, p in enumerate(paragrafi, start=1)]


@contextmanager
def connessione_db(registra_vettore: bool = False):
    """Transactional context manager guaranteeing commit/rollback on BaseException and conn.close() in finally."""
    conn = psycopg2.connect(**get_db_config())
    try:
        if registra_vettore:
            register_vector(conn)
        with conn:
            yield conn
    except BaseException:
        log_exception("Errore transazionale PostgreSQL (rollback eseguito)", "DB_CONN_001")
        raise
    finally:
        conn.close()


def _embedding_lessicale_locale(testo: str) -> List[float]:
    """Deterministic EMBED_DIM (768) fallback vector (L2 Feature Hashing) allowing local
    and cloud document indexing even when Ollama is not installed."""
    vec = [0.0] * EMBED_DIM
    tokens = re.findall(r"\w+", testo.lower())
    if not tokens:
        vec[0] = 1.0
        return vec
    for tok in tokens:
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % EMBED_DIM
        segno = 1.0 if (digest[4] % 2 == 0) else -1.0
        vec[idx] += segno
    return normalizza_l2(vec)


def calcola_embedding(testi: List[str]) -> List[List[float]]:
    """Calls Ollama /api/embed in batch; falls back to deterministic local 768-dim L2 vectors if unreachable."""
    try:
        res = requests.post(
            OLLAMA_EMBED_URL,
            json={"model": OLLAMA_EMBED_MODEL, "input": testi},
            timeout=10,
        )
        res.raise_for_status()
        raw_vecs = res.json()["embeddings"]
        output: List[List[float]] = []
        for v in raw_vecs:
            if len(v) != EMBED_DIM:
                raise RuntimeError(f"Dimensione embedding {len(v)} diversa da EMBED_DIM ({EMBED_DIM}).")
            output.append(normalizza_l2(v))
        return output
    except requests.exceptions.RequestException:
        log.warning(
            "Ollama /api/embed non raggiungibile: uso embedding deterministico locale per PostgreSQL",
            extra={"code": "EMB_FALLBACK_001"},
        )
        return [_embedding_lessicale_locale(t) for t in testi]


def inizializza_schema() -> None:
    """Creates the vector extension and the memoria_bottega and dominio_centroidi tables."""
    ddl = f"""
    CREATE EXTENSION IF NOT EXISTS vector;

    CREATE TABLE IF NOT EXISTS memoria_bottega (
        id SERIAL PRIMARY KEY,
        dominio TEXT NOT NULL,
        titolo TEXT NOT NULL,
        sezione TEXT NOT NULL,
        testo_ancorato TEXT NOT NULL,
        hash_text CHAR(64) UNIQUE NOT NULL,
        embedding vector({EMBED_DIM}) NOT NULL,
        tsv_it tsvector GENERATED ALWAYS AS (to_tsvector('italian', testo_ancorato)) STORED,
        tsv_simple tsvector GENERATED ALWAYS AS (to_tsvector('simple', testo_ancorato)) STORED,
        creato_il TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS ix_mem_fts_it ON memoria_bottega USING gin (tsv_it);
    CREATE INDEX IF NOT EXISTS ix_mem_fts_simple ON memoria_bottega USING gin (tsv_simple);
    CREATE INDEX IF NOT EXISTS ix_mem_hnsw ON memoria_bottega USING hnsw (embedding vector_cosine_ops);

    CREATE TABLE IF NOT EXISTS dominio_centroidi (
        dominio TEXT PRIMARY KEY,
        embedding vector({EMBED_DIM}) NOT NULL,
        n_frammenti INT NOT NULL
    );
    """
    with connessione_db(registra_vettore=False) as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
    log.info("Schema PostgreSQL + pgvector inizializzato", extra={"code": "DB_INIT_001"})


def incasella_e_salva(dominio: str, titolo: str, blocchi: List[Tuple[str, str]]) -> int:
    """Deduplicates blocks via SHA-256, computes embeddings outside the lock and updates PostgreSQL
    or the in-memory session archive when running on cloud without local PostgreSQL."""
    righe_grezze: List[Tuple[str, str, str]] = []
    for sezione, contenuto in blocchi:
        if not contenuto or not contenuto.strip():
            continue
        ancorato = costruisci_testo_ancorato(dominio, titolo, sezione, contenuto)
        h = hashlib.sha256(ancorato.encode("utf-8")).hexdigest()
        righe_grezze.append((sezione.strip(), ancorato, h))

    if not righe_grezze:
        return 0

    righe = sorted(righe_grezze, key=lambda item: len(item[1]), reverse=True)
    vettori = calcola_embedding([r[1] for r in righe])
    valori = [
        (dominio, titolo, righe[i][0], righe[i][1], righe[i][2], str(vettori[i]))
        for i in range(len(righe))
    ]

    with SEGRETARIO_THE.sezione_sacra(dominio, fabbisogno_massimo=1):
        hash_esistenti = {item["hash_text"] for item in _ARCHIVIO_MEMORIA_RAM}
        inseriti_ram = 0
        for i in range(len(righe)):
            if righe[i][2] not in hash_esistenti:
                _ARCHIVIO_MEMORIA_RAM.append({
                    "id": len(_ARCHIVIO_MEMORIA_RAM) + 1,
                    "dominio": dominio,
                    "titolo": titolo,
                    "sezione": righe[i][0],
                    "testo": righe[i][1],
                    "hash_text": righe[i][2],
                    "embedding": vettori[i],
                })
                hash_esistenti.add(righe[i][2])
                inseriti_ram += 1

        try:
            with connessione_db(registra_vettore=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM memoria_bottega WHERE dominio = %s", (dominio,))
                    prima = int(cur.fetchone()[0])

                    execute_values(
                        cur,
                        """
                        INSERT INTO memoria_bottega (dominio, titolo, sezione, testo_ancorato, hash_text, embedding)
                        VALUES %s
                        ON CONFLICT (hash_text) DO NOTHING
                        """,
                        valori,
                        template="(%s, %s, %s, %s, %s, %s::vector)",
                    )

                    cur.execute("SELECT COUNT(*) FROM memoria_bottega WHERE dominio = %s", (dominio,))
                    dopo = int(cur.fetchone()[0])
                    inseriti = dopo - prima

                    cur.execute(
                        "SELECT AVG(embedding)::text, COUNT(*) FROM memoria_bottega WHERE dominio = %s",
                        (dominio,),
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        raw_vals = [float(x) for x in row[0].strip("[]").split(",")]
                        centro_str = str(normalizza_l2(raw_vals))
                        cur.execute(
                            """
                            INSERT INTO dominio_centroidi (dominio, embedding, n_frammenti)
                            VALUES (%s, %s::vector, %s)
                            ON CONFLICT (dominio) DO UPDATE
                            SET embedding = EXCLUDED.embedding,
                                n_frammenti = EXCLUDED.n_frammenti
                            """,
                            (dominio, centro_str, int(row[1])),
                        )
        except psycopg2.Error:
            log.info(
                "PostgreSQL locale non attivo: salvati %d frammenti nell'archivio RAM (dominio '%s')",
                inseriti_ram,
                dominio,
                extra={"code": "RAG_RAM_001"},
            )
            return inseriti_ram

    log.info(
        "Indicizzati %d nuovi frammenti per dominio '%s'",
        inseriti,
        dominio,
        extra={"code": "RAG_INGEST_001"},
    )
    return inseriti


def _recupera_da_archivio_ram(
    query: str,
    q_vec: List[float],
    dominio: str,
    top_k: int = 3,
) -> Dict[str, Any]:
    """Executes 3-way RRF + Guarded Semaphore (EWD472) over the in-memory session archive."""
    if not _ARCHIVIO_MEMORIA_RAM:
        return {"semaforo": "ROJO", "s_max": 0.0, "s_dominio": 0.0, "frammenti": []}

    parole_q = list(dict.fromkeys(p for p in re.findall(r"\w+|\d+[.,]\d+", query.lower()) if len(p) >= 3))
    candidati_dom = [x for x in _ARCHIVIO_MEMORIA_RAM if x["dominio"] == dominio]
    ha_match_in_dominio = any(
        any(p in x["testo"].lower() for p in parole_q)
        for x in candidati_dom
    )
    candidati = candidati_dom if (candidati_dom and (ha_match_in_dominio or not parole_q)) else list(_ARCHIVIO_MEMORIA_RAM)

    somma_vec = [0.0] * EMBED_DIM
    for item in candidati:
        for idx, val in enumerate(item["embedding"]):
            somma_vec[idx] += val
    centroide = normalizza_l2(somma_vec)
    s_dom = max(0.0, similitudine_coseno(q_vec, centroide))

    valutati: List[Dict[str, Any]] = []
    cerca_costi = bool(set(parole_q) & TERMINI_ECONOMICI_AFFINI)
    denominatore_copertura = max(1, min(len(parole_q), 6))

    for item in candidati:
        sim_raw = max(0.0, similitudine_coseno(q_vec, item["embedding"]))
        testo_low = item["testo"].lower()
        match_count = sum(1 for p in parole_q if p in testo_low)
        if cerca_costi:
            bonus_economico = sum(1 for t_ec in TERMINI_ECONOMICI_AFFINI if t_ec in testo_low)
            if "€" in testo_low or "euro" in testo_low:
                bonus_economico += 2
            match_count += bonus_economico
        copertura = (match_count / denominatore_copertura) if parole_q else 0.0
        sim_effettiva = max(sim_raw, min(0.95, 0.52 + 0.43 * min(1.0, copertura))) if match_count > 0 else sim_raw
        valutati.append({
            "id": item["id"],
            "titolo": item["titolo"],
            "sezione": item["sezione"],
            "testo": item["testo"],
            "similitudine": float(sim_effettiva),
            "match_count": match_count,
        })

    limite_k = max(top_k, 5)
    lista_vett = sorted(valutati, key=lambda x: x["similitudine"], reverse=True)[:20]
    con_match = [x for x in valutati if x["match_count"] > 0]
    lista_it = sorted(con_match, key=lambda x: (x["match_count"], x["similitudine"]), reverse=True)[:20]
    lista_simple = list(lista_it)

    ordinati = fondi_rrf(lista_vett, lista_it, lista_simple, top_k=limite_k)
    ha_match = bool(con_match)
    if ha_match and s_dom < 0.35:
        s_dom = 0.55
    colore, s_max = valuta_semaforo(ordinati, s_dominio=s_dom, ha_match_lessicale=ha_match)
    return {
        "semaforo": colore,
        "s_max": float(arrotonda_esatto_el_x8(s_max, 4)),
        "s_dominio": float(arrotonda_esatto_el_x8(s_dom, 4)),
        "frammenti": ordinati,
    }


def recupera_con_semaforo(query: str, dominio: str, top_k: int = 3) -> Dict[str, Any]:
    """3-way hybrid retrieval (HNSW, FTS Italian, FTS Simple) with guaranteed connection closure
    and automatic fallback to the in-memory session archive when PostgreSQL is unreachable."""
    q_vec = calcola_embedding([query])[0]
    q_vec_str = str(q_vec)

    with SEGRETARIO_THE.sezione_sacra(dominio, fabbisogno_massimo=1):
        try:
            with connessione_db(registra_vettore=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT embedding::text FROM dominio_centroidi WHERE dominio = %s", (dominio,))
                    c_row = cur.fetchone()
                    if c_row and c_row[0]:
                        c_vec = [float(x) for x in c_row[0].strip("[]").split(",")]
                        s_dom = similitudine_coseno(q_vec, c_vec)
                    else:
                        s_dom = 0.0

                    cur.execute(
                        """
                        SELECT id, titolo, sezione, testo_ancorato, 1 - (embedding <=> %s::vector) AS sim
                        FROM memoria_bottega
                        WHERE dominio = %s
                        ORDER BY embedding <=> %s::vector ASC
                        LIMIT 20
                        """,
                        (q_vec_str, dominio, q_vec_str),
                    )
                    lista_vett = [
                        {"id": r[0], "titolo": r[1], "sezione": r[2], "testo": r[3], "similitudine": float(r[4])}
                        for r in cur.fetchall()
                    ]

                    cur.execute(
                        """
                        SELECT id, titolo, sezione, testo_ancorato, 1 - (embedding <=> %s::vector) AS sim
                        FROM memoria_bottega
                        WHERE dominio = %s AND tsv_it @@ plainto_tsquery('italian', %s)
                        ORDER BY ts_rank(tsv_it, plainto_tsquery('italian', %s)) DESC
                        LIMIT 20
                        """,
                        (q_vec_str, dominio, query, query),
                    )
                    lista_it = [
                        {"id": r[0], "titolo": r[1], "sezione": r[2], "testo": r[3], "similitudine": float(r[4])}
                        for r in cur.fetchall()
                    ]

                    cur.execute(
                        """
                        SELECT id, titolo, sezione, testo_ancorato, 1 - (embedding <=> %s::vector) AS sim
                        FROM memoria_bottega
                        WHERE dominio = %s AND tsv_simple @@ plainto_tsquery('simple', %s)
                        ORDER BY ts_rank(tsv_simple, plainto_tsquery('simple', %s)) DESC
                        LIMIT 20
                        """,
                        (q_vec_str, dominio, query, query),
                    )
                    lista_simple = [
                        {"id": r[0], "titolo": r[1], "sezione": r[2], "testo": r[3], "similitudine": float(r[4])}
                        for r in cur.fetchall()
                    ]
        except psycopg2.Error:
            return _recupera_da_archivio_ram(query, q_vec, dominio, top_k=top_k)

    ordinati = fondi_rrf(lista_vett, lista_it, lista_simple, top_k=top_k)
    if not ordinati and _ARCHIVIO_MEMORIA_RAM:
        return _recupera_da_archivio_ram(query, q_vec, dominio, top_k=top_k)

    ha_match = bool(lista_it or lista_simple)
    colore, s_max = valuta_semaforo(ordinati, s_dominio=s_dom, ha_match_lessicale=ha_match)
    s_max_esatto = float(arrotonda_esatto_el_x8(s_max, 4))
    s_dom_esatto = float(arrotonda_esatto_el_x8(s_dom, 4))

    log.info(
        "Recupero RAG dominio='%s' semaforo=%s s_max=%.4f",
        dominio,
        colore,
        s_max_esatto,
        extra={"code": "RAG_RET_001"},
    )
    return {
        "semaforo": colore,
        "s_max": s_max_esatto,
        "s_dominio": s_dom_esatto,
        "frammenti": ordinati,
    }
