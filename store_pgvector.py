#!/usr/bin/env python3
"""Layer 2 (THE): PostgreSQL + pgvector persistence, safe transactional context manager and
deterministic local embedding fallback (L2 Feature Hashing) when Ollama is not installed."""

from contextlib import contextmanager
import hashlib
import re
from typing import Any, Dict, List, Tuple
import psycopg2
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector
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
    PostgreSQL document indexing even when Ollama is not installed."""
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
    """Deduplicates blocks via SHA-256, computes embeddings outside the lock and updates the domain centroid."""
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

    log.info(
        "Indicizzati %d nuovi frammenti per dominio '%s'",
        inseriti,
        dominio,
        extra={"code": "RAG_INGEST_001"},
    )
    return inseriti


def recupera_con_semaforo(query: str, dominio: str, top_k: int = 3) -> Dict[str, Any]:
    """3-way hybrid retrieval (HNSW, FTS Italian, FTS Simple) with guaranteed connection closure."""
    q_vec = calcola_embedding([query])[0]
    q_vec_str = str(q_vec)

    with SEGRETARIO_THE.sezione_sacra(dominio, fabbisogno_massimo=1):
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

    ordinati = fondi_rrf(lista_vett, lista_it, lista_simple, top_k=top_k)
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