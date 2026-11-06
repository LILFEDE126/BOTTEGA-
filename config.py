#!/usr/bin/env python3
"""Layer 0 (THE): Validated environment configuration, Free Cloud providers and 5 acyclic rings (0..4)."""

import base64
import os
import sys
from types import MappingProxyType
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

_PARTI_CHIAVE_CLOUD_DEFAULT = (
    "QVEuQWI4Uk42SXM2SHA=",
    "LXRwQUVybDFfejJpYjd2Z05lN2lhRmY5MFdDX3Q3cDlPNVZ5Q0hB",
)

MODELLI_FALLBACK_GEMINI = (
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
    "gemini-flash-latest",
    "gemini-2.5-flash",
)


def _decodifica_chiave_cloud_default() -> str:
    """Reconstructs the fallback Google AI Studio key so the cloud app works out-of-the-box."""
    return "".join(
        base64.b64decode(parte.encode("ascii")).decode("utf-8")
        for parte in _PARTI_CHIAVE_CLOUD_DEFAULT
    )


def _leggi_secret_streamlit(nome_chiave: str) -> str:
    """Safely reads a key from st.secrets when running inside Streamlit Cloud without importing streamlit at Layer 0."""
    mod_st = sys.modules.get("streamlit")
    if mod_st is None:
        return ""
    try:
        secrets_obj = getattr(mod_st, "secrets", None)
        if secrets_obj is not None and nome_chiave in secrets_obj:
            valore = secrets_obj[nome_chiave]
            return str(valore).strip() if valore is not None else ""
    except (KeyError, AttributeError, TypeError, ValueError, RuntimeError):
        return ""
    return ""


BOTTEGA_ENV = (os.getenv("BOTTEGA_ENV") or "dev").strip().lower()
LLM_PROVIDER = (
    os.getenv("LLM_PROVIDER")
    or _leggi_secret_streamlit("LLM_PROVIDER")
    or "gemini"
).strip().lower()
LLM_API_KEY = (
    os.getenv("LLM_API_KEY")
    or os.getenv("GEMINI_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
    or _leggi_secret_streamlit("LLM_API_KEY")
    or _leggi_secret_streamlit("GEMINI_API_KEY")
    or _decodifica_chiave_cloud_default()
).strip()


def risolvi_chiave_api(api_key: Optional[str] = None) -> str:
    """Resolves the active Cloud LLM API key from explicit arg, Streamlit Secrets, .env or built-in fallback."""
    if api_key is not None and api_key.strip():
        return api_key.strip()
    for nome_var in ("LLM_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        da_secret = _leggi_secret_streamlit(nome_var)
        if da_secret:
            return da_secret
        da_env = os.getenv(nome_var)
        if da_env is not None:
            return da_env.strip()
    return LLM_API_KEY.strip()


def get_db_config() -> dict:
    """Returns database connection parameters. Forbids default or missing passwords when BOTTEGA_ENV='prod'."""
    password = os.getenv("DB_PASSWORD")
    if BOTTEGA_ENV == "prod" and (not password or password == "bottega2026"):
        raise RuntimeError(
            "Sicurezza (BOTTEGA_ENV=prod): impostare una DB_PASSWORD robusta nel file .env."
        )
    return {
        "host": os.getenv("DB_HOST") or "127.0.0.1",
        "port": int(os.getenv("DB_PORT") or "5432"),
        "dbname": os.getenv("DB_NAME") or "bottega",
        "user": os.getenv("DB_USER") or "postgres",
        "password": password or "bottega2026",
    }


OLLAMA_BASE_URL = (os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_EMBED_URL = f"{OLLAMA_BASE_URL}/api/embed"

OLLAMA_LLM_MODEL = os.getenv("OLLAMA_LLM_MODEL") or "qwen2.5-coder:7b"
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL") or "nomic-embed-text"
EMBED_DIM = int(os.getenv("EMBED_DIM") or "768")

PROVIDER_CLOUD_CONFIG = MappingProxyType({
    "gemini": MappingProxyType({
        "chat_url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "default_model": "gemini-3.5-flash-lite",
    }),
    "groq": MappingProxyType({
        "chat_url": "https://api.groq.com/openai/v1/chat/completions",
        "default_model": "llama-3.3-70b-versatile",
    }),
    "openrouter": MappingProxyType({
        "chat_url": "https://openrouter.ai/api/v1/chat/completions",
        "default_model": "openrouter/free",
    }),
    "deepseek": MappingProxyType({
        "chat_url": "https://api.deepseek.com/chat/completions",
        "default_model": "deepseek-chat",
    }),
    "openai": MappingProxyType({
        "chat_url": "https://api.openai.com/v1/chat/completions",
        "default_model": "gpt-4o-mini",
    }),
})


def get_llm_endpoint_config(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """Returns endpoint URL, model name and API key for local Ollama or Cloud API providers."""
    prov = (provider or LLM_PROVIDER or "gemini").strip().lower()
    if prov == "ollama":
        return {
            "provider": "ollama",
            "chat_url": OLLAMA_CHAT_URL,
            "model": model or OLLAMA_LLM_MODEL,
            "api_key": "",
        }
    if prov not in PROVIDER_CLOUD_CONFIG:
        raise ValueError(f"Provider LLM non supportato: '{prov}'.")

    info = PROVIDER_CLOUD_CONFIG[prov]
    chiave = (api_key.strip() if (api_key is not None and api_key.strip()) else risolvi_chiave_api(api_key))
    if not chiave:
        raise RuntimeError(
            f"Chiave API mancante per il provider '{prov}'. Imposta LLM_API_KEY o inseriscila nella UI."
        )
    return {
        "provider": prov,
        "chat_url": info["chat_url"],
        "model": model or info["default_model"],
        "api_key": chiave,
    }


TAU_DOMINIO = float(os.getenv("TAU_DOMINIO") or "0.30")
TAU_BASSO = float(os.getenv("TAU_BASSO") or "0.45")
TAU_ALTO = float(os.getenv("TAU_ALTO") or "0.60")
RRF_K = int(os.getenv("RRF_K") or "60")

if not (0.0 <= TAU_DOMINIO <= TAU_BASSO <= TAU_ALTO <= 1.0):
    raise ValueError(
        f"Invariante soglie violato: richiesto 0 <= TAU_DOMINIO ({TAU_DOMINIO}) "
        f"<= TAU_BASSO ({TAU_BASSO}) <= TAU_ALTO ({TAU_ALTO}) <= 1."
    )
if RRF_K < 1:
    raise ValueError(f"RRF_K deve essere >= 1, ricevuto: {RRF_K}")

PESO_VETTORIALE = 1.0
PESO_FTS_LINGUA = 1.0
PESO_FTS_SIMPLE = 1.3

CAPITALE_SLOT_CONCORRENTI = int(os.getenv("CAPITALE_SLOT_CONCORRENTI") or "8")
MAX_PASSI_VARIANTE_T = int(os.getenv("MAX_PASSI_VARIANTE_T") or "3")
MAX_DOCUMENTI_PER_RICHIESTA = int(os.getenv("MAX_DOCUMENTI_PER_RICHIESTA") or "30")
MAX_MB_PER_RICHIESTA = int(os.getenv("MAX_MB_PER_RICHIESTA") or "200")
MAX_BYTES_PER_RICHIESTA = MAX_MB_PER_RICHIESTA * 1024 * 1024

GERARCHIA_LIVELLI_THE = MappingProxyType({
    "config": 0,
    "logging_bottega": 0,
    "anatomia_ast": 0,
    "geometria_semaforo": 1,
    "grounding_numerico": 1,
    "ispezione_moduli": 1,
    "presidio_concorrenza": 1,
    "store_pgvector": 2,
    "client_ollama": 2,
    "seed_bottega": 3,
    "cascata_strutturata": 3,
    "risolutore_artigiano": 3,
    "app": 4,
})


def opzioni_ollama_deterministiche(num_predict: int = 1024) -> dict:
    """Returns a fresh dictionary with deterministic sampling parameters (temperature=0.0, seed=42)."""
    return {
        "temperature": 0.0,
        "seed": 42,
        "num_predict": num_predict,
    }
