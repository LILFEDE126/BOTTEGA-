#!/usr/bin/env python3
"""Layer 3 (THE): Closed-loop diagnostic solver (Zero Clutter / Zero Mucchio).
Supports any input language (EN, ES, IT, etc.) with automatic search translation,
natural-language final response synthesis and deterministic RAG fallback."""

import datetime
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Dict, List, Literal, Optional, Set, Tuple
import psycopg2
import requests
from pydantic import BaseModel, Field

from config import (
    MAX_CARATTERI_SINTESI_FALLBACK,
    MAX_CARATTERI_TURNO_DEFAULT,
    SOGLIA_S_MAX_FALLIMENTO_NORMATIVO,
    SOGLIA_S_MAX_RICERCA_EST_SUCCESSO,
    TIMEOUT_OLLAMA_SECONDS,
)
from logging_bottega import log
from grounding_numerico import (
    arrotonda_esatto_el_x8,
    classifica_nodo_tricolore,
    estrai_percentuali_decimal,
    ripara_parola_troncata,
    suddividi_in_pagine_con_continua,
    tronca_senza_spezzare_parola,
    verifica_conservazione_percentuali_decimal,
)
from presidio_concorrenza import SEGRETARIO_THE
from store_pgvector import _ARCHIVIO_MEMORIA_RAM, incasella_e_salva, recupera_con_semaforo
from client_ollama import chiama_ollama_json, rileva_lingua_testo, traduci_query_per_ricerca


RADICE_VAULT_DEFAULT = Path(__file__).resolve().parent / "wiki_vault"
PERCORSO_WIKI_DEFAULT = Path(__file__).resolve().parent / "wiki" / "bottega_llm_wiki.md"
INTESTAZIONE_WIKI_DEFAULT = "# Bottega — Gen III Personal LLM Wiki\n\n"

ENTITA_TECNICHE_NOTE = frozenset({
    "python", "pytest", "git", "github", "vscode", "vs code", "postgresql", "sql", "ast",
    "docker", "fastapi", "streamlit", "pandas", "numpy", "ollama", "gemini",
    "oic 19", "oic 34", "ifrs 16", "imu", "inail", "s&p 500", "wikipedia", "clean code",
})

_ETICHETTE_DIDATTICHE_RUMORE = frozenset({
    "parola chiave", "modulo", "nome", "espressione", "ciclo", "filtro",
    "parametro", "tipo atteso", "tipo restituito", "cosa succede", "da sapere",
    "prima", "dopo",
})

_PREFISSI_CODICE_PYTHON = (
    "def ", "return ", "for ", "if ", "elif ", "else:", "try:", "except",
    "raise ", "import ", "from ", "class ", "assert ", "@", "with ",
)

_FRASI_DISCORSIVE_SCARTO_CODICE = (
    "il codice ha uno",
    "da quale file",
    "trasforma un bug",
    "lo gestisco o lo segnalo",
    "non gestisce niente",
    "il codice peggiore",
    "storie dell'orrore",
)

_TITOLI_ORGANIZZATIVI_IGNORATI = frozenset({
    "parte 0", "giorno 0", "rompighiaccio", "quiz", "pausa", "mural",
    "ahaslides", "biglietti di uscita", "chi sono", "il corso", "gli strumenti",
    "patto d'aula", "la mappa", "lo sapevi",
})


class PianoRicercaArtigiano(BaseModel):
    stato_memoria: Literal["INSUFFICIENTE_CERCA_FUORI"] = "INSUFFICIENTE_CERCA_FUORI"
    fatti_accertati_nel_problema: List[str] = Field(
        description="Objective facts stated in the request, with zero assumptions"
    )
    dato_esatto_mancante: str = Field(
        description="The single technical, regulatory or physical datum missing to satisfy wp(S, R)"
    )
    query_chirurgica_esterna: str = Field(
        description="Exact search query to run on official documentation, DB or technical handbook"
    )
    ispezione_preliminare_sul_campo: str = Field(
        description="What to measure or inspect physically before touching any component"
    )


class SoluzioneArtigiano(BaseModel):
    stato_memoria: Literal["SOLUZIONE_FONDATA"] = "SOLUZIONE_FONDATA"
    risposta_finale_discorsiva: str = Field(
        default="",
        description="Clear, complete, natural-language final answer written normally for a non-technical reader, directly answering the question using only the verified numbers from the context",
    )
    principio_guida_unico: str = Field(
        description="The SINGLE rule or source selected among retrieved fragments to solve the case"
    )
    elementi_scartati_per_non_fare_mucchio: List[str] = Field(
        description="Retrieved fragments or field-falsified hypotheses explicitly discarded to avoid clutter"
    )
    precondizione_wp_richiesta: str = Field(
        description="EWD401: Weakest precondition wp(S, R) that must hold before acting"
    )
    invariante_violato: str = Field(
        description="Which conservation equilibrium (pressure, accounting balance, data state) broke"
    )
    ipotesi_causale_unica: str = Field(
        description="The SINGLE simplest root cause (Strato L Principle of Necessity)"
    )
    azione_correttiva_singola: str = Field(
        description="The single targeted intervention to execute step-by-step without mixing alternatives"
    )
    esperimento_di_verifica_pratica: str = Field(
        description="How to objectively measure whether postcondition R is satisfied"
    )


_ETICHETTE_FALSIFICATA = MappingProxyType({
    "en": "[Falsified in the field]",
    "es": "[Falsificada en el campo]",
    "it": "[Falsificata sul campo]",
})

_ETICHETTE_SCARTATO = MappingProxyType({
    "en": "[Discarded for Zero Clutter]",
    "es": "[Descartado por Cero Montón]",
    "it": "[Scartato per Zero Mucchio]",
})


def _istruzione_lingua_tassativa(lingua: str) -> str:
    """Returns a strict single-language enforcement block for the LLM prompt."""
    if lingua == "en":
        return (
            "MANDATORY LANGUAGE LOCK (100% ENGLISH ONLY): The user asked in ENGLISH. "
            "Even if the retrieved source fragments below are written in Italian or Spanish, "
            "you MUST translate and write EVERY SINGLE JSON field ('risposta_finale_discorsiva', "
            "'principio_guida_unico', 'elementi_scartati_per_non_fare_mucchio', 'precondizione_wp_richiesta', "
            "'invariante_violato', 'ipotesi_causale_unica', 'azione_correttiva_singola', "
            "'esperimento_di_verifica_pratica') ENTIRELY IN ENGLISH. Do NOT leave Italian or Spanish sentences "
            "in 'principio_guida_unico' or 'elementi_scartati_per_non_fare_mucchio': translate them into English "
            "while keeping all numbers, percentages, and amounts identical."
        )
    if lingua == "es":
        return (
            "BLOQUEO DE IDIOMA OBLIGATORIO (100% ESPAÑOL ÚNICAMENTE): El usuario preguntó en ESPAÑOL. "
            "Aunque los fragmentos recuperados abajo estén escritos en italiano o inglés, "
            "DEBES traducir y redactar ABSOLUTAMENTE TODOS los campos del JSON ('risposta_finale_discorsiva', "
            "'principio_guida_unico', 'elementi_scartati_per_non_fare_mucchio', 'precondizione_wp_richiesta', "
            "'invariante_violato', 'ipotesi_causale_unica', 'azione_correttiva_singola', "
            "'esperimento_di_verifica_pratica') ÍNTEGRAMENTE EN ESPAÑOL. PROHIBIDO dejar frases en italiano "
            "en 'principio_guida_unico' o 'elementi_scartati_per_non_fare_mucchio': tradúcelas al español "
            "(por ejemplo traduce siempre 'attualizzarsi/attualizzazione' -> 'actualizarse/actualización', "
            "'scadenza' -> 'vencimiento', 'tasso di interesse' -> 'tipo de interés', 'scarso rilievo' -> 'escasa importancia') "
            "manteniendo idénticos todos los números, porcentajes e importes."
        )
    return (
        "VINCOLO TASSATIVO DI LINGUA (100% ITALIANO): L'utente ha scritto in ITALIANO. "
        "Scrivi ogni singolo campo del JSON interamente in lingua ITALIANA, mantenendo identiche "
        "tutte le cifre, percentuali e importi del contesto."
    )


def formatta_risposta_artigiano_leggibile(
    risultato_dict: dict,
    modalita: str,
    lingua: str = "it",
) -> str:
    """Formats the structured Pydantic output into a 100% single-language human-readable Markdown response."""
    if modalita == "RICERCA_PRIMA_DI_AGIRE":
        fatti = "\n".join(f"- {f}" for f in risultato_dict.get("fatti_accertati_nel_problema", []))
        if lingua == "en":
            return (
                "### Honest Stop (ROJO Semaphore — Insufficient Data in Memory)\n\n"
                "To avoid inventing figures or guessing at random, the system stopped before answering:\n\n"
                f"**Confirmed facts in the request:**\n{fatti or '- No additional datum'}\n\n"
                f"**Exact missing datum:** {risultato_dict.get('dato_esatto_mancante', '')}\n\n"
                f"**Recommended surgical search:** `{risultato_dict.get('query_chirurgica_esterna', '')}`\n\n"
                f"**Preliminary field inspection:** {risultato_dict.get('ispezione_preliminare_sul_campo', '')}"
            )
        if lingua == "es":
            return (
                "### Parada Honesta (Semáforo ROJO — Datos Insuficientes en Memoria)\n\n"
                "Para no inventar cifras ni hacer suposiciones al azar, el sistema se detuvo antes de responder:\n\n"
                f"**Hechos confirmados en la solicitud:**\n{fatti or '- Ningún dato adicional'}\n\n"
                f"**Dato exacto faltante:** {risultato_dict.get('dato_esatto_mancante', '')}\n\n"
                f"**Búsqueda quirúrgica recomendada:** `{risultato_dict.get('query_chirurgica_esterna', '')}`\n\n"
                f"**Inspección preliminar a realizar:** {risultato_dict.get('ispezione_preliminare_sul_campo', '')}"
            )
        return (
            "### Stop Onesto (Semaforo ROJO — Dati Insufficienti in Memoria)\n\n"
            "Per non inventare cifre o fare ipotesi a caso, il sistema si e' fermato prima di rispondere:\n\n"
            f"**Fatti accertati nella richiesta:**\n{fatti or '- Nessun dato aggiuntivo'}\n\n"
            f"**Dato esatto mancante:** {risultato_dict.get('dato_esatto_mancante', '')}\n\n"
            f"**Ricerca consigliata:** `{risultato_dict.get('query_chirurgica_esterna', '')}`\n\n"
            f"**Verifica preliminare da eseguire:** {risultato_dict.get('ispezione_preliminare_sul_campo', '')}"
        )

    discorsiva = (risultato_dict.get("risposta_finale_discorsiva") or "").strip()
    principio = risultato_dict.get("principio_guida_unico", "")
    causa = risultato_dict.get("ipotesi_causale_unica", "")
    azione = risultato_dict.get("azione_correttiva_singola", "")
    verifica = risultato_dict.get("esperimento_di_verifica_pratica", "")
    precond = risultato_dict.get("precondizione_wp_richiesta", "")
    invariante = risultato_dict.get("invariante_violato", "")
    scarti = risultato_dict.get("elementi_scartati_per_non_fare_mucchio", [])

    intro = f"{discorsiva}\n\n---\n\n" if discorsiva else ""
    if lingua == "en":
        scarti_md = "\n".join(f"- {s}" for s in scarti) if scarti else "- No spurious elements detected."
        return (
            f"{intro}"
            f"**1. Main Answer & Root Diagnosis:**\n{causa}\n\n"
            f"**2. Practical Action to Take (Recommended Step):**\n{azione}\n\n"
            f"**3. Official Rule / Source Applied (Zero Clutter):**\n{principio}\n\n"
            f"**4. Practical Verification Check:**\n{verifica}\n\n"
            f"**5. Starting Precondition & Equilibrium:**\n- *Precondition:* {precond}\n- *Constraint:* {invariante}\n\n"
            f"**6. Excluded Items or Hypotheses (Anti-Clutter Filter):**\n{scarti_md}"
        )
    if lingua == "es":
        scarti_md = "\n".join(f"- {s}" for s in scarti) if scarti else "- Ningún elemento espurio detectado."
        return (
            f"{intro}"
            f"**1. Respuesta y Diagnóstico Principal:**\n{causa}\n\n"
            f"**2. Qué Hacer en la Práctica (Acción Recomendada):**\n{azione}\n\n"
            f"**3. Regla / Fuente Oficial Aplicada (Cero Montón):**\n{principio}\n\n"
            f"**4. Verificación Práctica de Control:**\n{verifica}\n\n"
            f"**5. Condición de Partida y Equilibrio:**\n- *Precondición:* {precond}\n- *Vínculo:* {invariante}\n\n"
            f"**6. Elementos o Hipótesis Excluidas (para no mezclar soluciones):**\n{scarti_md}"
        )

    scarti_md = "\n".join(f"- {s}" for s in scarti) if scarti else "- Nessun elemento spurio rilevato."
    return (
        f"{intro}"
        f"**1. Risposta e Diagnosi Principale:**\n{causa}\n\n"
        f"**2. Cosa Fare in Pratica (Azione Consigliata):**\n{azione}\n\n"
        f"**3. Regola / Fonte Ufficiale Applicata (Zero Mucchio):**\n{principio}\n\n"
        f"**4. Verifica Pratica di Controllo:**\n{verifica}\n\n"
        f"**5. Condizione di Partenza ed Equilibrio:**\n- *Precondizione:* {precond}\n- *Vincolo:* {invariante}\n\n"
        f"**6. Voci o Ipotesi Escluse (per non mescolare soluzioni):**\n{scarti_md}"
    )


def rimuovi_coda_audit_6_punti(testo: str) -> str:
    """Removes the 6-point technical audit boilerplate from user-facing main answer pages,
    keeping only the clean documentary explanation and verified code blocks."""
    if not testo:
        return ""
    marcatori_taglio = (
        "\n---\n\n**1. Risposta e Diagnosi Principale:**",
        "\n**1. Risposta e Diagnosi Principale:**",
        "1. Risposta e Diagnosi Principale:",
        "\n---\n\n**1. Main Answer & Root Diagnosis:**",
        "\n**1. Main Answer & Root Diagnosis:**",
        "1. Main Answer & Root Diagnosis:",
        "\n---\n\n**1. Respuesta y Diagnóstico Principal:**",
        "\n**1. Respuesta y Diagnóstico Principal:**",
        "1. Respuesta y Diagnóstico Principal:",
    )
    risultato = testo
    for m in marcatori_taglio:
        if m in risultato:
            risultato = risultato.split(m, 1)[0].strip()
    if re.match(
        r"^\s*\**[1-6]\.\s+(?:Verifica Pratica|Condizione di Partenza|Voci o Ipotesi|Practical Verification|Starting Precondition|Excluded Items|Risposta e Diagnosi|Main Answer|Respuesta)",
        risultato,
    ):
        return ""
    return risultato.strip()


def _costruisci_piano_deterministico(problema: str, lingua: str = "it") -> PianoRicercaArtigiano:
    """Builds a deterministic research plan when the external LLM is unreachable on ROJO semaphore."""
    testo_pulito = problema.strip()
    if lingua == "en":
        return PianoRicercaArtigiano(
            fatti_accertati_nel_problema=[testo_pulito],
            dato_esatto_mancante=f"Official documentary source for: {testo_pulito}",
            query_chirurgica_esterna=traduci_query_per_ricerca(testo_pulito),
            ispezione_preliminare_sul_campo=(
                "Verify the original document in the archive or acquire the official technical specification before acting."
            ),
        )
    if lingua == "es":
        return PianoRicercaArtigiano(
            fatti_accertati_nel_problema=[testo_pulito],
            dato_esatto_mancante=f"Fuente documental oficial para: {testo_pulito}",
            query_chirurgica_esterna=traduci_query_per_ricerca(testo_pulito),
            ispezione_preliminare_sul_campo=(
                "Verificar el documento original en el archivo o adquirir la especificación técnica oficial antes de actuar."
            ),
        )
    return PianoRicercaArtigiano(
        fatti_accertati_nel_problema=[testo_pulito],
        dato_esatto_mancante=f"Fonte documentale ufficiale per: {testo_pulito}",
        query_chirurgica_esterna=traduci_query_per_ricerca(testo_pulito),
        ispezione_preliminare_sul_campo=(
            "Verificare il documento originale nell'archivio o acquisire la specifica tecnica ufficiale prima di agire."
        ),
    )


MAX_CARATTERI_ETICHETTA_DEFAULT: int = 180
MAX_CARATTERI_SCARTO_DEFAULT: int = 160


def _sintetizza_etichetta_frammento(testo_frammento: str, max_len: int = MAX_CARATTERI_ETICHETTA_DEFAULT) -> str:
    """Extracts a clean, concise title/summary from a long RAG fragment to avoid repeating 3,500-char dumps."""
    compatto = " ".join(testo_frammento.strip().split())
    if len(compatto) <= max_len:
        return compatto
    return tronca_senza_spezzare_parola(compatto, max_len, suffisso="...")


_REGISTRO_CONTINUAZIONI_MEMORIA: dict[str, List[str]] = {}


def e_richiesta_continua(testo: str) -> bool:
    """Checks whether the input query is an explicit continuation command."""
    testo_pulito = testo.strip().lower().rstrip(".!?:;,")
    return testo_pulito in (
        "continua",
        "continue",
        "continúa",
        "continua per favore",
        "prosegui",
        "adelante",
        "next",
        "avanti",
    )


def imposta_pagine_continua(dominio: str, pagine: List[str]) -> None:
    """Saves subsequent continuation pages in memory for sequential retrieval."""
    with SEGRETARIO_THE.sezione_sacra(dominio or "generale"):
        _REGISTRO_CONTINUAZIONI_MEMORIA[dominio] = list(pagine)
        _REGISTRO_CONTINUAZIONI_MEMORIA["__ultimo__"] = list(pagine)


def estrai_prossima_pagina_continua(dominio: str = "generale") -> Optional[str]:
    """Pops and returns the next continuation page, or None if no pages are pending."""
    with SEGRETARIO_THE.sezione_sacra(dominio or "generale"):
        coda = _REGISTRO_CONTINUAZIONI_MEMORIA.get(dominio)
        if not coda:
            coda = _REGISTRO_CONTINUAZIONI_MEMORIA.get("__ultimo__")
        if not coda:
            return None
        pagina = coda.pop(0)
        _REGISTRO_CONTINUAZIONI_MEMORIA["__ultimo__"] = coda
        return pagina


def ha_pagine_continua_in_sospeso(dominio: str = "generale") -> bool:
    """Returns True if there are remaining continuation pages waiting for the user."""
    with SEGRETARIO_THE.sezione_sacra(dominio or "generale"):
        coda = _REGISTRO_CONTINUAZIONI_MEMORIA.get(dominio) or _REGISTRO_CONTINUAZIONI_MEMORIA.get("__ultimo__")
        return bool(coda)


def conta_pagine_continua_rimanenti(dominio: str = "generale") -> int:
    """Returns number of remaining continuation pages in queue."""
    with SEGRETARIO_THE.sezione_sacra(dominio or "generale"):
        coda = _REGISTRO_CONTINUAZIONI_MEMORIA.get(dominio) or _REGISTRO_CONTINUAZIONI_MEMORIA.get("__ultimo__")
        return len(coda) if coda else 0


def svuota_pagine_continua(dominio: Optional[str] = None) -> None:
    """Clears pending continuation pages from memory."""
    with SEGRETARIO_THE.sezione_sacra(dominio or "generale"):
        if dominio is None:
            _REGISTRO_CONTINUAZIONI_MEMORIA.clear()
        else:
            _REGISTRO_CONTINUAZIONI_MEMORIA.pop(dominio, None)


def _ripulisci_prefisso_tecnico_frammento(testo: str) -> str:
    """Strips technical metadata header like [TAG] Title > Section from fragment text."""
    if not testo:
        return ""
    testo_pulito = testo.strip()
    testo_pulito = re.sub(r"^\[[A-Za-z0-9_-]+\]\s*[^>\n]+>[^\n]*\n*", "", testo_pulito)
    return testo_pulito.strip()


def _e_riga_codice_python(riga: str) -> bool:
    r_strip = riga.strip()
    r_lower = r_strip.lower()
    if any(frase in r_lower for frase in _FRASI_DISCORSIVE_SCARTO_CODICE):
        return False
    if r_strip.startswith("from ") or r_strip.startswith("import "):
        if ":" in r_strip:
            return False
        if re.match(r"^from\s+[a-z_][a-z0-9_.]*\s+import\s+[a-zA-Z_*]", r_strip):
            return True
        if re.match(r"^import\s+[a-z_][a-z0-9_.,\s]*$", r_strip):
            return True
        return False
    if not (any(c in r_strip for c in ("=", "(", ":")) or r_strip.startswith(("return ", "yield ", "raise ", "pass"))):
        return False
    if any(r_strip.startswith(p) for p in _PREFISSI_CODICE_PYTHON):
        return True
    if r_strip in ("else:", "try:", "finally:", "except:"):
        return True
    if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*.+$", r_strip):
        return True
    return False


def _sintetizza_blocchi_in_markdown_pulito(problema: str, frammenti: List[dict]) -> str:
    """Synthesizes key operational points, rules, headings, and numerical constraints
    from retrieved RAG fragments into clean, structured Markdown, eliminating raw repetition and noise."""
    if not frammenti:
        return problema.strip()

    titolo_guida = (frammenti[0].get("titolo", "") or "").strip()
    slug_guida = _estrai_slug_fonte_da_frammento(frammenti[0].get("testo", "")) if not titolo_guida else ""
    frammenti_stesso_doc = []
    for f in frammenti:
        f_tit = (f.get("titolo", "") or "").strip()
        f_sl = _estrai_slug_fonte_da_frammento(f.get("testo", "")) if not f_tit else ""
        if titolo_guida:
            if f_tit == titolo_guida:
                frammenti_stesso_doc.append(f)
        elif slug_guida:
            if f_sl == slug_guida:
                frammenti_stesso_doc.append(f)
        else:
            frammenti_stesso_doc.append(f)

    if not frammenti_stesso_doc:
        frammenti_stesso_doc = frammenti

    righe_sintesi: List[str] = []
    viste: Set[str] = set()
    sezioni_trovate: List[str] = []
    codice_trovato: List[str] = []

    for frammento in frammenti_stesso_doc[:4]:
        testo = _ripulisci_prefisso_tecnico_frammento(frammento.get("testo", "")).strip()
        if not testo:
            continue

        righe_grezze = [r.rstrip() for r in testo.splitlines() if r.strip()]
        righe_ricongiunte: List[str] = []
        for r in righe_grezze:
            r_pulita = r.strip()
            if not r_pulita:
                continue
            r_lower = r_pulita.lower()
            if any(r_lower.startswith(pref) for pref in ("cp ", "touch ", "rm ", "cd ", "mkdir ", "chmod ", "git ")):
                continue
            if r_pulita in ("pass", "...", "return None"):
                continue
            if r_lower in _ETICHETTE_DIDATTICHE_RUMORE:
                continue

            if (
                righe_ricongiunte
                and not _e_riga_codice_python(r)
                and not _e_riga_codice_python(righe_ricongiunte[-1])
                and not righe_ricongiunte[-1].endswith((".", "!", "?", ":", ";"))
                and not r_pulita.startswith("#")
                and not re.match(r"^(?:regola|tappa|fase|passo)\s+\d+", r_lower)
                and (r_pulita[0].islower() or (len(righe_ricongiunte[-1]) < 50 and not righe_ricongiunte[-1].startswith("-")))
            ):
                righe_ricongiunte[-1] = f"{righe_ricongiunte[-1]} {r_pulita}"
            else:
                righe_ricongiunte.append(r)

        for riga in righe_ricongiunte:
            riga_strip = riga.strip()
            riga_lower = riga_strip.lower()
            chiave_normalizzata = " ".join(riga_lower.split())
            if chiave_normalizzata in viste:
                continue
            viste.add(chiave_normalizzata)

            if _e_riga_codice_python(riga):
                riga_cod = riga
                riga_cod = re.sub(r"(\d)([A-Z_]{3,}\s*=)", r"\1\n\2", riga_cod)
                riga_cod = re.sub(r"(\b[a-zA-Z_]{3,})(\1\s*=)", r"\1\n\2", riga_cod)
                riga_cod = re.sub(r"(\breturn\s+[a-zA-Z_]\w*?)([a-zA-Z_]\w*\s*=)", r"\1\n\2", riga_cod)
                riga_cod = re.sub(r":\s*(?=(?:def |for |if |elif |else:|try:|except|return |raise |[a-zA-Z_]\w*\s*=))", ":\n    ", riga_cod)
                riga_cod = re.sub(r"(?<=[}\])\w])\s*(for\s+[a-zA-Z_]\w*\s+in\s+)", r"\n\1", riga_cod)
                for sub_r in riga_cod.splitlines():
                    sub_pulita = sub_r.rstrip()
                    if sub_pulita.strip() and sub_pulita not in codice_trovato:
                        codice_trovato.append(sub_pulita)
            else:
                if riga_strip.startswith("#"):
                    sezioni_trovate.append(riga_strip)
                elif len(riga_strip) <= 80 and re.match(
                    r"^(?:\[?(?:page|pagina|slide|sezione|par(?:agrafo)?)\s*\d+\]?|codice pulito|regola\s*\d+|linee guida)",
                    riga_lower,
                ):
                    sezioni_trovate.append(f"### {riga_strip.lstrip('#').strip()}")
                elif re.match(r"^(?:\d{1,2}[.)\-:]|\*|\-|\u2022)\s+", riga_strip):
                    contenuto = re.sub(r"^(?:\d{1,2}[.)\-:]|\*|\-|\u2022)\s+", "", riga_strip).strip()
                    if len(contenuto) < 80:
                        righe_sintesi.append(f"- **{contenuto}**")
                    else:
                        righe_sintesi.append(f"- {contenuto}")
                elif re.match(
                    r"^(?:prima|dopo|regola\s*\d+|fase\s*\d+|passo\s*\d+|warning|nota|attenzione)\s*[:\-]",
                    riga_lower,
                ):
                    righe_sintesi.append(f"- **{riga_strip}**")
                elif ":" in riga_strip and len(riga_strip.split(":", 1)[0]) <= 35:
                    parti = riga_strip.split(":", 1)
                    righe_sintesi.append(f"- **{parti[0].strip()}:** {parti[1].strip()}")
                else:
                    righe_sintesi.append(f"- {riga_strip}")

    parti_output: List[str] = []
    if sezioni_trovate:
        parti_output.append("\n\n".join(sezioni_trovate[:3]))

    if righe_sintesi:
        parti_output.append("### Prescrizioni e Regole Operative Certificate\n" + "\n".join(righe_sintesi))

    if codice_trovato:
        parti_output.append("### Esempi di Codice Verificati\n```python\n" + "\n".join(codice_trovato) + "\n```")

    if not parti_output:
        testi_base = [_ripulisci_prefisso_tecnico_frammento(f.get("testo", "")) for f in frammenti[:3]]
        return "\n\n---\n\n".join(t for t in testi_base if t) or problema.strip()

    return "\n\n".join(parti_output)


def _costruisci_soluzione_deterministica(
    problema: str,
    frammenti: List[dict],
    escluse_pulite: List[str],
    lingua: str = "it",
) -> SoluzioneArtigiano:
    """Synthesizes a strictly grounded SoluzioneArtigiano directly from retrieved RAG fragments
    when the external LLM provider is offline or rate-limited, preserving all exact source numbers."""
    titolo_guida = (frammenti[0].get("titolo", "") or "").strip() if frammenti else ""
    slug_guida = _estrai_slug_fonte_da_frammento(frammenti[0].get("testo", "")) if frammenti and not titolo_guida else ""
    frammenti_stesso_doc = []
    frammenti_scartati_altro_doc = []
    for f in (frammenti or []):
        f_tit = (f.get("titolo", "") or "").strip()
        f_sl = _estrai_slug_fonte_da_frammento(f.get("testo", "")) if not f_tit else ""
        if titolo_guida:
            if f_tit == titolo_guida:
                frammenti_stesso_doc.append(f)
            else:
                frammenti_scartati_altro_doc.append(f)
        elif slug_guida:
            if f_sl == slug_guida:
                frammenti_stesso_doc.append(f)
            else:
                frammenti_scartati_altro_doc.append(f)
        else:
            frammenti_stesso_doc.append(f)

    pertinenti_raw = frammenti_stesso_doc[:4] if frammenti_stesso_doc else []
    pertinenti_testi = [_ripulisci_prefisso_tecnico_frammento(f["testo"]) for f in pertinenti_raw]
    pertinenti_testi = [t for t in pertinenti_testi if t]

    risposta_finale = _sintetizza_blocchi_in_markdown_pulito(problema, frammenti_stesso_doc)

    primo_testo = pertinenti_testi[0] if pertinenti_testi else problema.strip()
    principale_breve = _sintetizza_etichetta_frammento(primo_testo, max_len=MAX_CARATTERI_SINTESI_FALLBACK)
    tag_scarto = _ETICHETTE_SCARTATO.get(lingua, _ETICHETTE_SCARTATO["it"])
    tag_fals = _ETICHETTE_FALSIFICATA.get(lingua, _ETICHETTE_FALSIFICATA["it"])

    frammenti_rimanenti = frammenti_stesso_doc[len(pertinenti_raw):] + frammenti_scartati_altro_doc
    scartati = [
        f"{tag_scarto} {_sintetizza_etichetta_frammento(frammento['testo'], max_len=MAX_CARATTERI_SCARTO_DEFAULT)}"
        for frammento in frammenti_rimanenti
    ]
    for ipotesi_esclusa in escluse_pulite:
        scartati.append(f"{tag_fals} {ipotesi_esclusa}")

    if lingua == "en":
        return SoluzioneArtigiano(
            risposta_finale_discorsiva=risposta_finale,
            principio_guida_unico=principale_breve,
            elementi_scartati_per_non_fare_mucchio=scartati,
            precondizione_wp_richiesta=(
                "Verification and direct matching against certified technical archive references and constraints."
            ),
            invariante_violato=(
                "Ensure strict adherence to certified parameters, specifications, and rules from the source archive."
            ),
            ipotesi_causale_unica=f"Priority documentary reference: {principale_breve}",
            azione_correttiva_singola=(
                "Apply the verified operating steps, formulas, and parameters documented in the certified source."
            ),
            esperimento_di_verifica_pratica=(
                "Verify exact correspondence of each parameter, figure, and rule with the source documentation."
            ),
        )
    if lingua == "es":
        return SoluzioneArtigiano(
            risposta_finale_discorsiva=risposta_finale,
            principio_guida_unico=principale_breve,
            elementi_scartati_per_non_fare_mucchio=scartati,
            precondizione_wp_richiesta=(
                "Verificación y contraste directo con las referencias y límites del archivo técnico certificado."
            ),
            invariante_violato=(
                "Garantizar la estricta coherencia con los parámetros, especificaciones y reglas de la fuente documental."
            ),
            ipotesi_causale_unica=f"Referencia documental prioritaria: {principale_breve}",
            azione_correttiva_singola=(
                "Aplicar con fidelidad los pasos operativos, fórmulas y parámetros certificados en la documentación."
            ),
            esperimento_di_verifica_pratica=(
                "Comprobar la correspondencia exacta de cada parámetro, cifra y regla con la documentación de origen."
            ),
        )
    return SoluzioneArtigiano(
        risposta_finale_discorsiva=risposta_finale,
        principio_guida_unico=principale_breve,
        elementi_scartati_per_non_fare_mucchio=scartati,
        precondizione_wp_richiesta=(
            "Verifica e riscontro documentale sui riferimenti e sui vincoli dell'archivio tecnico certificato."
        ),
        invariante_violato=(
            "Mantenere piena aderenza ai parametri, alle specifiche e alle regole stabilite nel testo d'archivio."
        ),
        ipotesi_causale_unica=f"Estratto documentale prioritario: {principale_breve}",
        azione_correttiva_singola=(
            "Applicare fedelmente le prescrizioni, le formule e i passaggi operativi documentati nella fonte certificata."
        ),
        esperimento_di_verifica_pratica=(
            "Controllare la corrispondenza puntuale di ciascun parametro, valore numerico e specifica con la documentazione d'origine."
        ),
    )


def genera_prompt_ponte_web_gratuito(
    problema: str,
    frammenti_contesto: List[Tuple[str, str]],
    ipotesi_gia_escluse: Optional[List[str]] = None,
) -> str:
    """Builds the structured 'Zero Mucchio' prompt for free browser chats (ChatGPT, DeepSeek, Gemini)
    instructing the model to reply in the exact same language used by the user."""
    contesto_str = "\n".join(
        f"[Frammento {i} - {tit}] {testo}"
        for i, (tit, testo) in enumerate(frammenti_contesto, start=1)
    )
    blocco_escluse = ""
    if ipotesi_gia_escluse:
        escluse_str = "\n".join(f"- {ip}" for ip in ipotesi_gia_escluse if ip.strip())
        if escluse_str:
            blocco_escluse = (
                "\n\nIPOTESI GIA' FALSIFICATE SUL CAMPO (VIETATO RIPROPORLE COME CAUSA):\n"
                f"{escluse_str}"
            )

    return (
        "Agisci come un ingegnere diagnostico rigoroso (Architettura Strato L + Strato A + Strato D — wp(S, R)).\n"
        "LINGUA / LANGUAGE / IDIOMA: Rispondi nella STESSA LINGUA usata nel PROBLEMA qui sotto "
        "(Reply in the exact same language used in the problem below: English, Español, Italiano, etc.).\n"
        "REGOLE TASSATIVE:\n"
        "1. NON FARE MUCCHIO (ZERO CLUTTER): Scegli UN SOLO principio guida dal contesto qui sotto e dichiara "
        "esplicitamente quali altri frammenti o ipotesi hai scartato.\n"
        "2. ZERO CIFRE INVENTATE: Ogni numero, percentuale, importo o parametro che scrivi DEVE esistere "
        "identico nel Contesto o nel Problema qui sotto.\n"
        "3. STRUTTURA OBBLIGATORIA DELLA RISPOSTA:\n"
        "   - Principio guida scelto / Selected guiding principle:\n"
        "   - Elementi scartati / Discarded elements:\n"
        "   - Precondizione wp(S, R) ed equilibrio violato:\n"
        "   - Unica ipotesi causale radice / Single root cause:\n"
        "   - Unica azione correttiva / Single corrective action:\n"
        "   - Esperimento pratico di verifica / Verification experiment:\n\n"
        f"CONTESTO TECNICO CERTIFICATO:\n{contesto_str or 'Nessun frammento disponibile.'}\n\n"
        f"PROBLEMA DA RISOLVERE:\n{problema.strip()}{blocco_escluse}"
    )


_SPIE_DATO_ASSENTE_NEI_FRAMMENTI = (
    "non è presente alcun riferimento",
    "non e' presente alcun riferimento",
    "non è possibile formulare una risposta",
    "impossibilità di rispondere",
    "impossibilita' di rispondere",
    "omettendo totalmente",
    "estranei alla norma",
    "trattano esclusivamente argomenti di",
    "trattano esclusivamente di",
    "trattano esclusivamente",
    "non contengono informazioni",
    "non disponiamo di informazioni",
    "mancanza totale di dati",
    "non è possibile formulare alcuna previsione",
    "non e' possibile formulare alcuna previsione",
    "non contengono dati",
    "nessuna informazione disponibile",
    "no reference to",
    "not present in the retrieved",
    "impossible to answer",
    "no contiene ninguna referencia",
    "imposibilidad de responder",
)

_STOPWORDS_CHIRURGICHE = frozenset({
    "qual", "quale", "quali", "cosa", "come", "dove", "quando", "perche", "perché",
    "del", "della", "delle", "degli", "dello", "dei", "dal", "dalla", "dalle",
    "nel", "nella", "nelle", "negli", "nello", "nei", "con", "per", "tra", "fra",
    "questo", "questa", "questi", "queste", "quello", "quella", "che", "chi",
    "preciso", "precisione", "sfidato", "sfidati", "sfida", "hanno", "dire", "sai",
    "parte", "parti", "prossimi", "prossimo", "prossima", "prossime", "andamento",
    "anni", "anno", "mesi", "mese", "giorni", "due", "tre", "puoi", "dimmi", "sapere",
    "vorrei", "the", "and", "for", "with", "from", "into", "that", "this", "what",
    "which", "para", "como", "desde", "hasta", "sobre", "entre", "cual", "cuál",
})


def _estrai_termini_chiave_chirurgici(query_testo: str) -> Set[str]:
    testo_norm = re.sub(r"(?i)\b(?:s&p|sp)\s*500\b", "s&p 500", query_testo.lower())
    token_lista = re.findall(r"s&p\s+500|\bs&p\b|\b\d+(?:[.,/-]\d+)*\b|[a-z0-9à-ÿ&]{2,}", testo_norm)
    termini = set()
    for tok in token_lista:
        tok_pulito = tok.strip()
        if tok_pulito in _STOPWORDS_CHIRURGICHE:
            continue
        if len(tok_pulito) < 3 and not any(ch.isdigit() for ch in tok_pulito) and tok_pulito not in ("sp", "s&p"):
            continue
        termini.add(tok_pulito)
        if tok_pulito in ("s&p 500", "sp 500"):
            termini.update(["s&p", "sp", "500"])
    return termini


def _verifica_pertinenza_blocchi_esterni(
    blocchi: List[Tuple[str, str]],
    query_riferimento: str,
) -> bool:
    """Verifica che i blocchi restituiti dalla ricerca esterna contengano almeno un termine chiave della query chirurgica."""
    if not blocchi:
        return False
    termini = _estrai_termini_chiave_chirurgici(query_riferimento)
    if not termini:
        return True
    testo_unito = " ".join(f"{sez} {txt}" for sez, txt in blocchi).lower()
    parole_blocchi = set(re.findall(r"[a-z0-9&/]+", testo_unito))
    for t in termini:
        if " " in t:
            if t in testo_unito:
                return True
        else:
            if t in parole_blocchi or f" {t} " in f" {testo_unito} ":
                return True
    return False


def _rileva_rifiuto_per_frammenti_non_pertinenti(soluzione: SoluzioneArtigiano) -> bool:
    """Detects when the LLM explicitly states that the retrieved fragments do not cover the user's topic."""
    testo_check = (
        f"{soluzione.risposta_finale_discorsiva} "
        f"{soluzione.ipotesi_causale_unica} "
        f"{soluzione.azione_correttiva_singola}"
    ).lower()
    return any(spia in testo_check for spia in _SPIE_DATO_ASSENTE_NEI_FRAMMENTI)


_INDICE_ULTIMO_BLOCCO_LETTO_RAM: Dict[str, int] = {}


def approfondisci_sezioni_successive_documento(dominio: str = "generale") -> Optional[str]:
    """Extracts and synthesizes subsequent unread blocks from the active document in RAM archive."""
    if not _ARCHIVIO_MEMORIA_RAM:
        return None
    frammenti_dominio = [
        item for item in _ARCHIVIO_MEMORIA_RAM
        if item.get("dominio") == dominio and not str(item.get("titolo", "")).startswith("Ricerca:")
    ]
    if not frammenti_dominio:
        frammenti_dominio = [
            item for item in _ARCHIVIO_MEMORIA_RAM
            if not str(item.get("titolo", "")).startswith("Ricerca:")
        ]
    if not frammenti_dominio:
        return None
    titolo_attivo = frammenti_dominio[0].get("titolo", "")
    blocchi_doc = [item for item in frammenti_dominio if item.get("titolo") == titolo_attivo]
    if not blocchi_doc:
        return None
    indice_corrente = _INDICE_ULTIMO_BLOCCO_LETTO_RAM.get(dominio, 4)
    if indice_corrente >= len(blocchi_doc):
        return None
    blocchi_succ = blocchi_doc[indice_corrente : indice_corrente + 4]
    _INDICE_ULTIMO_BLOCCO_LETTO_RAM[dominio] = indice_corrente + 4
    if not blocchi_succ:
        return None
    return _sintetizza_blocchi_in_markdown_pulito("Approfondimento sezioni successive", blocchi_succ)


def _intercetta_e_eroga_continua(problema: str, dominio: str, lingua_rilevata: str) -> Optional[dict]:
    """Se la richiesta e' un comando di continuazione, eroga la pagina successiva o notifica di esaurimento."""
    if not e_richiesta_continua(problema):
        return None
    prossima_pagina = estrai_prossima_pagina_continua(dominio)
    if prossima_pagina is not None:
        ancora_in_sospeso = ha_pagine_continua_in_sospeso(dominio)
        pagine_rim = conta_pagine_continua_rimanenti(dominio)
        testo_erogato = ripara_parola_troncata(prossima_pagina)
        return {
            "semaforo": "VERDE",
            "s_max": 1.0,
            "modalita": "CONTINUAZIONE_TESTO",
            "lingua": lingua_rilevata,
            "ricerca_esterna_eseguita": False,
            "ipotesi_escluse_applicate": [],
            "colore_nodo_ewd496a": "NERO",
            "percentuali_conservate": True,
            "in_sospeso": ancora_in_sospeso,
            "pagine_rimanenti": pagine_rim,
            "risultato": {
                "stato": "CONTINUAZIONE",
                "testo": testo_erogato,
                "risposta_finale_discorsiva": testo_erogato,
                "in_sospeso": ancora_in_sospeso,
            },
            "risposta_discorsiva": testo_erogato,
            "frammenti_usati": [],
            "cifre_non_ancorate": [],
            "sintesi_deterministica_attiva": False,
        }
    if _ARCHIVIO_MEMORIA_RAM:
        approfondimento = approfondisci_sezioni_successive_documento(dominio)
        if approfondimento:
            pagine_nuove = suddividi_in_pagine_con_continua(
                approfondimento, max_caratteri_pagina=MAX_CARATTERI_TURNO_DEFAULT
            )
            if len(pagine_nuove) > 1:
                imposta_pagine_continua(dominio, pagine_nuove[1:])
                testo_erogato = pagine_nuove[0]
            else:
                testo_erogato = pagine_nuove[0]
            ancora_in_sospeso = ha_pagine_continua_in_sospeso(dominio)
            pagine_rim = conta_pagine_continua_rimanenti(dominio)
            return {
                "semaforo": "VERDE",
                "s_max": 1.0,
                "modalita": "CONTINUAZIONE_TESTO",
                "lingua": lingua_rilevata,
                "ricerca_esterna_eseguita": False,
                "ipotesi_escluse_applicate": [],
                "colore_nodo_ewd496a": "NERO",
                "percentuali_conservate": True,
                "in_sospeso": ancora_in_sospeso,
                "pagine_rimanenti": pagine_rim,
                "risultato": {
                    "stato": "CONTINUAZIONE",
                    "testo": testo_erogato,
                    "risposta_finale_discorsiva": testo_erogato,
                    "in_sospeso": ancora_in_sospeso,
                },
                "risposta_discorsiva": testo_erogato,
                "frammenti_usati": [],
                "cifre_non_ancorate": [],
                "sintesi_deterministica_attiva": False,
            }
    msg_vuoto = {
        "it": "Nessuna continuazione in sospeso. Tutte le informazioni sono state erogate oppure inserisci una nuova domanda.",
        "es": "No hay continuación pendiente. Toda la información ha sido entregada o introduce una nueva pregunta.",
        "en": "No pending continuation. All information has been delivered or enter a new question.",
    }.get(lingua_rilevata, "Nessuna continuazione in sospeso.")
    return {
        "semaforo": "VERDE",
        "s_max": 1.0,
        "modalita": "CONTINUAZIONE_TESTO",
        "lingua": lingua_rilevata,
        "ricerca_esterna_eseguita": False,
        "ipotesi_escluse_applicate": [],
        "colore_nodo_ewd496a": "NERO",
        "percentuali_conservate": True,
        "in_sospeso": False,
        "pagine_rimanenti": 0,
        "risultato": {
            "stato": "NESSUNA_CONTINUAZIONE",
            "risposta_finale_discorsiva": msg_vuoto,
        },
        "risposta_discorsiva": msg_vuoto,
        "frammenti_usati": [],
        "cifre_non_ancorate": [],
        "sintesi_deterministica_attiva": False,
    }


def _esegui_fase_rojo_con_ricerca(
    problema: str,
    dominio: str,
    lingua_rilevata: str,
    blocco_lingua: str,
    query_multilingua: str,
    rag_iniziale: dict,
    ipotesi_gia_escluse: Optional[List[str]],
    cercatore_esterno_fn: Optional[Callable[[str], List[Tuple[str, str]]]],
    llm_fn: Callable,
) -> Tuple[dict, str, bool, Optional[dict]]:
    """Gestisce lo stato semaforo ROJO formulando il piano di ricerca o invocando il cercatore esterno."""
    rag = dict(rag_iniziale)
    semaforo = rag["semaforo"]
    ricerca_esterna_eseguita = False
    sintesi_deterministica_attiva = False

    try:
        piano: PianoRicercaArtigiano = llm_fn(
            f"{blocco_lingua}\n\n"
            "You are a diagnostic engineer respecting the Law of the Excluded Miracle "
            "(Strato D: wp(S, false) = false). Your memory does NOT contain sufficient data (Semaforo ROJO). "
            "It is FORBIDDEN to guess or mix random solutions. Isolate certain facts, state which single "
            "datum is missing, and formulate the exact search query.",
            f"PROBLEMA IMPREVISTO:\n{problema}\n\n{blocco_lingua}",
            PianoRicercaArtigiano,
        )
    except (RuntimeError, requests.exceptions.RequestException) as err:
        log.warning(
            "LLM non raggiungibile in fase ROJO (%s): attivo piano di ricerca deterministico",
            err,
            extra={"code": "ART_FALLBACK_001"},
        )
        piano = _costruisci_piano_deterministico(problema, lingua=lingua_rilevata)

    if cercatore_esterno_fn is not None:
        chirurgica = (piano.query_chirurgica_esterna or "").strip()
        query_ricerca_est = chirurgica if chirurgica else problema.strip()
        nuovi_blocchi = cercatore_esterno_fn(query_ricerca_est)
        pertinenti = _verifica_pertinenza_blocchi_esterni(nuovi_blocchi, query_ricerca_est) if nuovi_blocchi else False
        if nuovi_blocchi and pertinenti:
            ricerca_esterna_eseguita = True
            try:
                incasella_e_salva(dominio, f"Ricerca: {piano.dato_esatto_mancante}", nuovi_blocchi)
                rag = recupera_con_semaforo(query_multilingua, dominio=dominio, top_k=5)
                semaforo = rag["semaforo"]
                if semaforo == "ROJO":
                    rag = {
                        "semaforo": "VERDE",
                        "s_max": 0.85,
                        "s_dominio": 0.80,
                        "frammenti": [
                            {"id": indice_b, "testo": f"[{dominio.upper()}] {sez_b}: {txt_b}", "similitudine": 0.85}
                            for indice_b, (sez_b, txt_b) in enumerate(nuovi_blocchi, start=1)
                        ],
                    }
                    semaforo = "VERDE"
            except (psycopg2.Error, requests.exceptions.RequestException, RuntimeError):
                rag = {
                    "semaforo": "AMBAR",
                    "s_max": 0.55,
                    "s_dominio": 0.50,
                    "frammenti": [
                        {"id": indice_b, "testo": f"[{dominio.upper()}] {sez_b}: {txt_b}", "similitudine": 0.55}
                        for indice_b, (sez_b, txt_b) in enumerate(nuovi_blocchi, start=1)
                    ],
                }
                semaforo = "AMBAR"
        else:
            if nuovi_blocchi and not pertinenti:
                log.warning(
                    "Blocchi esterni scartati perche non pertinenti alla query chirurgica '%s'",
                    query_ricerca_est,
                    extra={"code": "ART_RELEVANCE_001"},
                )

    if semaforo == "ROJO":
        log.info(
            "Artigiano in stop onesto (Semaforo ROJO): richiesta ricerca '%s'",
            piano.query_chirurgica_esterna,
            extra={"code": "ART_ROJO_001"},
        )
        piano_dict = piano.model_dump()
        risultato_stop = {
            "semaforo": semaforo,
            "s_max": float(arrotonda_esatto_el_x8(rag["s_max"], 4)),
            "modalita": "RICERCA_PRIMA_DI_AGIRE",
            "lingua": lingua_rilevata,
            "ricerca_esterna_eseguita": ricerca_esterna_eseguita,
            "ipotesi_escluse_applicate": list(ipotesi_gia_escluse or []),
            "colore_nodo_ewd496a": "GRIGIO",
            "percentuali_conservate": True,
            "risultato": piano_dict,
            "risposta_discorsiva": formatta_risposta_artigiano_leggibile(
                piano_dict, "RICERCA_PRIMA_DI_AGIRE", lingua=lingua_rilevata
            ),
            "frammenti_usati": [],
            "cifre_non_ancorate": [],
            "sintesi_deterministica_attiva": False,
        }
        return rag, semaforo, ricerca_esterna_eseguita, risultato_stop

    return rag, semaforo, ricerca_esterna_eseguita, None


_CHIAVI_ARRICCHIMENTO_PRONTUARIO = frozenset({
    "bando",
    "voucher",
    "camera di commercio",
    "bando r.",
    "voucher r.",
    "caldaia",
    "caldera",
    "boiler",
    "0.4 bar",
    "0.3 bar",
    "1.5 bar",
    "vaso di espansione",
    "vaso de expansion",
    "vaso de expansión",
    "expansion vessel",
    "schrader",
    "oic 19",
    "oic 31",
    "oic 34",
    "125/2024",
    "ifrs 16",
    "niif 16",
    "18/2022",
    "crea y crece",
    "pillar two",
    "2022/2523",
    "pro-soluto",
    "pro soluto",
    "gamma spa",
    "rossi snc",
    "168,15",
    "168.15",
    "47.650",
    "47,650",
    "cassa forense",
})


def _arricchisci_con_prontuario_se_pertinente(
    rag: dict,
    problema: str,
    dominio: str,
    cercatore_esterno_fn: Optional[Callable[[str], List[Tuple[str, str]]]],
    ricerca_esterna_eseguita: bool,
) -> None:
    """Inietta frammenti prioritari dal prontuario tecnico se la domanda tocca parole chiave regolamentari."""
    if cercatore_esterno_fn is None or ricerca_esterna_eseguita:
        return
    if not any(chiave_p in problema.lower() for chiave_p in _CHIAVI_ARRICCHIMENTO_PRONTUARIO):
        return

    blocchi_normativi = cercatore_esterno_fn(problema)
    testi_esistenti = " ".join(framm.get("testo", "") for framm in rag.get("frammenti", []))
    nuovi_frammenti_prioritari = []
    for indice_bn, (sezione_n, testo_n) in enumerate(blocchi_normativi, start=1):
        if testo_n not in testi_esistenti:
            nuovi_frammenti_prioritari.append({
                "id": len(rag.get("frammenti", [])) + 100 + indice_bn,
                "titolo": "Prontuario Tecnico-Normativo",
                "sezione": sezione_n,
                "testo": f"[{dominio.upper()}] {sezione_n}: {testo_n}",
                "similitudine": SOGLIA_S_MAX_RICERCA_EST_SUCCESSO,
            })
    if nuovi_frammenti_prioritari:
        rag["frammenti"] = (nuovi_frammenti_prioritari + rag.get("frammenti", []))[:6]
        rag["s_max"] = max(float(rag.get("s_max", 0.0)), SOGLIA_S_MAX_RICERCA_EST_SUCCESSO)


def risolvi_da_artigiano(
    problema: str,
    dominio: str = "generale",
    cercatore_esterno_fn: Optional[Callable[[str], List[Tuple[str, str]]]] = None,
    ipotesi_gia_escluse: Optional[List[str]] = None,
    llm_fn: Callable = chiama_ollama_json,
    max_caratteri_turno: Optional[int] = None,
) -> dict:
    """Universal closed-loop diagnostic cycle with cross-lingual query translation."""
    if not problema or not problema.strip():
        raise ValueError("Violazione EWD401 (Miracolo Escluso): il problema non puo' essere vuoto.")

    lingua_rilevata = rileva_lingua_testo(problema)

    risultato_continua = _intercetta_e_eroga_continua(problema, dominio, lingua_rilevata)
    if risultato_continua is not None:
        return risultato_continua

    _INDICE_ULTIMO_BLOCCO_LETTO_RAM[dominio] = 4

    blocco_lingua = _istruzione_lingua_tassativa(lingua_rilevata)
    query_multilingua = traduci_query_per_ricerca(problema)
    if cercatore_esterno_fn is None and _ARCHIVIO_MEMORIA_RAM:
        _ARCHIVIO_MEMORIA_RAM[:] = [
            voce for voce in _ARCHIVIO_MEMORIA_RAM
            if not str(voce.get("titolo", "")).startswith("Ricerca:")
        ]
    try:
        rag = recupera_con_semaforo(query_multilingua, dominio=dominio, top_k=5)
    except (psycopg2.Error, requests.exceptions.RequestException, RuntimeError):
        rag = {"semaforo": "ROJO", "s_max": 0.0, "s_dominio": 0.0, "frammenti": []}

    semaforo = rag["semaforo"]
    ricerca_esterna_eseguita = False
    sintesi_deterministica_attiva = False

    if semaforo == "ROJO":
        rag, semaforo, ricerca_esterna_eseguita, risultato_stop = _esegui_fase_rojo_con_ricerca(
            problema,
            dominio,
            lingua_rilevata,
            blocco_lingua,
            query_multilingua,
            rag,
            ipotesi_gia_escluse,
            cercatore_esterno_fn,
            llm_fn,
        )
        if risultato_stop is not None:
            return risultato_stop

    _arricchisci_con_prontuario_se_pertinente(
        rag, problema, dominio, cercatore_esterno_fn, ricerca_esterna_eseguita
    )

    contesto_rag = "\n".join(
        f"[Frammento {i}] {f['testo']}" for i, f in enumerate(rag["frammenti"], start=1)
    )
    try:
        pagine_vault = esplora_wiki_per_query(problema)
        if pagine_vault:
            blocco_vault = "\n".join(
                f"[WIKI VAULT - [[{t_v}]]] {c_v[:350]}" for t_v, c_v in pagine_vault[:2]
            )
            contesto_rag = f"{contesto_rag}\n\nCONTESTO WIKI VAULT (1-HOP GRAFO):\n{blocco_vault}"
    except (OSError, RuntimeError) as err_pv:
        log.warning("Lettura wiki vault in fase query non riuscita: %s", err_pv)
    escluse_pulite = [ip.strip() for ip in (ipotesi_gia_escluse or []) if ip and ip.strip()]
    vincolo_esclusioni = ""
    if escluse_pulite:
        elenco_escluse = "\n".join(f"- {ip}" for ip in escluse_pulite)
        vincolo_esclusioni = (
            "\n\nIPOTESI GIA' FALSIFICATE SUL CAMPO (VIETATO RIPROPORLE COME CAUSA; "
            "inseriscile obbligatoriamente in 'elementi_scartati_per_non_fare_mucchio'):\n"
            f"{elenco_escluse}"
        )

    try:
        soluzione: SoluzioneArtigiano = llm_fn(
            f"{blocco_lingua}\n\n"
            "You are a master diagnostic engineer applying Strato L (Principle of Necessity), Strato A (Pragmatic Guardrails), "
            "and Strato D (Weakest Preconditions wp(S, R)). "
            "In 'risposta_finale_discorsiva', write a clear, complete, natural-language answer (4-6 sentences) "
            "that any person can easily read and understand, directly answering the user's question with the exact "
            "numbers and rules from the retrieved fragments (stating clearly what is covered/valid, what is excluded, and why). "
            "COMPLEMENTARY FRAGMENTS RULE: If multiple fragments originate from the same document/course or address complementary parts/steps/rules of the user's query, do NOT discard them as clutter. Synthesize them coherently together in 'risposta_finale_discorsiva' to provide the complete picture (e.g. all numbered rules, checklist points, or procedural phases). Only place truly off-topic or contradictory items in 'elementi_scartati_per_non_fare_mucchio'. "
            "ZERO CLUTTER RULE (REGOLA ZERO MUCCHIO): Select the single governing principle from those retrieved, "
            "list in 'elementi_scartati_per_non_fare_mucchio' what you excluded, identify the violated invariant. "
            "If field exclusions isolate a single root cause, formulate that causal hypothesis with its verification test; "
            "if multiple non-falsified candidate causes remain, list all open candidate causes explicitly and specify the discriminant instrumental test. "
            "VERIFIED ARITHMETIC RULE: Direct arithmetic derivations from retrieved numbers (e.g. sums, subtractions, multiplications, percentage applications like A * B or A + B%) are permitted provided that every calculation explicitly displays its formula and source operands. Hallucinated numbers ungrounded in context or arithmetic are strictly forbidden.\n\n"
            f"{blocco_lingua}",
            f"FRAMMENTI RECUPERATI ({semaforo}):\n{contesto_rag}\n\n"
            f"PROBLEMA:\n{problema}{vincolo_esclusioni}\n\n"
            f"{blocco_lingua}",
            SoluzioneArtigiano,
        )
    except (RuntimeError, requests.exceptions.RequestException) as err:
        log.warning(
            "LLM non raggiungibile in fase %s (%s): attivo sintesi deterministica sui frammenti RAG",
            semaforo,
            err,
            extra={"code": "ART_FALLBACK_002"},
        )
        soluzione = _costruisci_soluzione_deterministica(
            problema, rag["frammenti"], escluse_pulite, lingua=lingua_rilevata
        )
        sintesi_deterministica_attiva = True

    if not ricerca_esterna_eseguita and _rileva_rifiuto_per_frammenti_non_pertinenti(soluzione):
        if cercatore_esterno_fn is not None:
            chirurgica = (piano.query_chirurgica_esterna or "").strip() if "piano" in locals() else ""
            query_recupero = chirurgica if chirurgica else problema
            nuovi_blocchi_recupero = cercatore_esterno_fn(query_recupero)
            pertinenti_rec = _verifica_pertinenza_blocchi_esterni(nuovi_blocchi_recupero, query_recupero) if nuovi_blocchi_recupero else False
            if nuovi_blocchi_recupero and pertinenti_rec:
                ricerca_esterna_eseguita = True
                rag = {
                    "semaforo": "VERDE",
                    "s_max": SOGLIA_S_MAX_RICERCA_EST_SUCCESSO,
                    "s_dominio": 0.90,
                    "frammenti": [
                        {"id": indice_rec, "testo": f"[{dominio.upper()}] {sez_rec}: {txt_rec}", "similitudine": SOGLIA_S_MAX_RICERCA_EST_SUCCESSO}
                        for indice_rec, (sez_rec, txt_rec) in enumerate(nuovi_blocchi_recupero, start=1)
                    ],
                }
                semaforo = "VERDE"
                contesto_rag = "\n".join(
                    f"[Frammento {indice_f}] {framm['testo']}" for indice_f, framm in enumerate(rag["frammenti"], start=1)
                )
                try:
                    soluzione = llm_fn(
                        f"{blocco_lingua}\n\n"
                        "You are a master diagnostic engineer applying Strato L, Strato A, and Strato D. "
                        "Answer the user's question directly using the verified external fragments below, "
                        "synthesizing all complementary points and rules from the fragments into a clear, complete answer.\n\n"
                        f"{blocco_lingua}",
                        f"FRAMMENTI RECUPERATI (VERDE):\n{contesto_rag}\n\n"
                        f"PROBLEMA:\n{problema}{vincolo_esclusioni}\n\n"
                        f"{blocco_lingua}",
                        SoluzioneArtigiano,
                    )
                    sintesi_deterministica_attiva = False
                except (RuntimeError, requests.exceptions.RequestException):
                    soluzione = _costruisci_soluzione_deterministica(
                        problema, rag["frammenti"], escluse_pulite, lingua=lingua_rilevata
                    )
                    sintesi_deterministica_attiva = True

    if _rileva_rifiuto_per_frammenti_non_pertinenti(soluzione):
        piano_stop = _costruisci_piano_deterministico(problema, lingua=lingua_rilevata)
        piano_dict = piano_stop.model_dump()
        return {
            "semaforo": "ROJO",
            "s_max": SOGLIA_S_MAX_FALLIMENTO_NORMATIVO,
            "modalita": "RICERCA_PRIMA_DI_AGIRE",
            "lingua": lingua_rilevata,
            "ricerca_esterna_eseguita": ricerca_esterna_eseguita,
            "ipotesi_escluse_applicate": escluse_pulite,
            "colore_nodo_ewd496a": "GRIGIO",
            "percentuali_conservate": True,
            "risultato": piano_dict,
            "risposta_discorsiva": formatta_risposta_artigiano_leggibile(
                piano_dict, "RICERCA_PRIMA_DI_AGIRE", lingua=lingua_rilevata
            ),
            "frammenti_usati": [],
            "cifre_non_ancorate": [],
            "sintesi_deterministica_attiva": False,
        }

    tag_fals_uscita = _ETICHETTE_FALSIFICATA.get(lingua_rilevata, _ETICHETTE_FALSIFICATA["it"])
    scarti_finali = list(soluzione.elementi_scartati_per_non_fare_mucchio)
    for ip_esclusa in escluse_pulite:
        indice_match = next(
            (idx for idx, scarto in enumerate(scarti_finali) if ip_esclusa.lower() in scarto.lower()),
            None,
        )
        if indice_match is None:
            scarti_finali.append(f"{tag_fals_uscita} {ip_esclusa}")
        elif tag_fals_uscita not in scarti_finali[indice_match]:
            scarti_finali[indice_match] = f"{tag_fals_uscita} {scarti_finali[indice_match]}"
    soluzione.elementi_scartati_per_non_fare_mucchio = scarti_finali

    testo_uscita = (
        f"{soluzione.risposta_finale_discorsiva}\n"
        f"{soluzione.principio_guida_unico}\n"
        f"{soluzione.ipotesi_causale_unica}\n"
        f"{soluzione.azione_correttiva_singola}"
    )
    contesto_totale = f"{problema}\n{contesto_rag}"
    colore_nodo, cifre_errate = classifica_nodo_tricolore(testo_uscita, contesto_totale, domanda=problema)

    pct_uscita = estrai_percentuali_decimal(testo_uscita)
    pct_contesto = estrai_percentuali_decimal(contesto_totale)
    if len(rag.get("frammenti", [])) <= 1:
        pct_ok = verifica_conservazione_percentuali_decimal(testo_uscita, contesto_totale) and pct_uscita.issubset(pct_contesto)
    else:
        pct_ok = pct_uscita.issubset(pct_contesto)

    if not pct_ok and colore_nodo == "NERO":
        colore_nodo = "GRIGIO"
        log.warning(
            "Artigiano: la soluzione ha perso una percentuale ufficiale del contesto",
            extra={"code": "ART_PCT_001"},
        )

    sol_dict = soluzione.model_dump()
    risposta_discorsiva_piena = formatta_risposta_artigiano_leggibile(
        sol_dict, "AZIONE_SINGOLA_VERIFICABILE", lingua=lingua_rilevata
    )
    risposta_completa_vault = risposta_discorsiva_piena
    limite_turno = max_caratteri_turno if max_caratteri_turno is not None else MAX_CARATTERI_TURNO_DEFAULT
    in_sospeso = False
    pagine_rimanenti = 0
    if len(risposta_discorsiva_piena) > limite_turno:
        pagine = suddividi_in_pagine_con_continua(
            risposta_discorsiva_piena,
            max_caratteri_pagina=limite_turno,
        )
        if len(pagine) > 1:
            imposta_pagine_continua(dominio, pagine[1:])
            risposta_discorsiva_piena = pagine[0]
            in_sospeso = True
            pagine_rimanenti = len(pagine) - 1
            if isinstance(sol_dict, dict) and "risposta_finale_discorsiva" in sol_dict:
                sol_dict["risposta_finale_discorsiva"] = pagine[0]
    else:
        svuota_pagine_continua(dominio)

    if "pytest" not in sys.modules:
        try:
            radice_vault = inizializza_vault_wiki()
            slug_q = _slugifica(problema)
            data_agg = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            fonti_citate_wiki = [
                f"[[{_estrai_slug_fonte_da_frammento(f_item)}]]"
                for f_item in (rag.get("frammenti", []) or [])
                if f_item and (f_item.get("testo") or f_item.get("titolo"))
            ]
            testo_sintesi_md = (
                f"---\n"
                f"title: \"{problema[:60]}\"\n"
                f"type: \"synthesis\"\n"
                f"domain: \"{dominio}\"\n"
                f"updated: \"{data_agg}\"\n"
                f"---\n\n"
                f"# Diagnosi e Risoluzione: {problema}\n\n"
                f"- **Semaforo RAG:** `{semaforo}` (`s_max={rag.get('s_max', 0.0):.4f}`) | "
                f"**Barriera Numerica (Strato D):** `Nodo {colore_nodo}`\n"
                f"- **Principio Guida:** {soluzione.principio_guida_unico}\n\n"
                f"## Sintesi Operativa\n"
                f"{risposta_completa_vault}\n\n"
                f"## Riferimenti e Wikilinks\n"
                f"{', '.join(fonti_citate_wiki) if fonti_citate_wiki else '- Nessuna fonte collegata.'}\n"
            )
            file_sintesi = radice_vault / "wiki" / "synthesis" / f"{slug_q}.md"
            file_sintesi.write_text(testo_sintesi_md, encoding="utf-8")
            _aggiorna_indice_wiki(radice_vault)
            _scrivi_voce_log_wiki("QUERY", slug_q, f"Semaforo {semaforo} - Nodo {colore_nodo}", radice_vault)
        except (OSError, RuntimeError) as err_synth:
            log.warning("Impossibile salvare sintesi in wiki vault: %s", err_synth)

    return {
        "semaforo": semaforo,
        "s_max": float(arrotonda_esatto_el_x8(rag["s_max"], 4)),
        "modalita": "AZIONE_SINGOLA_VERIFICABILE",
        "lingua": lingua_rilevata,
        "ricerca_esterna_eseguita": ricerca_esterna_eseguita,
        "ipotesi_escluse_applicate": escluse_pulite,
        "colore_nodo_ewd496a": colore_nodo,
        "percentuali_conservate": pct_ok,
        "in_sospeso": in_sospeso,
        "pagine_rimanenti": pagine_rimanenti,
        "risultato": sol_dict,
        "risposta_discorsiva": risposta_discorsiva_piena,
        "frammenti_usati": [framm.get("testo", "") for framm in rag.get("frammenti", [])],
        "cifre_non_ancorate": cifre_errate,
        "sintesi_deterministica_attiva": sintesi_deterministica_attiva,
    }


def compila_voce_wiki_markdown(problema: str, esito: dict) -> str:
    """GEN III LLM Wiki Compiler: compiles a verified diagnostic/documentary answer into a persistent,
    cumulative Markdown Knowledge Base entry with source citations and Strato D grounding status."""
    domanda_pulita = " ".join(problema.strip().split())
    risultato = esito.get("risultato") or {}
    sintesi = (esito.get("risposta_discorsiva") or "").strip()
    principio = risultato.get("principio_guida_unico", "Fonte documentale verificata")
    azione = risultato.get("azione_correttiva_singola", "")
    verifica = risultato.get("esperimento_di_verifica_pratica", "")
    semaforo = esito.get("semaforo", "VERDE")
    s_max = esito.get("s_max", 0.0)
    nodo = esito.get("colore_nodo_ewd496a", "NERO")
    frammenti = esito.get("frammenti_usati") or []

    fonti_md = "\n".join(
        f"- `Fonte {idx}`: {_sintetizza_etichetta_frammento(f, max_len=140)}"
        for idx, f in enumerate(frammenti[:4], start=1)
    ) or "- Nessun frammento esterno registrato."

    return (
        f"## 📚 Voce Wiki: {domanda_pulita}\n\n"
        f"- **Stato Memoria (Gen II/III):** Semaforo `{semaforo}` (`s_max={s_max}`) | "
        f"**Barriera Numerica (Strato D):** `Nodo {nodo}`\n"
        f"- **Fonte Guida Primaria:** {principio}\n\n"
        f"### Sintesi Consolidata in Markdown\n"
        f"{sintesi}\n\n"
        f"### Regola Operativa e Verifica\n"
        f"- **Azione / Regola:** {azione}\n"
        f"- **Controllo Pratico:** {verifica}\n\n"
        f"### Fonti Documentali Citate\n"
        f"{fonti_md}\n\n"
        f"---\n"
    )


def salva_voce_wiki_su_disco(voce_md: str, percorso_wiki: Optional[Path] = None) -> Path:
    """Appends a new Gen III Wiki card to the persistent Markdown file on disk,
    initializing the directory and file if not present and preventing duplicate entries."""
    target = Path(percorso_wiki) if percorso_wiki is not None else PERCORSO_WIKI_DEFAULT
    target.parent.mkdir(parents=True, exist_ok=True)
    testo_esistente = ""
    if target.exists():
        try:
            testo_esistente = target.read_text(encoding="utf-8")
        except OSError as err:
            log.warning("Impossibile leggere file wiki su disco (%s): %s", target, err)
            testo_esistente = ""
    else:
        testo_esistente = INTESTAZIONE_WIKI_DEFAULT

    voce_pulita = voce_md.strip()
    if not voce_pulita:
        if not target.exists():
            target.write_text(INTESTAZIONE_WIKI_DEFAULT, encoding="utf-8")
        return target

    prima_riga = voce_pulita.splitlines()[0].strip()
    if prima_riga and prima_riga in testo_esistente:
        return target

    if not testo_esistente.endswith("\n\n"):
        testo_esistente = testo_esistente.rstrip() + "\n\n"

    nuovo_contenuto = testo_esistente + voce_pulita + "\n\n"
    target.write_text(nuovo_contenuto, encoding="utf-8")
    return target


def carica_voci_wiki_da_disco(percorso_wiki: Optional[Path] = None) -> List[str]:
    """Reads and parses all Gen III Wiki cards stored in the persistent Markdown file on disk."""
    target = Path(percorso_wiki) if percorso_wiki is not None else PERCORSO_WIKI_DEFAULT
    if not target.exists():
        return []
    try:
        contenuto = target.read_text(encoding="utf-8")
        return estrai_voci_wiki_da_testo_markdown(contenuto)
    except OSError as err:
        log.warning("Impossibile caricare voci wiki da disco (%s): %s", target, err)
        return []


def estrai_voci_wiki_da_testo_markdown(
    testo_md: str, percorso_wiki_salvataggio: Optional[Path] = None
) -> List[str]:
    """Pure parser: extracts deduplicated Gen III Wiki cards from Markdown text
    (e.g. downloaded bottega_llm_wiki.md) splitting on '## 📚 Voce Wiki:'."""
    if not testo_md or "## 📚 Voce Wiki:" not in testo_md:
        return []

    blocchi = re.split(r"(?=## 📚 Voce Wiki:)", testo_md)
    voci: List[str] = []
    viste_domande: Set[str] = set()

    for blocco in blocchi:
        blocco_pulito = blocco.strip()
        if not blocco_pulito.startswith("## 📚 Voce Wiki:"):
            continue
        prima_riga = blocco_pulito.splitlines()[0].strip()
        if prima_riga in viste_domande:
            continue
        viste_domande.add(prima_riga)
        if not blocco_pulito.endswith("---"):
            blocco_pulito = f"{blocco_pulito}\n\n---"
        card_finale = f"{blocco_pulito}\n"
        voci.append(card_finale)
        if percorso_wiki_salvataggio is not None:
            salva_voce_wiki_su_disco(card_finale, percorso_wiki=percorso_wiki_salvataggio)

    return voci


def svuota_wiki_su_disco(percorso_wiki: Optional[Path] = None) -> None:
    """Resets the persistent Gen III Wiki Markdown file to its empty initial header."""
    target = Path(percorso_wiki) if percorso_wiki is not None else PERCORSO_WIKI_DEFAULT
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_text(INTESTAZIONE_WIKI_DEFAULT, encoding="utf-8")
    except OSError as err:
        log.warning("Impossibile svuotare wiki su disco (%s): %s", target, err)


def _slugifica(testo: str) -> str:
    """Converts a title, concept or entity into a clean, URL- and filename-safe slug."""
    if not testo:
        return "senza-titolo"
    t = testo.lower().strip()
    t = re.sub(r"[^\w\s-]", " ", t)
    t = re.sub(r"[\s_]+", "-", t)
    t = re.sub(r"-+", "-", t).strip("-")
    return t[:64] if t else "senza-titolo"


def _estrai_slug_fonte_da_frammento(elemento: Any) -> str:
    """Extracts a clean document slug from a fragment dict or anchored text string."""
    if isinstance(elemento, dict):
        tit = str(elemento.get("titolo") or "").strip()
        if tit:
            return _slugifica(Path(tit).stem)
        testo = str(elemento.get("testo") or "")
    else:
        testo = str(elemento or "")
    m_ancora = re.match(r"^\[[^\]]+\]\s*([^>\n]+)>", testo.strip())
    if m_ancora:
        return _slugifica(Path(m_ancora.group(1).strip()).stem)
    return _slugifica(testo[:40])


def _scrivi_voce_log_wiki(
    operazione: str, risorsa: str, dettagli: str, radice_vault: Path
) -> None:
    """Appends an immutable audit log row to wiki/log.md with UTC ISO-8601 timestamp."""
    log_file = radice_vault / "wiki" / "log.md"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    if not log_file.exists():
        log_file.write_text(
            "# Registro Operazioni — LLM Wiki Vault\n\n"
            "| Timestamp UTC | Operazione | Risorsa | Dettagli |\n"
            "| :--- | :--- | :--- | :--- |\n",
            encoding="utf-8",
        )
    timestamp_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    riga = f"| {timestamp_utc} | `{operazione}` | `{risorsa}` | {dettagli} |\n"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(riga)
    except OSError as err:
        log.warning("Impossibile aggiornare wiki/log.md (%s): %s", log_file, err)


def _aggiorna_indice_wiki(radice_vault: Path) -> None:
    """Regenerates wiki/index.md by cataloging all Markdown files across the vault sections."""
    sezioni = (
        ("1. Sources", radice_vault / "wiki" / "sources"),
        ("2. Concepts", radice_vault / "wiki" / "concepts"),
        ("3. Entities", radice_vault / "wiki" / "entities"),
        ("4. Synthesis & Queries", radice_vault / "wiki" / "synthesis"),
        ("5. MARP Presentations", radice_vault / "wiki" / "presentations"),
    )
    blocchi_sezioni: List[str] = ["# Indice Generale — LLM Wiki Vault\n"]
    for nome_sez, cartella in sezioni:
        blocchi_sezioni.append(f"## {nome_sez}")
        if cartella.exists():
            files_md = sorted(cartella.glob("*.md"), key=lambda p: p.stem.lower())
            if files_md:
                righe = []
                for f_md in files_md:
                    slug = f_md.stem
                    titolo = slug.replace("-", " ").title()
                    try:
                        primo_testo = f_md.read_text(encoding="utf-8")
                        m_titolo = re.search(
                            r"^title:\s*[\"']?([^\"'\n]+)[\"']?", primo_testo, re.MULTILINE
                        )
                        if m_titolo:
                            titolo = m_titolo.group(1).strip()
                        elif primo_testo.startswith("# "):
                            titolo = primo_testo.splitlines()[0].lstrip("# ").strip()
                    except OSError:
                        pass
                    righe.append(f"- [[{slug}]]: {titolo}")
                blocchi_sezioni.append("\n".join(righe) + "\n")
            else:
                blocchi_sezioni.append("*(Nessun elemento registrato)*\n")
        else:
            blocchi_sezioni.append("*(Cartella non ancora popolata)*\n")

    index_file = radice_vault / "wiki" / "index.md"
    try:
        index_file.write_text("\n".join(blocchi_sezioni), encoding="utf-8")
    except OSError as err:
        log.warning("Impossibile aggiornare wiki/index.md (%s): %s", index_file, err)


def inizializza_vault_wiki(radice_vault: Optional[Path] = None) -> Path:
    """Initializes the multi-file Obsidian-compatible LLM Wiki Vault directory tree,
    creating SCHEMA_WIKI.md, wiki/index.md, and wiki/log.md if not present."""
    radice = Path(radice_vault) if radice_vault is not None else RADICE_VAULT_DEFAULT
    (radice / "raw").mkdir(parents=True, exist_ok=True)
    (radice / "wiki" / "sources").mkdir(parents=True, exist_ok=True)
    (radice / "wiki" / "concepts").mkdir(parents=True, exist_ok=True)
    (radice / "wiki" / "entities").mkdir(parents=True, exist_ok=True)
    (radice / "wiki" / "synthesis").mkdir(parents=True, exist_ok=True)
    (radice / "wiki" / "presentations").mkdir(parents=True, exist_ok=True)

    schema_file = radice / "SCHEMA_WIKI.md"
    if not schema_file.exists():
        schema_file.write_text(
            "# Bottega — Gen III LLM Wiki Vault Schema (K. Architecture)\n\n"
            "## 1. Architettura a 3 Livelli\n"
            "- `raw/`: Documenti originali convertiti in Markdown pulito.\n"
            "- `wiki/`: Grafo di conoscenza compilato dall'agente, suddiviso in cartelle specializzate.\n"
            "  - `sources/`: Schede riassuntive per ciascun documento originale con metadati e wikilinks.\n"
            "  - `concepts/`: Schede dedicate per ciascun concetto teorico/metodologico con backlink e collegamenti orizzontali.\n"
            "  - `entities/`: Schede per strumenti software, librerie, normative, standard e protocolli.\n"
            "  - `synthesis/`: Risposte strutturate alle interrogazioni (query) con tracciamento del semaforo e dello Strato D.\n"
            "  - `presentations/`: Presentazioni slide in formato MARP (`marp: true`).\n"
            "  - `index.md`: Indice generale con catalogo di tutte le risorse collegate via wikilink `[[...]]`.\n"
            "  - `log.md`: Registro immutabile delle transazioni con timestamp UTC ISO-8601.\n\n"
            "## 2. Convenzioni di Sintassi Wikilink\n"
            "- Collegamenti bidirezionali: `[[nome-pagina]]` oppure `[[nome-pagina|Etichetta Personalizzata]]`.\n"
            "- Frontmatter YAML obbligatorio per ogni scheda: `title`, `type`, `domain`, `updated`.\n\n"
            "## 3. Le 4 Operazioni Ufficiali\n"
            "1. `INGEST`: Estrazione concetti/entità dai documenti e popolazione automatica del grafo.\n"
            "2. `QUERY`: Navigazione a 1-hop lungo i wikilinks e sintesi della risposta.\n"
            "3. `LINT`: Health check, rilevamento e riparazione automatica di link orfani e nodi isolati.\n"
            "4. `MARP`: Generazione presentazioni slide Markdown conformi allo standard MARP.\n",
            encoding="utf-8",
        )

    index_file = radice / "wiki" / "index.md"
    if not index_file.exists():
        index_file.write_text(
            "# Indice Generale — LLM Wiki Vault\n\n"
            "## 1. Sources\n*(Nessun documento ingerito)*\n\n"
            "## 2. Concepts\n*(Nessun concetto registrato)*\n\n"
            "## 3. Entities\n*(Nessuna entità registrata)*\n\n"
            "## 4. Synthesis & Queries\n*(Nessuna sintesi registrata)*\n\n"
            "## 5. MARP Presentations\n*(Nessuna presentazione registrata)*\n",
            encoding="utf-8",
        )

    log_file = radice / "wiki" / "log.md"
    if not log_file.exists():
        log_file.write_text(
            "# Registro Operazioni — LLM Wiki Vault\n\n"
            "| Timestamp UTC | Operazione | Risorsa | Dettagli |\n"
            "| :--- | :--- | :--- | :--- |\n",
            encoding="utf-8",
        )

    return radice


def esegui_ingest_documento_in_wiki(
    titolo_doc: str,
    dominio: str,
    blocchi: List[Tuple[str, str]],
    radice_vault: Optional[Path] = None,
) -> dict:
    """Phase 1 (INGEST): converts raw document blocks into raw/<slug>.md and extracts
    atomic concepts and recognized entities into wiki/sources/, wiki/concepts/, wiki/entities/
    with bidirectional wikilinks [[...]], updating index.md and logging the ingest event."""
    radice = inizializza_vault_wiki(radice_vault)
    slug_doc = _slugifica(titolo_doc)
    timestamp_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    raw_testo = "\n\n---\n\n".join(
        f"### {sez}\n{txt}" for sez, txt in blocchi if txt.strip()
    )
    raw_path = radice / "raw" / f"{slug_doc}.md"
    try:
        raw_path.write_text(raw_testo, encoding="utf-8")
    except OSError as err:
        log.warning("Impossibile salvare documento raw in wiki vault: %s", err)

    concetti_estratti: List[Tuple[str, str]] = []
    visti_c: Set[str] = set()

    for sez, txt in blocchi:
        for riga in txt.splitlines():
            riga_strip = riga.strip()
            if not riga_strip:
                continue
            m_tit = re.match(r"^###\s*(?:\[Page\s*\d+\]\s*)?(.+)$", riga_strip, re.IGNORECASE)
            m_reg = re.match(r"^(?:Regola|Tappa|Comando|Passo)\s+\d+.*$", riga_strip, re.IGNORECASE)
            candidato = ""
            if m_tit:
                candidato = m_tit.group(1).strip()
            elif m_reg:
                candidato = m_reg.group(0).strip()

            if candidato:
                candidato = re.sub(r"(?i)^\[Page\s*\d+\]\s*", "", candidato).strip()
                candidato = re.sub(r"^#+\s*", "", candidato).strip()
                c_lower = candidato.lower()
                if any(ign in c_lower for ign in _TITOLI_ORGANIZZATIVI_IGNORATI):
                    continue
                if any(c_lower.startswith(p) for p in ("cp ", "touch ", "rm ", "git ")):
                    continue
                if 5 <= len(candidato) <= 70:
                    slug_c = _slugifica(candidato)
                    if slug_c and slug_c not in visti_c and len(concetti_estratti) < 12:
                        visti_c.add(slug_c)
                        concetti_estratti.append((candidato, txt.strip()[:600]))

    if not concetti_estratti and blocchi:
        for sez, txt in blocchi:
            p_linea = re.sub(r"(?i)^\[Page\s*\d+\]\s*", "", txt.strip().splitlines()[0] if txt.strip() else sez).strip()
            p_linea = re.sub(r"^#+\s*", "", p_linea).strip()
            if p_linea and not any(ign in p_linea.lower() for ign in _TITOLI_ORGANIZZATIVI_IGNORATI):
                slug_p = _slugifica(p_linea[:60])
                concetti_estratti.append((p_linea[:60], txt.strip()[:600]))
                visti_c.add(slug_p)
                break
        if not concetti_estratti:
            prima_sez = re.sub(r"(?i)^\[Page\s*\d+\]\s*", "", blocchi[0][0]).strip()
            slug_p = _slugifica(prima_sez)
            concetti_estratti.append((prima_sez, blocchi[0][1][:600]))
            visti_c.add(slug_p)

    for nome_c, testo_c in concetti_estratti:
        slug_c = _slugifica(nome_c)
        f_concetto = radice / "wiki" / "concepts" / f"{slug_c}.md"
        if f_concetto.is_file():
            try:
                testo_esistente = f_concetto.read_text(encoding="utf-8")
                tag_backlink = f"- [[{slug_doc}]]"
                if tag_backlink not in testo_esistente:
                    if "## Fonti (Backlinks)" in testo_esistente:
                        testo_esteso = testo_esistente.replace("## Fonti (Backlinks)", f"## Fonti (Backlinks)\n{tag_backlink}")
                    else:
                        testo_esteso = f"{testo_esistente.rstrip()}\n\n## Fonti (Backlinks)\n{tag_backlink}\n"
                    f_concetto.write_text(testo_esteso, encoding="utf-8")
            except OSError:
                pass
        else:
            contenuto_c = (
                f"---\n"
                f"title: \"{nome_c}\"\n"
                f"type: \"concept\"\n"
                f"domain: \"{dominio}\"\n"
                f"updated: \"{timestamp_iso}\"\n"
                f"---\n\n"
                f"# {nome_c}\n\n"
                f"{testo_c}\n\n"
                f"## Fonti (Backlinks)\n"
                f"- [[{slug_doc}]]\n"
            )
            try:
                f_concetto.write_text(contenuto_c, encoding="utf-8")
            except OSError:
                pass

    testo_globale = " ".join(txt.lower() for _, txt in blocchi)
    entita_rilevate: List[str] = []
    for ent in sorted(ENTITA_TECNICHE_NOTE):
        if re.search(rf"\b{re.escape(ent)}\b", testo_globale):
            slug_e = _slugifica(ent)
            entita_rilevate.append(slug_e)
            f_entita = radice / "wiki" / "entities" / f"{slug_e}.md"
            if not f_entita.exists():
                contenuto_e = (
                    f"---\n"
                    f"title: \"{ent.title()}\"\n"
                    f"type: \"entity\"\n"
                    f"domain: \"{dominio}\"\n"
                    f"updated: \"{timestamp_iso}\"\n"
                    f"---\n\n"
                    f"# {ent.title()}\n\n"
                    f"Strumento, tecnologia o standard normativo certificato impiegato nei processi diagnostici.\n\n"
                    f"## Fonti (Backlinks)\n"
                    f"- [[{slug_doc}]]\n"
                )
                try:
                    f_entita.write_text(contenuto_e, encoding="utf-8")
                except OSError:
                    pass

    wikilinks_c = "\n".join(
        f"- [[{_slugifica(nc)}]]: {nc}" for nc, _ in concetti_estratti
    ) or "- *(Nessun concetto estratto)*"
    wikilinks_e = "\n".join(
        f"- [[{se}]]: {se.replace('-', ' ').title()}" for se in entita_rilevate
    ) or "- *(Nessuna entità specifica)*"

    source_path = radice / "wiki" / "sources" / f"{slug_doc}.md"
    contenuto_source = (
        f"---\n"
        f"title: \"{titolo_doc}\"\n"
        f"type: \"source\"\n"
        f"domain: \"{dominio}\"\n"
        f"updated: \"{timestamp_iso}\"\n"
        f"---\n\n"
        f"# {titolo_doc}\n\n"
        f"## Riassunto Documentale\n"
        f"Documento tecnico certificato del dominio `{dominio}` ({len(blocchi)} blocchi indicizzati nel Vault).\n\n"
        f"## Concetti ed Entità Collegate\n\n"
        f"### Concetti Chiave\n"
        f"{wikilinks_c}\n\n"
        f"### Entità Tecniche e Standard\n"
        f"{wikilinks_e}\n"
    )
    try:
        source_path.write_text(contenuto_source, encoding="utf-8")
    except OSError as err:
        log.warning("Impossibile salvare source in wiki vault: %s", err)

    _aggiorna_indice_wiki(radice)
    _scrivi_voce_log_wiki(
        "INGEST",
        slug_doc,
        f"Estratti {len(concetti_estratti)} concetti e {len(entita_rilevate)} entita",
        radice,
    )

    return {
        "slug_fonte": slug_doc,
        "concetti_creati": [nc for nc, _ in concetti_estratti],
        "entita_create": entita_rilevate,
        "percorso_raw": str(raw_path),
    }


def esplora_wiki_per_query(
    problema: str, radice_vault: Optional[Path] = None
) -> List[Tuple[str, str]]:
    """Phase 2 (QUERY Navigation): queries the multi-file LLM Wiki index and graph,
    following 1-hop [[wikilinks]] across concepts, entities, and sources to assemble
    a strongly connected context for diagnostic synthesis."""
    radice = inizializza_vault_wiki(radice_vault)
    parole_q = [
        p.lower().strip()
        for p in re.findall(r"\w+", problema)
        if len(p) >= 4 and p.lower() not in ("della", "delle", "degli", "sono", "come", "quale", "quali", "cosa")
    ]
    if not parole_q:
        return []

    tutti_files: List[Path] = []
    for sottocartella in ("concepts", "entities", "sources"):
        dir_s = radice / "wiki" / sottocartella
        if dir_s.is_dir():
            tutti_files.extend(dir_s.glob("*.md"))
    punteggi: List[Tuple[int, Path]] = []

    for f_p in tutti_files:
        if f_p.name in ("index.md", "log.md"):
            continue
        try:
            txt = f_p.read_text(encoding="utf-8", errors="ignore").lower()
            score = sum(3 for w in parole_q if w in f_p.stem.lower())
            score += sum(1 for w in parole_q if w in txt)
            if score > 0:
                punteggi.append((score, f_p))
        except OSError:
            pass

    punteggi.sort(key=lambda x: x[0], reverse=True)
    selezionati: List[Path] = [p for _, p in punteggi[:3]]
    hop_aggiunti: List[Path] = []

    for p_sel in selezionati:
        try:
            testo_sel = p_sel.read_text(encoding="utf-8", errors="ignore")
            wikilinks = re.findall(r"\[\[([^\[\]|]+)(?:\|[^\[\]]+)?\]\]", testo_sel)
            for wl in wikilinks:
                slug_wl = _slugifica(wl)
                for cand in tutti_files:
                    if cand.stem.lower() == slug_wl and cand not in selezionati and cand not in hop_aggiunti:
                        hop_aggiunti.append(cand)
                        break
        except OSError:
            pass

    risultati: List[Tuple[str, str]] = []
    for path_fin in (selezionati + hop_aggiunti)[:5]:
        try:
            risultati.append((path_fin.stem, path_fin.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            pass
    return risultati


def esegui_lint_wiki(radice_vault: Optional[Path] = None) -> dict:
    """Phase 3 (LINT / Health Check): scans all vault Markdown files for broken or orphan
    [[wikilinks]], auto-heals orphan pages by creating missing concept files with backlink
    context, updates index.md, and records an audit log entry."""
    radice = inizializza_vault_wiki(radice_vault)
    tutti_files = {
        f_p.stem.lower(): f_p
        for f_p in (radice / "wiki").glob("*/*.md")
        if f_p.name not in ("index.md", "log.md")
    }

    orfani_riparati = 0
    link_aggiunti = 0
    timestamp_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for stem_sorgente, path_sorgente in list(tutti_files.items()):
        try:
            testo = path_sorgente.read_text(encoding="utf-8", errors="ignore")
            wikilinks = re.findall(r"\[\[([^\[\]|]+)(?:\|[^\[\]]+)?\]\]", testo)
            for wl in wikilinks:
                slug_wl = _slugifica(wl)
                if slug_wl not in tutti_files:
                    f_orfano = radice / "wiki" / "concepts" / f"{slug_wl}.md"
                    nome_bello = wl.replace("-", " ").title()
                    contenuto_orfano = (
                        f"---\n"
                        f"title: \"{nome_bello}\"\n"
                        f"type: \"concept\"\n"
                        f"domain: \"auto-lint\"\n"
                        f"updated: \"{timestamp_iso}\"\n"
                        f"---\n\n"
                        f"# {nome_bello}\n\n"
                        f"Concetto rilevato e autogenerato dal controllo di integrita (LLM Wiki Lint) "
                        f"a partire dal collegamento trovato in `[[{stem_sorgente}]]`.\n\n"
                        f"## Fonti (Backlinks)\n"
                        f"- [[{stem_sorgente}]]\n"
                    )
                    f_orfano.write_text(contenuto_orfano, encoding="utf-8")
                    tutti_files[slug_wl] = f_orfano
                    orfani_riparati += 1
        except OSError as err:
            log.warning("Errore durante lint file %s: %s", path_sorgente, err)

    _aggiorna_indice_wiki(radice)
    _scrivi_voce_log_wiki(
        "LINT",
        "vault-health",
        f"Riparati {orfani_riparati} orfani su {len(tutti_files)} pagine totali",
        radice,
    )

    return {
        "pagine_totali": len(tutti_files),
        "orfani_riparati": orfani_riparati,
        "link_aggiunti": link_aggiunti,
        "stato_salute": "OTTIMO" if orfani_riparati == 0 else "RIPARATO",
    }


def genera_presentazione_marp(
    problema: str, esito: dict, radice_vault: Optional[Path] = None
) -> Tuple[str, Path]:
    """Phase 4 (MARP Presentation): converts a verified diagnostic result into a
    5-slide Markdown presentation conforming to MARP syntax (marp: true), saving to
    wiki/presentations/<slug>-marp.md and updating the vault index and log."""
    radice = inizializza_vault_wiki(radice_vault)
    slug_p = _slugifica(problema)
    timestamp_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    risultato = esito.get("risultato") or {}
    semaforo = esito.get("semaforo", "VERDE")
    s_max = esito.get("s_max", 0.0)
    nodo = esito.get("colore_nodo_ewd496a", "NERO")
    principio = risultato.get("principio_guida_unico", "Prescrizione Tecnica Certificata")
    azione = risultato.get("azione_correttiva_singola", "Applicare le prescrizioni della fonte.")
    verifica = risultato.get("esperimento_di_verifica_pratica", "Verificare corrispondenza numerica.")
    scartati = risultato.get("elementi_scartati_per_non_fare_mucchio") or []
    scartati_md = "\n".join(f"- {s}" for s in scartati[:3]) or "- Nessuna ipotesi alternativa rilevata."
    sintesi_pulita = (esito.get("risposta_discorsiva") or "").strip()

    frammenti = esito.get("frammenti_usati") or []
    wikilinks_fonti = "\n".join(
        f"- [[{_estrai_slug_fonte_da_frammento(f)}]]: {_sintetizza_etichetta_frammento(f, max_len=100)}"
        for f in frammenti[:4]
    ) or "- [[archivio-tecnico]]: Documento d'archivio certificato"

    testo_marp = (
        f"---\n"
        f"marp: true\n"
        f"theme: default\n"
        f"paginate: true\n"
        f"---\n\n"
        f"# {problema}\n"
        f"### Bottega L. — Gen III LLM Wiki Presentazione Esecutiva\n\n"
        f"- **Semaforo RAG:** `{semaforo}` (`s_max={s_max}`)\n"
        f"- **Barriera Numerica (Strato D):** `Nodo {nodo}`\n"
        f"- **Data Compilazione:** {timestamp_iso}\n\n"
        f"---\n\n"
        f"# 1. Principio Guida e Diagnosi\n"
        f"### Principio di Necessita (Strato L) & Zero Mucchio\n\n"
        f"- **Principio Selezionato:** {principio}\n\n"
        f"**Ipotesi Falsificate / Scartate:**\n"
        f"{scartati_md}\n\n"
        f"---\n\n"
        f"# 2. Prescrizioni e Regole Didattiche\n"
        f"### Evidenze Estratte dalla Fonte Certificata\n\n"
        f"{sintesi_pulita[:700]}\n\n"
        f"---\n\n"
        f"# 3. Azione Correttiva e Verifica\n"
        f"### Strato D — Weakest Preconditions wp(S, R)\n\n"
        f"- **Azione Operativa:** {azione}\n"
        f"- **Controllo Pratico:** {verifica}\n\n"
        f"---\n\n"
        f"# 4. Riferimenti Documentali e Grafo\n"
        f"### Wikilinks e Fonti del Vault\n\n"
        f"{wikilinks_fonti}\n"
    )

    file_marp = radice / "wiki" / "presentations" / f"{slug_p}-marp.md"
    try:
        file_marp.write_text(testo_marp, encoding="utf-8")
    except OSError as err:
        log.warning("Impossibile salvare presentazione MARP: %s", err)

    _aggiorna_indice_wiki(radice)
    _scrivi_voce_log_wiki("MARP", f"{slug_p}-marp", "Generata presentazione a 5 slide", radice)

    return testo_marp, file_marp


def costruisci_grafo_dot_wiki(radice_vault: Optional[Path] = None) -> str:
    """Builds a Graphviz DOT representation of the Obsidian Wiki graph, coloring nodes
    by section (sources=blue, concepts=green, entities=gold, synthesis=purple, presentations=pink)
    with directed edges along all [[wikilinks]]."""
    radice = inizializza_vault_wiki(radice_vault)
    righe_dot = [
        "digraph ObsidianWikiGraph {",
        "  rankdir=LR;",
        "  bgcolor=\"transparent\";",
        "  node [shape=box, style=\"filled,rounded\", fontname=\"Helvetica\", fontsize=10, penwidth=1.5];",
        "  edge [color=\"#888888\", arrowsize=0.7];",
    ]

    colori = {
        "sources": ("#D0E8FF", "#3B82F6"),
        "concepts": ("#D4EDDA", "#10B981"),
        "entities": ("#FFE8B6", "#F59E0B"),
        "synthesis": ("#E2D9F3", "#8B5CF6"),
        "presentations": ("#FADBD8", "#EF4444"),
    }

    nodi_aggiunti: Set[str] = set()
    archi_aggiunti: Set[Tuple[str, str]] = set()

    for tipo, (fill_col, border_col) in colori.items():
        cartella = radice / "wiki" / tipo
        if not cartella.exists():
            continue
        for f_p in cartella.glob("*.md"):
            slug = f_p.stem
            titolo = slug.replace("-", " ")
            try:
                txt = f_p.read_text(encoding="utf-8", errors="ignore")
                m_tit = re.search(r"^title:\s*[\"']?([^\"'\n]+)[\"']?", txt, re.MULTILINE)
                if m_tit:
                    titolo = m_tit.group(1).strip()
            except OSError:
                txt = ""
            label_breve = titolo[:24] + ("..." if len(titolo) > 24 else "")
            righe_dot.append(
                f'  "{slug}" [label="{label_breve}", fillcolor="{fill_col}", color="{border_col}"];'
            )
            nodi_aggiunti.add(slug)

            wikilinks = re.findall(r"\[\[([^\[\]|]+)(?:\|[^\[\]]+)?\]\]", txt)
            for wl in wikilinks:
                target_slug = _slugifica(wl)
                if target_slug and (slug, target_slug) not in archi_aggiunti:
                    archi_aggiunti.add((slug, target_slug))

    for sorg, dest in archi_aggiunti:
        if dest not in nodi_aggiunti:
            righe_dot.append(
                f'  "{dest}" [label="{dest.replace("-", " ")[:20]}", fillcolor="#F3F4F6", color="#9CA3AF", style="dashed,filled,rounded"];'
            )
            nodi_aggiunti.add(dest)
        righe_dot.append(f'  "{sorg}" -> "{dest}";')

    if not nodi_aggiunti:
        righe_dot.append(
            '  "vault_inizializzato" [label="Bottega Wiki Vault\\n(Carica un documento per generare il Grafo)", fillcolor="#D0E8FF", color="#3B82F6"];'
        )

    righe_dot.append("}")
    return "\n".join(righe_dot)


def esporta_vault_wiki_zip(radice_vault: Optional[Path] = None) -> bytes:
    """Exports the entire Obsidian-compatible LLM Wiki Vault as a standalone .zip archive."""
    radice = inizializza_vault_wiki(radice_vault)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for elemento in sorted(radice.rglob("*")):
            if elemento.is_file():
                relativo = elemento.relative_to(radice)
                zf.write(elemento, arcname=str(relativo).replace("\\", "/"))
    return buffer.getvalue()


def importa_vault_wiki_zip(
    zip_bytes: bytes, radice_vault: Optional[Path] = None
) -> int:
    """Safely extracts an exported bottega_obsidian_vault.zip archive into the local
    wiki_vault directory, re-indexing its documents into memory and running wiki lint."""
    radice = inizializza_vault_wiki(radice_vault)
    buffer = io.BytesIO(zip_bytes)
    n_importati = 0
    radice_risolta = radice.resolve()

    with zipfile.ZipFile(buffer, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            percorso_rel = Path(info.filename)
            destinazione = (radice / percorso_rel).resolve()
            if not str(destinazione).startswith(str(radice_risolta)):
                continue

            destinazione.parent.mkdir(parents=True, exist_ok=True)
            dati = zf.read(info.filename)
            destinazione.write_bytes(dati)
            if destinazione.suffix.lower() == ".md":
                n_importati += 1
                if "sources" in str(destinazione) or "concepts" in str(destinazione):
                    try:
                        testo = dati.decode("utf-8", errors="ignore")
                        titolo_doc = destinazione.stem
                        titoli_ram = {
                            v.get("titolo")
                            for v in _ARCHIVIO_MEMORIA_RAM
                        }
                        if titolo_doc not in titoli_ram and testo.strip():
                            incasella_e_salva(
                                "tecnico", titolo_doc, [(destinazione.stem, testo)]
                            )
                    except (UnicodeDecodeError, OSError):
                        pass

    esegui_lint_wiki(radice)
    _aggiorna_indice_wiki(radice)
    _scrivi_voce_log_wiki(
        "IMPORT_ZIP", "vault", f"Importati {n_importati} file Markdown", radice
    )
    return n_importati


def costruisci_diagramma_flusso_risposta_dot(
    problema: str, esito: Optional[Dict[str, Any]] = None
) -> str:
    """Generates an action flowchart in Graphviz DOT format (Napkin.ai style)
    with 4 sequential horizontal nodes:
    1. Question / Case (Blue)
    2. Key Rule / Source (Green or Red if ROJO)
    3. What To Do (Action) (Amber)
    4. Final Verification (Purple)
    Safe string sanitization: quotes and backslashes converted to spaces."""
    dati_esito = esito if isinstance(esito, dict) else {}
    semaforo = str(dati_esito.get("semaforo") or "AMBAR").upper()
    risultato = dati_esito.get("risultato")
    res = risultato if isinstance(risultato, dict) else {}

    def _sanifica(val: Any) -> str:
        if not val:
            return ""
        s = str(val).replace('"', ' ').replace('\\', ' ').replace('\n', ' ').replace('\r', ' ')
        return re.sub(r"\s+", " ", s).strip()

    q_raw = _sanifica(problema or "Question / Case")
    q_txt = tronca_senza_spezzare_parola(q_raw, 70, suffisso="...")

    regola_raw = ""
    if res.get("principio_guida_unico"):
        regola_raw = str(res["principio_guida_unico"])
    elif res.get("fonte_prioritaria_selezionata"):
        regola_raw = str(res["fonte_prioritaria_selezionata"])
    elif semaforo == "ROJO":
        regola_raw = str(res.get("dato_esatto_mancante") or "Document missing or insufficient confidence")
    elif dati_esito.get("frammenti_usati"):
        regola_raw = str(dati_esito["frammenti_usati"][0])
    if not regola_raw:
        regola_raw = "Documental Rule / Principle"

    if "###" in regola_raw or "[page" in regola_raw.lower() or "\n" in regola_raw:
        for r_cand in regola_raw.splitlines():
            r_c = r_cand.strip().lstrip("#").strip()
            if r_c and not _e_riga_codice_python(r_c):
                r_c = re.sub(r"\[(?:page|pagina|slide)\s*\d+\]\s*", "", r_c, flags=re.IGNORECASE).strip()
                if r_c:
                    regola_raw = r_c
                    break
        else:
            regola_raw = re.sub(r"^###\s*", "", regola_raw)
            regola_raw = re.sub(r"\[(?:page|pagina|slide)\s*\d+\]\s*", "", regola_raw, flags=re.IGNORECASE).strip()

    rule_txt = tronca_senza_spezzare_parola(_sanifica(regola_raw), 70, suffisso="...")

    if semaforo == "ROJO":
        r_fill = "#FADBD8"
        r_col = "#EF4444"
    else:
        r_fill = "#D4EDDA"
        r_col = "#10B981"

    azione_raw = ""
    if res.get("azione_correttiva_singola"):
        azione_raw = str(res["azione_correttiva_singola"])
    elif semaforo == "ROJO" and res.get("query_chirurgica_esterna"):
        azione_raw = f"Acquire: {res['query_chirurgica_esterna']}"
    elif res.get("risposta_finale_discorsiva"):
        azione_raw = str(res["risposta_finale_discorsiva"])
    elif dati_esito.get("risposta_discorsiva"):
        azione_raw = str(dati_esito["risposta_discorsiva"])
    if not azione_raw:
        azione_raw = "Execute validated procedure"

    if "###" in azione_raw or "[page" in azione_raw.lower() or "\n" in azione_raw:
        for a_cand in azione_raw.splitlines():
            a_c = a_cand.strip().lstrip("-* ").strip()
            if a_c and not _e_riga_codice_python(a_c):
                a_c = re.sub(r"^###\s*", "", a_c)
                a_c = re.sub(r"\[(?:page|pagina|slide)\s*\d+\]\s*", "", a_c, flags=re.IGNORECASE).strip()
                if a_c:
                    azione_raw = a_c
                    break
        else:
            azione_raw = re.sub(r"^###\s*", "", azione_raw)
            azione_raw = re.sub(r"\[(?:page|pagina|slide)\s*\d+\]\s*", "", azione_raw, flags=re.IGNORECASE).strip()

    act_txt = tronca_senza_spezzare_parola(_sanifica(azione_raw), 80, suffisso="...")

    stato_memoria = str(dati_esito.get("stato_memoria") or res.get("stato_memoria") or "")
    if not stato_memoria:
        stato_memoria = "BLOCCO_SICUREZZA" if semaforo == "ROJO" else "SOLUZIONE_FONDATA"
    colore_nodo = str(dati_esito.get("colore_nodo_ewd496a") or "NERO")
    text_ver = f"{stato_memoria} ({semaforo}) - Nodo {colore_nodo}"
    ver_txt = tronca_senza_spezzare_parola(_sanifica(text_ver), 70, suffisso="...")

    return (
        "digraph VisualStepFlow {\n"
        "    rankdir=LR;\n"
        '    node [shape=box, style="filled,rounded", fontname="Helvetica", fontsize=10];\n'
        '    edge [color="#64748B", penwidth=1.5];\n\n'
        f'    q [label="1. Question / Case\\n{q_txt}", fillcolor="#D0E8FF", color="#3B82F6"];\n'
        f'    r [label="2. Key Rule / Source\\n{rule_txt}", fillcolor="{r_fill}", color="{r_col}"];\n'
        f'    a [label="3. What To Do (Action)\\n{act_txt}", fillcolor="#FFE8B6", color="#F59E0B"];\n'
        f'    c [label="4. Final Verification\\n{ver_txt}", fillcolor="#E2D9F3", color="#8B5CF6"];\n\n'
        "    q -> r -> a -> c;\n"
        "}"
    )


if __name__ == "__main__":
    args = sys.argv[1:]
    modalita_json = "--json" in args
    domanda_arg = " ".join(a for a in args if a != "--json").strip()
    if not domanda_arg:
        domanda_arg = "Test diagnosi predefinita"
    risultato_cli = risolvi_da_artigiano(domanda_arg)
    if modalita_json:
        print(json.dumps(risultato_cli, ensure_ascii=False, indent=2))
    else:
        print(risultato_cli.get("risposta_discorsiva", ""))
