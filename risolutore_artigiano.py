#!/usr/bin/env python3
"""Layer 3 (THE): Closed-loop diagnostic solver (Zero Clutter / Zero Mucchio).
Supports any input language (EN, ES, IT, etc.) with automatic search translation,
natural-language final response synthesis and deterministic RAG fallback."""

from typing import Callable, List, Literal, Optional, Tuple
import psycopg2
import requests
from pydantic import BaseModel, Field

from logging_bottega import log
from grounding_numerico import (
    arrotonda_esatto_el_x8,
    classifica_nodo_tricolore,
    estrai_percentuali_decimal,
    verifica_conservazione_percentuali_decimal,
)
from store_pgvector import incasella_e_salva, recupera_con_semaforo
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
        description="The SINGLE simplest root cause (Leonardo's Principle of Necessity)"
    )
    azione_correttiva_singola: str = Field(
        description="The single targeted intervention to execute step-by-step without mixing alternatives"
    )
    esperimento_di_verifica_pratica: str = Field(
        description="How to objectively measure whether postcondition R is satisfied"
    )


_ETICHETTE_FALSIFICATA = {
    "en": "[Falsified in the field]",
    "es": "[Falsificada en el campo]",
    "it": "[Falsificata sul campo]",
}

_ETICHETTE_SCARTATO = {
    "en": "[Discarded for Zero Clutter]",
    "es": "[Descartado por Cero Montón]",
    "it": "[Scartato per Zero Mucchio]",
}


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


def _costruisci_soluzione_deterministica(
    problema: str,
    frammenti: List[dict],
    escluse_pulite: List[str],
    lingua: str = "it",
) -> SoluzioneArtigiano:
    """Synthesizes a strictly grounded SoluzioneArtigiano directly from retrieved RAG fragments
    when the external LLM provider is offline or rate-limited, preserving all exact source numbers."""
    principale = frammenti[0]["testo"] if frammenti else problema.strip()
    tag_scarto = _ETICHETTE_SCARTATO.get(lingua, _ETICHETTE_SCARTATO["it"])
    tag_fals = _ETICHETTE_FALSIFICATA.get(lingua, _ETICHETTE_FALSIFICATA["it"])
    scartati = [f"{tag_scarto} {f['testo']}" for f in frammenti[1:]]
    for ip_escl in escluse_pulite:
        scartati.append(f"{tag_fals} {ip_escl}")

    if lingua == "en":
        return SoluzioneArtigiano(
            risposta_finale_discorsiva=(
                f"Based on the documents analyzed in the archive for the query ({problema.strip()}), "
                f"the primary reference source establishes the following: {principale}"
            ),
            principio_guida_unico=principale,
            elementi_scartati_per_non_fare_mucchio=scartati,
            precondizione_wp_richiesta=(
                "Direct compliance verification on the fragments extracted from the official archive."
            ),
            invariante_violato=(
                "Alignment between the problem requirements and the certified parameters in the documentary source."
            ),
            ipotesi_causale_unica=f"Direct documentary match from the priority source: {principale}",
            azione_correttiva_singola=(
                f"Apply exclusively the parameters and constraints of the selected source to the case: {problema.strip()}"
            ),
            esperimento_di_verifica_pratica=(
                "Verify exact correspondence of all figures, caps, and percentages with the archive text."
            ),
        )
    if lingua == "es":
        return SoluzioneArtigiano(
            risposta_finale_discorsiva=(
                f"Según los documentos analizados en el archivo para la consulta ({problema.strip()}), "
                f"la fuente de referencia establece lo siguiente: {principale}"
            ),
            principio_guida_unico=principale,
            elementi_scartati_per_non_fare_mucchio=scartati,
            precondizione_wp_richiesta=(
                "Verificación directa de conformidad sobre los fragmentos extraídos del archivo oficial."
            ),
            invariante_violato=(
                "Alineación entre los requisitos del problema y los parámetros certificados en la fuente documental."
            ),
            ipotesi_causale_unica=f"Respaldo documental directo de la fuente prioritaria: {principale}",
            azione_correttiva_singola=(
                f"Aplicar exclusivamente los parámetros y límites de la fuente seleccionada al caso: {problema.strip()}"
            ),
            esperimento_di_verifica_pratica=(
                "Comprobar la correspondencia exacta de todas las cifras, topes y porcentajes con el texto del archivo."
            ),
        )
    return SoluzioneArtigiano(
        risposta_finale_discorsiva=(
            f"In base ai documenti analizzati nell'archivio per il quesito ({problema.strip()}), "
            f"la fonte di riferimento stabilisce quanto segue: {principale}"
        ),
        principio_guida_unico=principale,
        elementi_scartati_per_non_fare_mucchio=scartati,
        precondizione_wp_richiesta=(
            "Verifica diretta di conformita' sui frammenti estratti dall'archivio ufficiale."
        ),
        invariante_violato=(
            "Allineamento tra i requisiti del problema e i parametri certificati nella fonte documentale."
        ),
        ipotesi_causale_unica=f"Riscontro documentale diretto dalla fonte prioritaria: {principale}",
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

    lingua_rilevata = rileva_lingua_testo(problema)
    blocco_lingua = _istruzione_lingua_tassativa(lingua_rilevata)
    query_multilingua = traduci_query_per_ricerca(problema)
    try:
        rag = recupera_con_semaforo(query_multilingua, dominio=dominio, top_k=5)
    except (psycopg2.Error, requests.exceptions.RequestException, RuntimeError):
        rag = {"semaforo": "ROJO", "s_max": 0.0, "s_dominio": 0.0, "frammenti": []}

    semaforo = rag["semaforo"]
    ricerca_esterna_eseguita = False

    if semaforo == "ROJO":
        try:
            piano: PianoRicercaArtigiano = llm_fn(
                f"{blocco_lingua}\n\n"
                "You are a diagnostic engineer respecting Dijkstra's Law of the Excluded Miracle "
                "(EWD401: wp(S, false) = false). Your memory does NOT contain sufficient data (Semaforo ROJO). "
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
            nuovi_blocchi = cercatore_esterno_fn(piano.query_chirurgica_esterna)
            if nuovi_blocchi:
                ricerca_esterna_eseguita = True
                try:
                    incasella_e_salva(dominio, f"Ricerca: {piano.dato_esatto_mancante}", nuovi_blocchi)
                    rag = recupera_con_semaforo(query_multilingua, dominio=dominio, top_k=5)
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
            piano_dict = piano.model_dump()
            return {
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

    if (
        cercatore_esterno_fn is not None
        and not ricerca_esterna_eseguita
        and any(k in problema.lower() for k in ("bando", "voucher", "camera di commercio", "reggio emilia"))
    ):
        blocchi_normativi = cercatore_esterno_fn(problema)
        testi_esistenti = " ".join(f.get("testo", "") for f in rag.get("frammenti", []))
        for sez_n, txt_n in blocchi_normativi:
            if txt_n not in testi_esistenti:
                rag["frammenti"].append({
                    "id": len(rag["frammenti"]) + 100,
                    "titolo": "Prontuario Normativo",
                    "sezione": sez_n,
                    "testo": f"[{dominio.upper()}] {sez_n}: {txt_n}",
                    "similitudine": 0.85,
                })

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
            "You are a master diagnostic engineer applying Leonardo's Principle of Necessity and Dijkstra's "
            "Weakest Preconditions wp(S, R) (EWD401). "
            "In 'risposta_finale_discorsiva', write a clear, complete, natural-language answer (4-6 sentences) "
            "that any person can easily read and understand, directly answering the user's question with the exact "
            "numbers and rules from the retrieved fragments (stating clearly what is covered/valid, what is excluded, and why). "
            "ZERO CLUTTER RULE (REGOLA ZERO MUCCHIO): Select ONLY ONE guiding principle from those retrieved, "
            "list in 'elementi_scartati_per_non_fare_mucchio' what you excluded, identify the violated invariant, "
            "and formulate ONE SINGLE causal hypothesis with its practical verification test. "
            "CRITICAL NUMERIC RULE: Every single number or percentage you write MUST appear identically in FRAMMENTI RECUPERATI or PROBLEMA.\n\n"
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

    tag_fals_uscita = _ETICHETTE_FALSIFICATA.get(lingua_rilevata, _ETICHETTE_FALSIFICATA["it"])
    scarti_finali = list(soluzione.elementi_scartati_per_non_fare_mucchio)
    for ip_esclusa in escluse_pulite:
        if not any(ip_esclusa.lower() in s.lower() for s in scarti_finali):
            scarti_finali.append(f"{tag_fals_uscita} {ip_esclusa}")
    soluzione.elementi_scartati_per_non_fare_mucchio = scarti_finali

    testo_uscita = (
        f"{soluzione.risposta_finale_discorsiva}\n"
        f"{soluzione.principio_guida_unico}\n"
        f"{soluzione.ipotesi_causale_unica}\n"
        f"{soluzione.azione_correttiva_singola}"
    )
    contesto_totale = f"{problema}\n{contesto_rag}"
    colore_nodo, cifre_errate = classifica_nodo_tricolore(testo_uscita, contesto_totale)

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
        "risposta_discorsiva": formatta_risposta_artigiano_leggibile(
            sol_dict, "AZIONE_SINGOLA_VERIFICABILE", lingua=lingua_rilevata
        ),
        "frammenti_usati": [f.get("testo", "") for f in rag.get("frammenti", [])],
        "cifre_non_ancorate": cifre_errate,
    }
