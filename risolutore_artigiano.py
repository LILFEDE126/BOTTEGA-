#!/usr/bin/env python3
"""Layer 3 (THE): Closed-loop diagnostic solver (Zero Clutter / Zero Mucchio).
Supports any input language (EN, ES, IT, etc.) with automatic search translation and response matching."""

from typing import Callable, List, Literal, Optional, Tuple
import psycopg2
import requests
from pydantic import BaseModel, Field

from logging_bottega import log
from grounding_numerico import (
    arrotonda_esatto_el_x8,
    classifica_nodo_tricolore,
    verifica_conservazione_percentuali_decimal,
)
from store_pgvector import incasella_e_salva, recupera_con_semaforo
from client_ollama import chiama_ollama_json, traduci_query_per_ricerca


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
        description="The SINGLE simplest root cause (Leonardo's Principle of Necessity)"
    )
    azione_correttiva_singola: str = Field(
        description="The single targeted intervention to execute step-by-step without mixing alternatives"
    )
    esperimento_di_verifica_pratica: str = Field(
        description="How to objectively measure whether postcondition R is satisfied"
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
        "Agisci come un maestro artigiano e ingegnere diagnostico (Metodo Leonardo + Dijkstra EWD401).\n"
        "LINGUA / LANGUAGE / IDIOMA: Rispondi nella STESSA LINGUA usata nel PROBLEMA qui sotto "
        "(Reply in the exact same language used in the problem below: English, Español, Italiano, etc.).\n"
        "REGOLE TASSATIVE:\n"
        "1. NON FARE MUCCHIO (ZERO CLUTTER): Scegli UN SOLO principio guida dal contesto qui sotto e dichiara "
        "esplicitamente quali altri frammenti o ipotesi hai scartato.\n"
        "2. ZERO CIFRE INVENTATE: Ogni numero, percentuale, importo o pressione che scrivi DEVE esistere "
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


def risolvi_da_artigiano(
    problema: str,
    dominio: str = "generale",
    cercatore_esterno_fn: Optional[Callable[[str], List[Tuple[str, str]]]] = None,
    ipotesi_gia_escluse: Optional[List[str]] = None,
    llm_fn: Callable = chiama_ollama_json,
) -> dict:
    """Universal closed-loop diagnostic cycle with cross-lingual query translation."""
    if not problema or not problema.strip():
        raise ValueError("Violazione EWD401 (Miracolo Escluso): il problema non puo' essere vuoto.")

    query_multilingua = traduci_query_per_ricerca(problema)
    try:
        rag = recupera_con_semaforo(query_multilingua, dominio=dominio, top_k=3)
    except (psycopg2.Error, requests.exceptions.RequestException, RuntimeError):
        rag = {"semaforo": "ROJO", "s_max": 0.0, "s_dominio": 0.0, "frammenti": []}

    semaforo = rag["semaforo"]
    ricerca_esterna_eseguita = False

    if semaforo == "ROJO":
        piano: PianoRicercaArtigiano = llm_fn(
            "You are a diagnostic engineer respecting Dijkstra's Law of the Excluded Miracle "
            "(EWD401: wp(S, false) = false). Your memory does NOT contain sufficient data (Semaforo ROJO). "
            "It is FORBIDDEN to guess or mix random solutions. Isolate certain facts, state which single "
            "datum is missing, and formulate the exact search query. "
            "IMPORTANT: Write all field values in the EXACT SAME LANGUAGE used in the user's problem.",
            f"PROBLEMA IMPREVISTO:\n{problema}",
            PianoRicercaArtigiano,
        )
        if cercatore_esterno_fn is not None:
            nuovi_blocchi = cercatore_esterno_fn(piano.query_chirurgica_esterna)
            if nuovi_blocchi:
                ricerca_esterna_eseguita = True
                try:
                    incasella_e_salva(dominio, f"Ricerca: {piano.dato_esatto_mancante}", nuovi_blocchi)
                    rag = recupera_con_semaforo(query_multilingua, dominio=dominio, top_k=3)
                    semaforo = rag["semaforo"]
                except (psycopg2.Error, requests.exceptions.RequestException, RuntimeError):
                    rag = {
                        "semaforo": "AMBAR",
                        "s_max": 0.55,
                        "s_dominio": 0.50,
                        "frammenti": [
                            {"id": idx, "testo": f"[{dominio.upper()}] {sez}: {txt}", "similitudine": 0.55}
                            for idx, (sez, txt) in enumerate(nuovi_blocchi, start=1)
                        ],
                    }
                    semaforo = "AMBAR"

        if semaforo == "ROJO":
            log.info(
                "Artigiano in stop onesto (Semaforo ROJO): richiesta ricerca '%s'",
                piano.query_chirurgica_esterna,
                extra={"code": "ART_ROJO_001"},
            )
            return {
                "semaforo": semaforo,
                "s_max": float(arrotonda_esatto_el_x8(rag["s_max"], 4)),
                "modalita": "RICERCA_PRIMA_DI_AGIRE",
                "ricerca_esterna_eseguita": ricerca_esterna_eseguita,
                "ipotesi_escluse_applicate": list(ipotesi_gia_escluse or []),
                "colore_nodo_ewd496a": "GRIGIO",
                "percentuali_conservate": True,
                "risultato": piano.model_dump(),
                "cifre_non_ancorate": [],
            }

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

    soluzione: SoluzioneArtigiano = llm_fn(
        "You are a master diagnostic engineer applying Leonardo's Principle of Necessity and Dijkstra's "
        "Weakest Preconditions wp(S, R) (EWD401). "
        "ZERO CLUTTER RULE (REGOLA ZERO MUCCHIO): Select ONLY ONE guiding fragment from those retrieved, "
        "list in 'elementi_scartati_per_non_fare_mucchio' what you excluded, identify the violated invariant, "
        "and formulate ONE SINGLE causal hypothesis with its practical verification test. "
        "IMPORTANT: Write all text fields in the EXACT SAME LANGUAGE used in the PROBLEMA below "
        "(English, Español, Italiano, etc.), preserving all exact numbers and percentages from the context.",
        f"FRAMMENTI RECUPERATI ({semaforo}):\n{contesto_rag}\n\n"
        f"PROBLEMA:\n{problema}{vincolo_esclusioni}",
        SoluzioneArtigiano,
    )

    scarti_finali = list(soluzione.elementi_scartati_per_non_fare_mucchio)
    for ip_esclusa in escluse_pulite:
        if not any(ip_esclusa.lower() in s.lower() for s in scarti_finali):
            scarti_finali.append(f"[Falsificata sul campo] {ip_esclusa}")
    soluzione.elementi_scartati_per_non_fare_mucchio = scarti_finali

    testo_uscita = (
        f"{soluzione.principio_guida_unico}\n"
        f"{soluzione.ipotesi_causale_unica}\n"
        f"{soluzione.azione_correttiva_singola}"
    )
    contesto_totale = f"{problema}\n{contesto_rag}"
    colore_nodo, cifre_errate = classifica_nodo_tricolore(testo_uscita, contesto_totale)
    pct_ok = verifica_conservazione_percentuali_decimal(testo_uscita, contesto_totale)

    if not pct_ok and colore_nodo == "NERO":
        colore_nodo = "GRIGIO"
        log.warning(
            "Artigiano: la soluzione ha perso una percentuale ufficiale del contesto",
            extra={"code": "ART_PCT_001"},
        )

    return {
        "semaforo": semaforo,
        "s_max": float(arrotonda_esatto_el_x8(rag["s_max"], 4)),
        "modalita": "AZIONE_SINGOLA_VERIFICABILE",
        "ricerca_esterna_eseguita": ricerca_esterna_eseguita,
        "ipotesi_escluse_applicate": escluse_pulite,
        "colore_nodo_ewd496a": colore_nodo,
        "percentuali_conservate": pct_ok,
        "risultato": soluzione.model_dump(),
        "cifre_non_ancorate": cifre_errate,
    }