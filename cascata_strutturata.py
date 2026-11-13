#!/usr/bin/env python3
"""Layer 3 (THE): 3-Layer Code Review Cascade (Strato L -> Strato A -> Strato D) with EWD426
Self-Stabilization, EL X8 Exact Rounding (EWD145) and Tri-Color Write Barrier (EWD496A)."""

import json
import sys
import time
from pathlib import Path
from typing import Callable, List
import psycopg2
import requests
from pydantic import BaseModel, Field

from logging_bottega import log, log_exception
from ispezione_moduli import ispezione_completa
from grounding_numerico import (
    arrotonda_esatto_el_x8,
    classifica_nodo_tricolore,
    verifica_conservazione_percentuali_decimal,
)
from store_pgvector import recupera_con_semaforo
from client_ollama import chiama_ollama_json


class OutputL(BaseModel):
    osservazione_architetturale: str = Field(
        description="Empirical analysis of what the code does and its structure"
    )
    scomposizione_moduli: List[str] = Field(
        description="Decomposition of responsibilities into pure functions and I/O boundaries"
    )
    complessita_inutile_rilevata: List[str] = Field(
        description="Superfluous abstractions, dead code or unnecessary coupling"
    )
    proposta_semplificata: str = Field(
        description="Concrete architectural simplification plan"
    )


class OutputA(BaseModel):
    criticita_sicurezza_e_limiti: List[str] = Field(
        description="Breaking points under load, race conditions, locks or memory leaks"
    )
    guardrail_mancanti: List[str] = Field(
        description="Missing timeouts, typed exceptions, rollbacks and structured log codes"
    )
    valutazione_originalita: str = Field(
        description="Craftsmanship solidity assessment versus fragile boilerplate"
    )
    test_consigliati: List[str] = Field(
        description="Edge cases and breaking tests to implement immediately"
    )


VOTO_MINIMO_INGEGNERISTICO: int = 1
VOTO_MASSIMO_INGEGNERISTICO: int = 10


class OutputD(BaseModel):
    dominio_e_codominio: str = Field(
        description="Formal specification of input types, output types and error states"
    )
    invarianti: List[str] = Field(
        description="Conditions that must hold true before and after execution"
    )
    complessita_big_o: str = Field(
        description="Asymptotic time and space complexity (e.g. O(N log N))"
    )
    codice_raffinato_finale: str = Field(
        description="The rewritten Python code: complete, typed, safe and testable"
    )
    voto_finale: int = Field(
        ge=VOTO_MINIMO_INGEGNERISTICO,
        le=VOTO_MASSIMO_INGEGNERISTICO,
        description="Strict engineering score from 1 to 10 for the original code",
    )


OutputLeonardo = OutputL
OutputAntirez = OutputA
OutputDijkstra = OutputD


def _formatta_frammenti_rag(risultato_rag: dict) -> str:
    frammenti = risultato_rag.get("frammenti", [])
    if not frammenti:
        return "Nessun frammento recuperato dal database."
    return "\n\n".join(f"- {frammento['testo']}" for frammento in frammenti)


def esegui_cascata(file_path: str, llm_fn: Callable = chiama_ollama_json) -> str:
    """Runs AST/THE inspection, hybrid RAG retrieval and the 3 sequential judgment layers (Strato L, Strato A, Strato D)."""
    percorso = Path(file_path)
    if not percorso.is_file():
        raise FileNotFoundError(f"File non trovato: {file_path}")

    codice_sorgente = percorso.read_text(encoding="utf-8")

    log.info("[Passo 0/4] Ispezione statica AST, Gerarchia THE & Radon su %s", percorso.name, extra={"code": "CAS_AST_001"})
    anatomia = ispezione_completa(str(percorso))
    anatomia_json = json.dumps(anatomia, indent=2, ensure_ascii=False)

    log.info("[Passo 1/4] Recupero RAG Ibrido (HNSW + FTS + RRF + Semaforo Guardato)", extra={"code": "CAS_RAG_001"})
    nomi_fn = " ".join(fn_info["nome"] for fn_info in anatomia["funzioni"])
    query_str = f"analisi architettura guardrail invarianti python {nomi_fn}".strip()
    try:
        rag_leo = recupera_con_semaforo(query_str, "generale", top_k=2)
        rag_ant = recupera_con_semaforo(query_str, "tecnico", top_k=2)
        rag_dij = recupera_con_semaforo(query_str, "normativo", top_k=2)
    except (psycopg2.Error, requests.exceptions.RequestException, RuntimeError) as exc:
        log_exception("RAG non raggiungibile (%s): proseguo con sola anatomia AST", "CAS_RAG_002", exc)
        rag_leo = {"semaforo": "AMBAR", "s_max": 0.0, "s_dominio": 0.0, "frammenti": []}
        rag_ant = {"semaforo": "AMBAR", "s_max": 0.0, "s_dominio": 0.0, "frammenti": []}
        rag_dij = {"semaforo": "AMBAR", "s_max": 0.0, "s_dominio": 0.0, "frammenti": []}

    ctx_leo = _formatta_frammenti_rag(rag_leo)
    ctx_ant = _formatta_frammenti_rag(rag_ant)
    ctx_dij = _formatta_frammenti_rag(rag_dij)

    log.info("[Passo 2/4] Strato 1/3: Strato L", extra={"code": "CAS_LEO_001"})
    t0 = time.perf_counter()
    out_leo = llm_fn(
        "Sei il primo strato (Strato L — Osservazione e Semplicita'): analizza l'anatomia empirica AST del codice, "
        "separa calcolo puro e I/O e individua ogni complessita' superflua. Non citare nomi propri di autori nei testi; "
        "usa esclusivamente i termini Strato L, Strato A, Strato D. Rispondi in italiano.",
        f"PRINCIPI STRATO L:\n{ctx_leo}\n\nANATOMIA AST:\n{anatomia_json}\n\n"
        f"CODICE SORGENTE:\n```python\n{codice_sorgente}\n```",
        OutputL,
    )
    t_leo = arrotonda_esatto_el_x8(time.perf_counter() - t0, 2)

    log.info("[Passo 3/4] Strato 2/3: Strato A", extra={"code": "CAS_ANT_001"})
    t0 = time.perf_counter()
    out_anti = llm_fn(
        "Sei il secondo strato (Strato A — Guardrail e Pragmatismo): individua i punti di rottura in produzione, "
        "gli except nudi, i timeout mancanti, i lock mal gestiti e i test di rottura. Non citare nomi propri di autori; "
        "usa esclusivamente Strato L, Strato A, Strato D. Rispondi in italiano.",
        f"PRINCIPI STRATO A:\n{ctx_ant}\n\nANALISI STRATO L:\n{out_leo.model_dump_json(indent=2)}\n\n"
        f"ANATOMIA AST:\n{anatomia_json}\n\nCODICE SORGENTE:\n```python\n{codice_sorgente}\n```",
        OutputA,
    )
    t_anti = arrotonda_esatto_el_x8(time.perf_counter() - t0, 2)

    log.info("[Passo 4/4] Strato 3/3: Strato D", extra={"code": "CAS_DIJ_001"})
    t0 = time.perf_counter()
    out_dijk = llm_fn(
        "Sei il terzo strato (Strato D — Rigore Formale e Refactoring): formalizza dominio, codominio, invarianti, "
        "complessita' Big-O e riscrivi il codice Python completo applicando le osservazioni dello Strato L e i guardrail "
        "dello Strato A. Non citare nomi propri di autori nei testi; usa esclusivamente Strato L, Strato A, Strato D.",
        f"PRINCIPI STRATO D:\n{ctx_dij}\n\nANALISI STRATO L:\n{out_leo.model_dump_json(indent=2)}\n\n"
        f"ANALISI STRATO A:\n{out_anti.model_dump_json(indent=2)}\n\n"
        f"CODICE SORGENTE:\n```python\n{codice_sorgente}\n```",
        OutputD,
    )
    t_dijk = arrotonda_esatto_el_x8(time.perf_counter() - t0, 2)

    prosa_generata = "\n".join([
        out_leo.osservazione_architetturale,
        out_leo.proposta_semplificata,
        out_anti.valutazione_originalita,
        out_dijk.dominio_e_codominio,
    ])
    contesto_totale = "\n".join([codice_sorgente, anatomia_json, ctx_leo, ctx_ant, ctx_dij])
    colore_nodo, cifre_non_ancorate = classifica_nodo_tricolore(prosa_generata, contesto_totale)
    pct_conservate = verifica_conservazione_percentuali_decimal(prosa_generata, contesto_totale)

    stato_grounding = (
        f"Nodo {colore_nodo} (EWD496A: cifre ancorate, percentuali conservate={pct_conservate})"
        if colore_nodo == "NERO"
        else f"Nodo {colore_nodo} - Write Barrier attivata per cifre non ancorate: {cifre_non_ancorate}"
    )

    sep = "\n"
    scomposizione_md = sep.join(f"- {item}" for item in out_leo.scomposizione_moduli)
    complessita_md = sep.join(f"- {item}" for item in out_leo.complessita_inutile_rilevata)
    criticita_md = sep.join(f"- {item}" for item in out_anti.criticita_sicurezza_e_limiti)
    guardrail_md = sep.join(f"- {item}" for item in out_anti.guardrail_mancanti)
    test_md = sep.join(f"- {item}" for item in out_anti.test_consigliati)
    invarianti_md = sep.join(f"- {item}" for item in out_dijk.invarianti)

    referto = (
        f"# Referto Ingegneristico: `{percorso.name}`\n\n"
        f"## 0. Anatomia Deterministica (THE) e Telemetria RAG\n"
        f"- **Funzioni e Metodi rilevati (AST)**: {anatomia['numero_funzioni']}\n"
        f"- **Blocchi `except:` nudi rilevati**: {anatomia['totale_except_nudi']}\n"
        f"- **Blocchi `except Exception:` generici**: {anatomia['totale_except_generici']}\n"
        f"- **Cicli privi di variante t (EWD316)**: {anatomia['cicli_senza_variante']}\n"
        f"- **Variabili globali mutabili (EWD35)**: {anatomia['usi_global_mutabili']}\n"
        f"- **Violazioni Gerarchia THE (EWD196)**: {anatomia['violazioni_gerarchia_the'] or 'Nessuna'}\n"
        f"- **Semafori RAG**: Strato L `{rag_leo['semaforo']}` (s_max={rag_leo['s_max']}) | "
        f"Strato A `{rag_ant['semaforo']}` (s_max={rag_ant['s_max']}) | "
        f"Strato D `{rag_dij['semaforo']}` (s_max={rag_dij['s_max']})\n"
        f"- **Barriera Tri-Colore Grounding (EWD496A)**: {stato_grounding}\n\n"
        f"```dot\n{anatomia['dot_graph']}\n```\n\n"
        f"---\n\n"
        f"## 1. Strato L — Osservazione e Semplicita' ({t_leo}s)\n"
        f"**Osservazione architetturale:** {out_leo.osservazione_architetturale}\n\n"
        f"**Scomposizione in moduli:**\n{scomposizione_md}\n\n"
        f"**Complessita' superflua rilevata:**\n{complessita_md}\n\n"
        f"**Proposta di semplificazione:** {out_leo.proposta_semplificata}\n\n"
        f"---\n\n"
        f"## 2. Strato A — Guardrail e Pragmatismo ({t_anti}s)\n"
        f"**Criticita' e punti di rottura:**\n{criticita_md}\n\n"
        f"**Guardrail obbligatori:**\n{guardrail_md}\n\n"
        f"**Valutazione solidita':** {out_anti.valutazione_originalita}\n\n"
        f"**Test di rottura consigliati:**\n{test_md}\n\n"
        f"---\n\n"
        f"## 3. Strato D — Rigore Formale e Refactoring ({t_dijk}s)\n"
        f"- **Dominio e Codominio:** {out_dijk.dominio_e_codominio}\n"
        f"- **Complessita' Asintotica:** `{out_dijk.complessita_big_o}`\n"
        f"- **Voto Ingegneristico al codice originale:** **{out_dijk.voto_finale}/10**\n\n"
        f"**Invarianti formali:**\n{invarianti_md}\n\n"
        f"### Codice Raffinato Finale\n"
        f"```python\n{out_dijk.codice_raffinato_finale}\n```\n"
    )
    return referto


if __name__ == "__main__":
    if len(sys.argv) != 2:
        log.error("Uso corretto: python cascata_strutturata.py <percorso_file.py>", extra={"code": "CAS_ARG_001"})
        sys.exit(1)
    referto_md = esegui_cascata(sys.argv[1])
    file_out = f"referto_{Path(sys.argv[1]).stem}.md"
    Path(file_out).write_text(referto_md, encoding="utf-8")
    log.info("Referto salvato con successo in: %s", file_out, extra={"code": "CAS_OK_001"})
