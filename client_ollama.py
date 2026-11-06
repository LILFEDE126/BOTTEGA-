#!/usr/bin/env python3
"""Layer 2 (THE): Multi-provider LLM client (Ollama + Gemini/Groq/OpenRouter Free API),
deterministic query translation, EWD426 self-stabilization, HTTP 429/404/503 model fallback and EWD316 variant t."""

import json
import re
import time
from typing import Callable, Optional, Type, TypeVar
import requests
from pydantic import BaseModel, ValidationError

from config import (
    MAX_PASSI_VARIANTE_T,
    MODELLI_FALLBACK_GEMINI,
    get_llm_endpoint_config,
    opzioni_ollama_deterministiche,
)
from logging_bottega import log, log_exception

T = TypeVar("T", bound=BaseModel)

GLOSSARIO_MULTILINGUA_IT = {
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
}

PAROLE_SPIA_LINGUA = {
    "en": {
        "the", "how", "what", "why", "when", "where", "which", "is", "are", "with",
        "from", "according", "retail", "price", "margin", "months", "delivery", "lead",
        "boiler", "duty", "pressure", "loss", "please", "respond", "reply", "english",
        "for", "and", "in", "of", "to",
    },
    "es": {
        "que", "qué", "como", "cómo", "cuando", "cuándo", "donde", "dónde", "cual",
        "cuál", "cuales", "cuáles", "cuanto", "cuánto", "para", "con", "del", "las",
        "los", "por", "según", "segun", "sitio", "folletos", "presupuesto", "porcentaje",
        "cubre", "inversiones", "caldera", "arancel", "presion", "presión", "español",
        "espagnol", "hablame", "háblame", "favor", "responde",
    },
    "it": {
        "che", "come", "quando", "dove", "quale", "quali", "quanto", "della", "nella",
        "delle", "degli", "dallo", "sulla", "sono", "calcola", "dichiarato", "documento",
        "maglia", "pantaloncino", "caldaia", "pressione", "dazio", "impianto", "perdita",
        "italiano", "rispondi",
    },
}


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
    if any(w in tokens for w in ("qual", "quale", "quali", "quanto", "della", "nella")):
        punteggi["it"] += 2

    migliore = max(punteggi, key=punteggi.get)
    if punteggi[migliore] == 0:
        return "it"
    return migliore


def traduci_query_per_ricerca(query: str) -> str:
    """Normalizes and translates EN/ES technical terms into Italian equivalents so the hybrid
    RAG engine can match the internal knowledge base regardless of the user's input language."""
    parole_originali = re.findall(r"\w+|\d+[.,]\d+", query.lower())
    tradotte = []
    for p in parole_originali:
        tradotte.append(GLOSSARIO_MULTILINGUA_IT.get(p, p))
    unione = " ".join(dict.fromkeys(parole_originali + tradotte))
    return unione.strip() or query


def _pulisci_json_markdown(testo: str) -> str:
    """Removes optional ```json ... ``` wrappers returned by cloud providers."""
    pulito = testo.strip()
    if pulito.startswith("```"):
        pulito = re.sub(r"^```(?:json)?\s*", "", pulito, flags=re.IGNORECASE)
        pulito = re.sub(r"\s*```$", "", pulito)
    return pulito.strip()


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

    while t_variante > 0:
        t_precedente = t_variante
        t_variante -= 1
        if t_variante >= t_precedente:
            raise RuntimeError("Violazione EWD316: mancato decremento stretto della variante t.")

        modello_corrente = modelli_candidati[min(idx_modello, len(modelli_candidati) - 1)]

        try:
            if cfg["provider"] == "ollama":
                payload = {
                    "model": modello_corrente,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt_corrente},
                    ],
                    "format": schema_dict,
                    "stream": False,
                    "options": opzioni_ollama_deterministiche(),
                }
                response = requests.post(cfg["chat_url"], json=payload, timeout=180)
                response.raise_for_status()
                contenuto_json = response.json()["message"]["content"]
            else:
                istruzione_schema = (
                    f"{system_prompt}\n\n"
                    "OUTPUT CONSTRAINT: Reply EXCLUSIVELY with a valid JSON object "
                    f"conforming to this JSON Schema:\n{json.dumps(schema_dict, ensure_ascii=False)}"
                )
                headers = {
                    "Authorization": f"Bearer {cfg['api_key']}",
                    "Content-Type": "application/json",
                }
                payload_cloud = {
                    "model": modello_corrente,
                    "messages": [
                        {"role": "system", "content": istruzione_schema},
                        {"role": "user", "content": prompt_corrente},
                    ],
                    "temperature": 0.0,
                    "response_format": {"type": "json_object"},
                }
                response = requests.post(cfg["chat_url"], headers=headers, json=payload_cloud, timeout=120)
                response.raise_for_status()
                contenuto_json = _pulisci_json_markdown(
                    response.json()["choices"][0]["message"]["content"]
                )

            return schema_pydantic.model_validate_json(contenuto_json)
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
            if t_variante > 0:
                time.sleep(2 ** (max_passi_variante - t_variante))
        except requests.exceptions.HTTPError as err:
            status_code = err.response.status_code if err.response is not None else 0
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
