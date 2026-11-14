#!/usr/bin/env python3
"""Layer 2 (THE): Multi-provider LLM client (Ollama + Gemini/Groq/OpenRouter Free API),
deterministic query translation, EWD426 self-stabilization, HTTP 429/404/503 model fallback and EWD316 variant t."""

import json
import re
import time
from types import MappingProxyType
from typing import Callable, Optional, Type, TypeVar
import requests
from pydantic import BaseModel, ValidationError

from config import (
    MAX_PASSI_VARIANTE_T,
    MODELLI_FALLBACK_GEMINI,
    MODELLI_NATIVI_GEMINI_LIVE,
    TIMEOUT_OLLAMA_FALLBACK_SECONDS,
    TIMEOUT_OLLAMA_SECONDS,
    _decodifica_chiave_cloud_default,
    get_llm_endpoint_config,
    opzioni_ollama_deterministiche,
    risolvi_chiave_api,
)
from logging_bottega import log, log_exception
from grounding_numerico import ripara_parola_troncata

T = TypeVar("T", bound=BaseModel)

_REQUESTS_POST_ORIGINALE = requests.post

GLOSSARIO_MULTILINGUA_IT = MappingProxyType({
    "boiler": "caldaia",
    "caldera": "caldaia",
    "pressure": "pressione",
    "presion": "pressione",
    "presión": "pressione",
    "drop": "perdita",
    "loss": "perdita",
    "leak": "perdita",
    "fuga": "perdita",
    "perdida": "perdita",
    "pérdida": "perdita",
    "expansion": "espansione",
    "vessel": "vaso",
    "tank": "vaso",
    "valve": "valvola",
    "valvula": "valvola",
    "válvula": "valvola",
    "cold": "freddo",
    "frio": "freddo",
    "frío": "freddo",
    "customs": "doganale",
    "aduana": "doganale",
    "arancel": "dazio",
    "duty": "dazio",
    "tariff": "dazio",
    "aluminum": "alluminio",
    "aluminium": "alluminio",
    "aluminio": "alluminio",
    "vat": "iva",
    "water": "acqua",
    "agua": "acqua",
    "hammer": "ariete",
    "ariete": "ariete",
    "overpressure": "sovrappressione",
    "sobrepresion": "sovrappressione",
    "pipes": "tubazioni",
    "tuberias": "tubazioni",
    "price": "prezzo",
    "precio": "prezzo",
    "retail": "mercato",
    "shirt": "maglia",
    "shorts": "pantaloncino",
    "margin": "margine",
    "margen": "margine",
    "months": "mesi",
    "meses": "mesi",
    "website": "sito",
    "sitio": "sito",
    "brochures": "brochure",
    "folletos": "brochure",
    "budget": "budget",
    "presupuesto": "budget",
    "percentage": "percentuale",
    "porcentaje": "percentuale",
    "requirements": "requisiti",
    "requisitos": "requisiti",
    "rent": "fitto fitti",
    "prepaid": "risconto attivo",
    "august": "agosto",
    "december": "dicembre",
    "legal": "legali",
    "fee": "parcella spese",
    "withholding": "ritenuta",
    "supplier": "fornitori",
    "inventory": "rimanenze magazzino",
    "march": "marzo",
    "weighted": "ponderato",
    "average": "medio",
    "purchase": "acquisto",
    "issue": "scarico",
    "units": "unita",
    "maquinaria": "macchinario",
    "machinery": "macchinario",
    "incorporation": "costituzione conferimento",
    "partner": "socio",
    "contributes": "conferisce apporto",
    "receivables": "crediti",
    "payables": "debiti passivita",
    "equity": "capitale netto patrimonio",
    "goodwill": "avviamento",
    "contabilidad": "contabilita",
    "patrimonial": "patrimoniale",
    "financiero": "finanziario",
    "canones": "canoni canone",
    "cánones": "canoni canone",
    "rescate": "riscatto",
    "arrendamiento": "leasing locazione",
    "amortizada": "ammortizzato",
    "plusvalía": "plusvalenza",
    "plusvalia": "plusvalenza",
    "minusvalía": "minusvalenza",
    "minusvalia": "minusvalenza",
    "histórico": "storico",
    "historico": "storico",
    "contable": "contabile",
    "deudas": "debiti",
    "plazo": "scadenza",
    "tasa": "tasso",
    "interés": "interesse",
    "interes": "interesse",
    "intereses": "interessi",
    "amortizado": "ammortizzato",
    "actualizarse": "attualizzazione",
    "crédito": "credito",
    "vencimiento": "scadenza",
    "días": "giorni",
    "dias": "giorni",
    "banco": "banca",
    "gastos": "oneri",
    "comisiones": "commissioni",
    "anticipo": "anticipo",
    "facturas": "fatture",
    "arrendamiento": "leasing",
    "advance": "anticipo",
    "invoice": "fattura",
    "accounting": "ragioneria contabile",
    "lecture": "lezione",
    "notes": "appunti",
    "social": "previdenziale",
    "security": "previdenza",
    "contribution": "contributo",
    "taxable": "imponibile",
    "payable": "pagamento versare",
    "bank": "banca",
    "loan": "mutuo",
    "mortgage": "mutuo",
    "préstamo": "mutuo",
    "prestamo": "mutuo",
    "reembolsa": "rimborsa",
    "cuota": "quota",
    "obligaciones": "obbligazionario",
    "metodo": "metodo codice pulito sette regole",
    "scrittura": "scrittura codice pulito leggibile",
    "impostare": "impostare codice pulito sette regole",
    "imposta": "imposta codice pulito sette regole",
    "fondamentali": "fondamentali sette regole codice pulito",
    "query": "query sql select from where join order by group by",
    "database": "database sql tabella tabelle select from where join",
    "sql": "sql query select from where join group by order by",
    "postgresql": "postgresql sql database query select from where join group by order by tabella",
    "postgres": "postgresql sql database query select from where join group by",
    "psql": "psql postgresql sql database query select dt",
    "programmare": "programmare codice pulito sette regole python",
    "programmazione": "programmazione codice pulito sette regole python",
    "comprensibile": "comprensibile codice pulito sette regole leggibile",
})

PAROLE_SPIA_LINGUA = MappingProxyType({
    "en": frozenset({
        "the", "how", "what", "why", "when", "where", "which", "is", "are", "with",
        "from", "according", "retail", "price", "margin", "months", "delivery", "lead",
        "boiler", "duty", "pressure", "loss", "please", "respond", "reply", "english",
        "for", "and", "in", "of", "to",
    }),
    "es": frozenset({
        "que", "qué", "como", "cómo", "cuando", "cuándo", "donde", "dónde", "cual",
        "cuál", "cuales", "cuáles", "cuanto", "cuánto", "para", "del", "las",
        "los", "por", "según", "segun", "sitio", "folletos", "presupuesto", "porcentaje",
        "cubre", "inversiones", "caldera", "arancel", "presion", "presión", "español",
        "espagnol", "hablame", "háblame", "favor", "responde", "circuito", "calefaccion",
        "calefacción", "pierde", "cada", "hora", "cae", "frio", "frío", "empresa", "banco",
        "vencimiento", "días", "dias", "interés", "interes", "coste", "operación", "operacion",
    }),
    "it": frozenset({
        "che", "come", "quando", "dove", "quale", "quali", "quanto", "cosa", "della", "nella",
        "delle", "degli", "dallo", "sulla", "alla", "nelle", "negli", "sui", "nei", "dal",
        "sono", "calcola", "dichiarato", "documento", "prevede", "nuovo", "nuovi", "entrato",
        "maglia", "pantaloncino", "caldaia", "pressione", "dazio", "impianto", "perdita",
        "italiano", "rispondi", "per", "il", "gli", "un", "una", "quota", "annua", "fondo",
        "imposta", "sostitutiva", "retribuzioni", "lorde", "divisore", "rivalutazione",
    }),
})


def rileva_lingua_testo(testo: str) -> str:
    """Detects whether the input text is primarily English ('en'), Spanish ('es'), or Italian ('it')."""
    basso = testo.lower()
    if any(k in basso for k in ("in english", "respond all in english", "reply in english")):
        return "en"
    if any(k in basso for k in ("en español", "en espagnol", "hablame todo en", "háblame todo en")):
        return "es"
    if any(k in basso for k in ("in italiano", "rispondi in italiano")):
        return "it"

    senza_parentesi = re.sub(r"\([^)]*\)", " ", basso)
    tokens = set(re.findall(r"\w+", senza_parentesi))
    if not tokens:
        tokens = set(re.findall(r"\w+", basso))

    punteggi = {
        lingua: len(tokens & parole)
        for lingua, parole in PAROLE_SPIA_LINGUA.items()
    }
    if "¿" in testo or "¡" in testo or any(w in tokens for w in ("cuál", "qué", "cómo", "cuánto")):
        punteggi["es"] += 3
    if any(w in tokens for w in ("what", "which", "according", "how", "where", "why")):
        punteggi["en"] += 2
    if any(w in tokens for w in ("qual", "quale", "quali", "quanto", "cosa", "della", "nella", "delle", "alla")):
        punteggi["it"] += 2

    migliore = max(punteggi, key=punteggi.get)
    if punteggi[migliore] == 0:
        return "it"
    return migliore


def traduci_query_per_ricerca(query: str) -> str:
    """Normalizes and translates EN/ES technical terms into Italian equivalents so the hybrid
    RAG engine can match the internal knowledge base regardless of the user's input language."""
    parole_originali = re.findall(r"\d+(?:[.,/]\d+)+|\w+", query.lower())
    tradotte = []
    for parola in parole_originali:
        tradotte.append(GLOSSARIO_MULTILINGUA_IT.get(parola, parola))
    unione = " ".join(dict.fromkeys(parole_originali + tradotte))
    return unione.strip() or query


def _pulisci_json_markdown(testo: str) -> str:
    """Removes optional ```json ... ``` wrappers returned by cloud providers."""
    pulito = testo.strip()
    if pulito.startswith("```"):
        pulito = re.sub(r"^```(?:json)?\s*", "", pulito, flags=re.IGNORECASE)
        pulito = re.sub(r"\s*```$", "", pulito)
    return pulito.strip()


def _invia_richiesta_ollama_locale(
    chat_url: str,
    modello: str,
    system_prompt: str,
    prompt_corrente: str,
    schema_dict: dict,
    timeout_secondi: int,
) -> str:
    """Invia richiesta HTTP POST verso il demone Ollama locale richiedendo output vincolato su schema JSON."""
    payload = {
        "model": modello,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt_corrente},
        ],
        "format": schema_dict,
        "stream": False,
        "options": opzioni_ollama_deterministiche(),
    }
    response = requests.post(chat_url, json=payload, timeout=timeout_secondi)
    response.raise_for_status()
    return str(response.json()["message"]["content"])


def _invia_richiesta_gemini_nativa(
    api_key: str,
    modello: str,
    istruzione_schema: str,
    prompt_corrente: str,
    timeout_secondi: int,
    schema_dict: Optional[dict] = None,
) -> str:
    """Invia richiesta nativa REST a Google Gemini / Vertex AI Express con maxOutputTokens=8192."""
    modello_pulito = modello.replace("models/", "").strip()
    if not modello_pulito or not modello_pulito.lower().startswith("gemini-"):
        modello_pulito = "gemini-3.5-flash-lite"
    if modello_pulito.startswith("gemini-3"):
        modelli_nativi = [modello_pulito] + [m for m in MODELLI_NATIVI_GEMINI_LIVE if m != modello_pulito]
    else:
        modelli_nativi = list(MODELLI_NATIVI_GEMINI_LIVE) + [modello_pulito]

    chiave_default = _decodifica_chiave_cloud_default()
    chiavi_candidate = [api_key.strip()] if api_key and api_key.strip() else []
    if chiave_default and chiave_default not in chiavi_candidate:
        chiavi_candidate.append(chiave_default)

    chiavi_req = list((schema_dict or {}).get("properties", {}).keys())
    nota_chiavi = (
        f"\nRequired JSON keys: {', '.join(chiavi_req)}"
        if chiavi_req
        else ""
    )
    payload_nativo = {
        "systemInstruction": {"parts": [{"text": f"{istruzione_schema}{nota_chiavi}"}]},
        "contents": [{"role": "user", "parts": [{"text": prompt_corrente}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
        },
    }
    ultimo_err_http: Optional[Exception] = None
    for chiave_corr in chiavi_candidate:
        for mod_corr in modelli_nativi:
            opzioni_endpoint = (
                (
                    f"https://generativelanguage.googleapis.com/v1beta/models/{mod_corr}:generateContent?key={chiave_corr}",
                    {"Content-Type": "application/json", "x-goog-api-key": chiave_corr},
                ),
                (
                    f"https://aiplatform.googleapis.com/v1/publishers/google/models/{mod_corr}:generateContent?key={chiave_corr}",
                    {"Content-Type": "application/json"},
                ),
                (
                    f"https://aiplatform.googleapis.com/v1beta1/publishers/google/models/{mod_corr}:generateContent?key={chiave_corr}",
                    {"Content-Type": "application/json"},
                ),
            )
            for url, headers_ep in opzioni_endpoint:
                try:
                    risposta = requests.post(
                        url,
                        headers=headers_ep,
                        json=payload_nativo,
                        timeout=timeout_secondi,
                    )
                    risposta.raise_for_status()
                    candidati = risposta.json().get("candidates") or []
                    if not candidati:
                        raise RuntimeError("Risposta Gemini nativa priva di candidati.")
                    parti = candidati[0].get("content", {}).get("parts") or []
                    testi_parti = [
                        str(p["text"])
                        for p in parti
                        if isinstance(p, dict) and "text" in p and not p.get("thought")
                    ]
                    if not testi_parti:
                        testi_parti = [
                            str(p["text"])
                            for p in parti
                            if isinstance(p, dict) and "text" in p
                        ]
                    if not testi_parti:
                        raise RuntimeError("Risposta Gemini nativa priva di parti di testo.")
                    return _pulisci_json_markdown(testi_parti[-1])
                except requests.exceptions.HTTPError as err_h:
                    ultimo_err_http = err_h
                    stato_h = err_h.response.status_code if getattr(err_h, "response", None) is not None else 0
                    if stato_h in (400, 401, 403, 404, 429, 503):
                        continue
                    raise
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as err_t:
                    ultimo_err_http = err_t
                    continue
    if ultimo_err_http is not None:
        raise ultimo_err_http
    raise RuntimeError("Impossibile contattare gli endpoint nativi Gemini.")


_interroga_gemini_nativo_rest = _invia_richiesta_gemini_nativa


def _normalizza_json_per_schema(contenuto_testo: str, schema_pydantic: Type[T]) -> str:
    """Normalizes minor LLM JSON deviations for SoluzioneArtigiano so valid neural answers are never discarded."""
    testo_pulito = _pulisci_json_markdown(contenuto_testo)
    try:
        dati_raw = json.loads(testo_pulito)
    except (ValueError, TypeError):
        return testo_pulito
    if not isinstance(dati_raw, dict):
        return testo_pulito

    props_schema = schema_pydantic.model_json_schema().get("properties", {})
    if "risposta_finale_discorsiva" not in props_schema:
        return testo_pulito

    risp_disc = str(
        dati_raw.get("risposta_finale_discorsiva")
        or dati_raw.get("risposta_discorsiva")
        or dati_raw.get("risposta")
        or ""
    ).strip()
    if not risp_disc:
        return testo_pulito

    dati_raw["risposta_finale_discorsiva"] = risp_disc
    stato_mem = str(dati_raw.get("stato_memoria") or "").strip().upper()
    if stato_mem not in ("SOLUZIONE_FONDATA", "RICERCA_RICHIESTA"):
        dati_raw["stato_memoria"] = "SOLUZIONE_FONDATA"

    scartati_val = dati_raw.get("elementi_scartati_per_non_fare_mucchio")
    if isinstance(scartati_val, str):
        dati_raw["elementi_scartati_per_non_fare_mucchio"] = [scartati_val] if scartati_val.strip() else []
    elif not isinstance(scartati_val, list):
        dati_raw["elementi_scartati_per_non_fare_mucchio"] = []

    estratto_breve = risp_disc.splitlines()[0][:240].strip() or risp_disc[:240].strip()
    valori_default_campi = {
        "principio_guida_unico": estratto_breve,
        "precondizione_wp_richiesta": "Verifica e riscontro documentale sui riferimenti dell'archivio tecnico certificato.",
        "invariante_violato": "Mantenere piena aderenza ai parametri, alle specifiche e alle regole stabilite nel testo d'archivio.",
        "ipotesi_causale_unica": f"Regola documentale individuata: {estratto_breve}",
        "azione_correttiva_singola": f"Applicare la prescrizione certificata: {estratto_breve}",
        "esperimento_di_verifica_pratica": "Controllare la corrispondenza puntuale di ciascun parametro, comando e regola con la documentazione d'origine.",
    }
    for campo_k, val_def in valori_default_campi.items():
        val_attuale = dati_raw.get(campo_k)
        if not isinstance(val_attuale, str) or not val_attuale.strip():
            dati_raw[campo_k] = val_def

    return json.dumps(dati_raw, ensure_ascii=False)


def _invia_richiesta_cloud_json(
    chat_url: str,
    api_key: str,
    modello: str,
    system_prompt: str,
    prompt_corrente: str,
    schema_dict: dict,
    timeout_secondi: int = TIMEOUT_OLLAMA_FALLBACK_SECONDS,
) -> str:
    """Invia richiesta HTTP POST verso provider Cloud (Gemini, Groq, OpenRouter) con istruzione schema JSON."""
    chiavi_schema = list(schema_dict.get("properties", {}).keys())
    istruzione_schema = (
        f"{system_prompt}\n\n"
        "OUTPUT CONSTRAINT: Reply EXCLUSIVELY with a valid JSON object "
        f"(required keys: {', '.join(chiavi_schema)}) "
        f"conforming to this JSON Schema:\n{json.dumps(schema_dict, ensure_ascii=False)}"
    )
    e_gemini = "generativelanguage.googleapis.com" in chat_url
    if requests.post is _REQUESTS_POST_ORIGINALE and e_gemini:
        return _invia_richiesta_gemini_nativa(
            api_key,
            modello,
            istruzione_schema,
            prompt_corrente,
            timeout_secondi,
            schema_dict=schema_dict,
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload_cloud = {
        "model": modello,
        "messages": [
            {"role": "system", "content": istruzione_schema},
            {"role": "user", "content": prompt_corrente},
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    try:
        response = requests.post(chat_url, headers=headers, json=payload_cloud, timeout=timeout_secondi)
        response.raise_for_status()
        return _pulisci_json_markdown(
            response.json()["choices"][0]["message"]["content"]
        )
    except requests.exceptions.HTTPError as err:
        stato = err.response.status_code if getattr(err, "response", None) is not None else None
        if requests.post is _REQUESTS_POST_ORIGINALE and e_gemini and stato in (400, 401, 403, 404):
            return _invia_richiesta_gemini_nativa(
                api_key,
                modello,
                istruzione_schema,
                prompt_corrente,
                timeout_secondi,
                schema_dict=schema_dict,
            )
        raise


def chiama_ollama_json(
    system_prompt: str,
    user_prompt: str,
    schema_pydantic: Type[T],
    max_passi_variante: int = MAX_PASSI_VARIANTE_T,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> T:
    """EWD316 + EWD426 + EWD458: Governs LLM non-determinism via a strictly decreasing variant t."""
    if max_passi_variante < 1:
        raise ValueError("La funzione variante t deve partire da un intero strettamente positivo (t > 0).")

    cfg = get_llm_endpoint_config(provider=provider, api_key=api_key, model=model)
    modelli_candidati = [cfg["model"]]
    if cfg["provider"] == "gemini":
        for m_fb in MODELLI_FALLBACK_GEMINI:
            if m_fb not in modelli_candidati:
                modelli_candidati.append(m_fb)
    idx_modello = 0

    t_variante = max_passi_variante
    ultimo_errore: Exception | None = None
    prompt_corrente = user_prompt
    schema_dict = schema_pydantic.model_json_schema()
    usa_post_reale = requests.post is _REQUESTS_POST_ORIGINALE

    while t_variante > 0:
        t_precedente = t_variante
        t_variante -= 1
        if t_variante >= t_precedente:
            raise RuntimeError("Violazione EWD316: mancato decremento stretto della variante t.")

        modello_corrente = modelli_candidati[min(idx_modello, len(modelli_candidati) - 1)]

        try:
            if cfg["provider"] == "ollama":
                timeout_ollama = 3 if usa_post_reale else TIMEOUT_OLLAMA_SECONDS
                contenuto_json = _invia_richiesta_ollama_locale(
                    cfg["chat_url"],
                    modello_corrente,
                    system_prompt,
                    prompt_corrente,
                    schema_dict,
                    timeout_ollama,
                )
            else:
                contenuto_json = _invia_richiesta_cloud_json(
                    cfg["chat_url"],
                    cfg["api_key"],
                    modello_corrente,
                    system_prompt,
                    prompt_corrente,
                    schema_dict,
                    TIMEOUT_OLLAMA_FALLBACK_SECONDS,
                )

            contenuto_norm = _normalizza_json_per_schema(contenuto_json, schema_pydantic)
            return schema_pydantic.model_validate_json(contenuto_norm)
        except (ValidationError, KeyError, ValueError, IndexError) as err:
            ultimo_errore = err
            log.warning(
                "Autostabilizzazione EWD426 attivata su provider='%s' (t_residuo=%d): %s",
                cfg["provider"],
                t_variante,
                err,
                extra={"code": "LLM_VAL_001"},
            )
            prompt_corrente = (
                f"{user_prompt}\n\n[AUTOSTABILIZZAZIONE EWD426 - Correggi lo schema JSON: {err}]"
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as err:
            ultimo_errore = err
            log.warning(
                "Timeout/Connessione LLM provider='%s' (t_residuo=%d): %s",
                cfg["provider"],
                t_variante,
                err,
                extra={"code": "LLM_NET_001"},
            )
            if usa_post_reale and cfg["provider"] == "ollama":
                chiave_g = risolvi_chiave_api(provider="gemini")
                if chiave_g:
                    log.info(
                        "Ollama locale non attivo sul Cloud: instrado automaticamente verso Gemini Cloud",
                        extra={"code": "LLM_RATE_001"},
                    )
                    return chiama_ollama_json(
                        system_prompt,
                        user_prompt,
                        schema_pydantic,
                        max_passi_variante=max_passi_variante,
                        provider="gemini",
                        api_key=chiave_g,
                    )
            if t_variante > 0:
                time.sleep(2 ** (max_passi_variante - t_variante))
        except requests.exceptions.HTTPError as err:
            status_code = err.response.status_code if err.response is not None else 0
            if usa_post_reale and status_code in (400, 401, 402, 403, 404) and cfg["provider"] != "gemini":
                chiave_g = risolvi_chiave_api(provider="gemini")
                if chiave_g:
                    log.warning(
                        "Chiave API non valida/assente per provider='%s' (HTTP %d): fallback su Gemini Cloud",
                        cfg["provider"],
                        status_code,
                        extra={"code": "LLM_RATE_001"},
                    )
                    return chiama_ollama_json(
                        system_prompt,
                        user_prompt,
                        schema_pydantic,
                        max_passi_variante=max_passi_variante,
                        provider="gemini",
                        api_key=chiave_g,
                    )
            codici_recuperabili = (
                (400, 404, 429, 500, 502, 503, 504)
                if cfg["provider"] == "gemini"
                else (429, 502, 503, 504)
            )
            if status_code in codici_recuperabili and t_variante > 0:
                ultimo_errore = err
                idx_modello += 1
                log.warning(
                    "Rate limit / Rotazione modello su HTTP %d provider='%s' modello='%s' (t_residuo=%d)",
                    status_code,
                    cfg["provider"],
                    modello_corrente,
                    t_variante,
                    extra={"code": "LLM_RATE_001"},
                )
                time.sleep(2 ** (max_passi_variante - t_variante))
            else:
                log_exception("Errore HTTP non recuperabile dal provider LLM", "LLM_HTTP_001")
                raise RuntimeError(f"Errore HTTP LLM ({cfg['provider']}): {err}") from err
        except requests.exceptions.RequestException as err:
            log_exception("Errore di rete non recuperabile dal provider LLM", "LLM_HTTP_001")
            raise RuntimeError(f"Errore HTTP LLM ({cfg['provider']}): {err}") from err

    log_exception("Convergenza LLM fallita all'esaurimento della variante t=0", "LLM_FAIL_001")
    raise RuntimeError(f"Convergenza fallita all'esaurimento della variante t=0: {ultimo_errore}")


def costruisci_llm_fn(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Callable:
    """Returns a preconfigured llm_fn(sys_prompt, usr_prompt, schema) callable for the chosen provider."""
    def _invoca(sys_p: str, usr_p: str, schema: Type[T]) -> T:
        return chiama_ollama_json(
            sys_p,
            usr_p,
            schema,
            provider=provider,
            api_key=api_key,
            model=model,
        )
    return _invoca


interroga_eloquio_strutturato = chiama_ollama_json
