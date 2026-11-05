#!/usr/bin/env python3
"""Layer 1 (THE): Pure vector geometry functions, RRF fusion and EWD472 guarded semaphore."""

import math
from typing import Any, Dict, List, Tuple

from config import (
    PESO_FTS_LINGUA,
    PESO_FTS_SIMPLE,
    PESO_VETTORIALE,
    RRF_K,
    TAU_ALTO,
    TAU_BASSO,
    TAU_DOMINIO,
)


def normalizza_l2(vettore: List[float]) -> List[float]:
    """Normalizes a vector to unit Euclidean norm so cosine similarity equals dot product."""
    norma = math.sqrt(sum(x * x for x in vettore))
    if norma == 0.0:
        raise ValueError("Impossibile normalizzare un vettore nullo (Legge del Miracolo Escluso).")
    return [x / norma for x in vettore]


def similitudine_coseno(v1: List[float], v2: List[float]) -> float:
    """Computes dot product on L2-normalized vectors with strict dimension checking."""
    if len(v1) != len(v2):
        raise ValueError(f"Dimensioni vettoriali incompatibili: {len(v1)} != {len(v2)}")
    return float(sum(a * b for a, b in zip(v1, v2)))


def costruisci_testo_ancorato(dominio: str, titolo: str, sezione: str, contenuto: str) -> str:
    """Builds a hierarchically anchored chunk: [DOMAIN] Title > Section."""
    return f"[{dominio.strip().upper()}] {titolo.strip()} > {sezione.strip()}\n\n{contenuto.strip()}"


def fondi_rrf(
    lista_vettoriale: List[Dict[str, Any]],
    lista_fts_lingua: List[Dict[str, Any]],
    lista_fts_simple: List[Dict[str, Any]],
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """Pure 3-way Reciprocal Rank Fusion (RRF, K=60) with 1.3 weight on exact literal matches."""
    accumulo: Dict[int, Dict[str, Any]] = {}

    for rank, item in enumerate(lista_vettoriale, start=1):
        accumulo[item["id"]] = {**item, "rrf": PESO_VETTORIALE / (RRF_K + rank)}

    for rank, item in enumerate(lista_fts_lingua, start=1):
        if item["id"] not in accumulo:
            accumulo[item["id"]] = {**item, "rrf": 0.0}
        accumulo[item["id"]]["rrf"] += PESO_FTS_LINGUA / (RRF_K + rank)

    for rank, item in enumerate(lista_fts_simple, start=1):
        if item["id"] not in accumulo:
            accumulo[item["id"]] = {**item, "rrf": 0.0}
        accumulo[item["id"]]["rrf"] += PESO_FTS_SIMPLE / (RRF_K + rank)

    return sorted(accumulo.values(), key=lambda x: x["rrf"], reverse=True)[:top_k]


def valuta_semaforo(
    frammenti: List[Dict[str, Any]],
    s_dominio: float,
    ha_match_lessicale: bool = False,
) -> Tuple[str, float]:
    """EWD418 / EWD472 (Guarded Commands): Deterministic selection with disjoint guards."""
    if not frammenti:
        return ("ROJO", 0.0)

    sims = [float(f.get("similitudine", 0.0)) for f in frammenti]
    s_max = max(sims) if sims else 0.0
    supporto = sum(1 for s in sims if s >= TAU_BASSO)

    b_rojo = (s_dominio < TAU_DOMINIO and not ha_match_lessicale) or (
        s_max < TAU_BASSO and not ha_match_lessicale
    )
    b_verde = (not b_rojo) and (s_max >= TAU_ALTO and (supporto >= 2 or ha_match_lessicale))
    b_ambar = (not b_rojo) and (not b_verde)

    if not (b_rojo or b_verde or b_ambar):
        raise RuntimeError("Violazione EWD401: nessuna guardia vera nel costrutto IF.")

    if b_rojo:
        return ("ROJO", round(s_max, 4))
    if b_verde:
        return ("VERDE", round(s_max, 4))
    return ("AMBAR", round(s_max, 4))