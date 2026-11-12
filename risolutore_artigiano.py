#!/usr/bin/env python3
"""Layer 3 (THE): Closed-loop diagnostic solver (Zero Clutter / Zero Mucchio).
Supports any input language (EN, ES, IT, etc.) with automatic search translation,
natural-language final response synthesis and deterministic RAG fallback."""

import re
from types import MappingProxyType
from typing import Callable, List, Literal, Optional, Set, Tuple
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


def svuota_pagine_continua(dominio: Optional[str] = None) -> None:
    """Clears pending continuation pages from memory."""
    with SEGRETARIO_THE.sezione_sacra(dominio or "generale"):
        if dominio is None:
            _REGISTRO_CONTINUAZIONI_MEMORIA.clear()
        else:
            _REGISTRO_CONTINUAZIONI_MEMORIA.pop(dominio, None)


def _costruisci_soluzione_deterministica(
    problema: str,
    frammenti: List[dict],
    escluse_pulite: List[str],
    lingua: str = "it",
) -> SoluzioneArtigiano:
    """Synthesizes a strictly grounded SoluzioneArtigiano directly from retrieved RAG fragments
    when the external LLM provider is offline or rate-limited, preserving all exact source numbers."""
    principale = frammenti[0]["testo"] if frammenti else problema.strip()
    principale_breve = _sintetizza_etichetta_frammento(principale, max_len=MAX_CARATTERI_SINTESI_FALLBACK)
    tag_scarto = _ETICHETTE_SCARTATO.get(lingua, _ETICHETTE_SCARTATO["it"])
    tag_fals = _ETICHETTE_FALSIFICATA.get(lingua, _ETICHETTE_FALSIFICATA["it"])
    scartati = [
        f"{tag_scarto} {_sintetizza_etichetta_frammento(frammento['testo'], max_len=MAX_CARATTERI_SCARTO_DEFAULT)}"
        for frammento in frammenti[1:]
    ]
    for ipotesi_esclusa in escluse_pulite:
        scartati.append(f"{tag_fals} {ipotesi_esclusa}")

    if lingua == "en":
        return SoluzioneArtigiano(
            risposta_finale_discorsiva=principale,
            principio_guida_unico=principale_breve,
            elementi_scartati_per_non_fare_mucchio=scartati,
            precondizione_wp_richiesta=(
                "Direct compliance verification on the fragments extracted from the official archive."
            ),
            invariante_violato=(
                "Alignment between the problem requirements and the certified parameters in the documentary source."
            ),
            ipotesi_causale_unica=f"Direct documentary match from the priority source: {principale_breve}",
            azione_correttiva_singola=(
                f"Apply exclusively the parameters and constraints of the selected source to the case: {problema.strip()}"
            ),
            esperimento_di_verifica_pratica=(
                "Verify exact correspondence of all figures, caps, and percentages with the archive text."
            ),
        )
    if lingua == "es":
        return SoluzioneArtigiano(
            risposta_finale_discorsiva=principale,
            principio_guida_unico=principale_breve,
            elementi_scartati_per_non_fare_mucchio=scartati,
            precondizione_wp_richiesta=(
                "Verificación directa de conformidad sobre los fragmentos extraídos del archivo oficial."
            ),
            invariante_violato=(
                "Alineación entre los requisitos del problema y los parámetros certificados en la fuente documental."
            ),
            ipotesi_causale_unica=f"Respaldo documental directo de la fuente prioritaria: {principale_breve}",
            azione_correttiva_singola=(
                f"Aplicar exclusivamente los parámetros y límites de la fuente seleccionada al caso: {problema.strip()}"
            ),
            esperimento_di_verifica_pratica=(
                "Comprobar la correspondencia exacta de todas las cifras, topes y porcentajes con el texto del archivo."
            ),
        )
    return SoluzioneArtigiano(
        risposta_finale_discorsiva=principale,
        principio_guida_unico=principale_breve,
        elementi_scartati_per_non_fare_mucchio=scartati,
        precondizione_wp_richiesta=(
            "Verifica diretta di conformita' sui frammenti estratti dall'archivio ufficiale."
        ),
        invariante_violato=(
            "Allineamento tra i requisiti del problema e i parametri certificati nella fonte documentale."
        ),
        ipotesi_causale_unica=f"Riscontro documentale diretto dalla fonte prioritaria: {principale_breve}",
        azione_correttiva_singola=(
            f"Applicare esclusivamente i parametri e i vincoli della fonte selezionata al caso: {problema.strip()}"
        ),
        esperimento_di_verifica_pratica=(
            "Controllare la corrispondenza esatta di tutte le cifre, massimali e percentuali con il testo d'archivio."
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


def _intercetta_e_eroga_continua(problema: str, dominio: str, lingua_rilevata: str) -> Optional[dict]:
    """Se la richiesta e' un comando di continuazione, eroga la pagina successiva o notifica di esaurimento."""
    if not e_richiesta_continua(problema):
        return None
    prossima_pagina = estrai_prossima_pagina_continua(dominio)
    if prossima_pagina is not None:
        ancora_in_sospeso = ha_pagine_continua_in_sospeso(dominio)
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
            "risultato": {
                "stato": "CONTINUAZIONE",
                "testo": testo_erogato,
                "in_sospeso": ancora_in_sospeso,
            },
            "risposta_discorsiva": testo_erogato,
            "frammenti_usati": [],
            "cifre_non_ancorate": [],
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
        "risultato": {"stato": "NESSUNA_CONTINUAZIONE"},
        "risposta_discorsiva": msg_vuoto,
        "frammenti_usati": [],
        "cifre_non_ancorate": [],
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
        }
        return rag, semaforo, ricerca_esterna_eseguita, risultato_stop

    return rag, semaforo, ricerca_esterna_eseguita, None


_CHIAVI_ARRICCHIMENTO_PRONTUARIO = frozenset({
    "bando",
    "voucher",
    "camera di commercio",
    "bando reggio emilia",
    "voucher reggio emilia",
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
                        "Answer the user's question directly using the verified external fragments below.\n\n"
                        f"{blocco_lingua}",
                        f"FRAMMENTI RECUPERATI (VERDE):\n{contesto_rag}\n\n"
                        f"PROBLEMA:\n{problema}{vincolo_esclusioni}\n\n"
                        f"{blocco_lingua}",
                        SoluzioneArtigiano,
                    )
                except (RuntimeError, requests.exceptions.RequestException):
                    soluzione = _costruisci_soluzione_deterministica(
                        problema, rag["frammenti"], escluse_pulite, lingua=lingua_rilevata
                    )

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
    limite_turno = max_caratteri_turno if max_caratteri_turno is not None else MAX_CARATTERI_TURNO_DEFAULT
    if len(risposta_discorsiva_piena) > limite_turno:
        pagine = suddividi_in_pagine_con_continua(
            risposta_discorsiva_piena,
            max_caratteri_pagina=limite_turno,
        )
        if len(pagine) > 1:
            imposta_pagine_continua(dominio, pagine[1:])
            risposta_discorsiva_piena = pagine[0]
    else:
        svuota_pagine_continua(dominio)

    return {
        "semaforo": semaforo,
        "s_max": float(arrotonda_esatto_el_x8(rag["s_max"], 4)),
        "modalita": "AZIONE_SINGOLA_VERIFICABILE",
        "lingua": lingua_rilevata,
        "ricerca_esterna_eseguita": ricerca_esterna_eseguita,
        "ipotesi_escluse_applicate": escluse_pulite,
        "colore_nodo_ewd496a": colore_nodo,
        "percentuali_conservate": pct_ok,
        "risultato": sol_dict,
        "risposta_discorsiva": risposta_discorsiva_piena,
        "frammenti_usati": [framm.get("testo", "") for framm in rag.get("frammenti", [])],
        "cifre_non_ancorate": cifre_errate,
    }
