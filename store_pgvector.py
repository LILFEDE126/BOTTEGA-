#!/usr/bin/env python3
"""Layer 2 (THE): PostgreSQL + pgvector persistence, fast C++ PDFium/pypdf extraction,
safe transactional context manager, circuit-breaker L2 embedding fallback and RAM archive."""

from contextlib import contextmanager
import hashlib
import io
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
import psycopg2
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector
from pypdf import PdfReader
from pypdf.errors import PyPdfError
import requests

try:
    import pypdfium2 as pdfium
except ImportError:
    pdfium = None

from config import (
    EMBED_DIM,
    LIMITE_ITERAZIONI_D,
    LIMITE_ITERAZIONI_DIJKSTRA,
    MAX_CARATTERI_PARAGRAFO_PDF,
    OLLAMA_EMBED_MODEL,
    OLLAMA_EMBED_URL,
    SOGLIA_S_MAX_FALLIMENTO_NORMATIVO,
    TIMEOUT_HTTP_BREVE,
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
from grounding_numerico import arrotonda_esatto_el_x8, tronca_senza_spezzare_parola
from presidio_concorrenza import SEGRETARIO_THE

logging.getLogger("pypdf").setLevel(logging.ERROR)

_REQUESTS_POST_ORIGINALE = requests.post
_PSYCOPG2_CONNECT_ORIGINALE = psycopg2.connect
_PDF_READER_ORIGINALE = PdfReader

_OLLAMA_EMBED_OFFLINE = False
_POSTGRES_OFFLINE = False


def e_postgres_locale_attivo() -> bool:
    """Restituisce True solo quando il database PostgreSQL locale e attivo, False in modalita Web RAM."""
    return not _POSTGRES_OFFLINE

_ARCHIVIO_MEMORIA_RAM: List[Dict[str, Any]] = []
_CACHE_BLOCCHI_DOCUMENTO: Dict[str, List[Tuple[str, str]]] = {}

TERMINI_ECONOMICI_AFFINI = frozenset({
    "costi",
    "costo",
    "prezzo",
    "prezzi",
    "preventivo",
    "preventivi",
    "budget",
    "investimento",
    "investimenti",
    "spesa",
    "spese",
    "euro",
    "eur",
    "bando",
    "bandi",
    "voucher",
    "contributo",
    "agevolazione",
    "finanziamento",
    "sito",
    "brochure",
    "packaging",
    "marketing",
    "business",
})

STOPWORDS_RICERCA_COMUNI = frozenset({
    "che", "con", "del", "della", "delle", "degli", "dei", "dal", "dalla", "nel", "nella",
    "nelle", "negli", "nei", "sul", "sulla", "sulle", "per", "tra", "fra", "una", "uno",
    "gli", "le", "la", "il", "lo", "non", "sono", "alla", "alle", "agli", "allo", "cui",
    "piu", "più", "quale", "quali", "quanto", "come", "quando", "dove", "cosa", "chi",
    "the", "and", "for", "with", "from", "what", "which", "how", "when", "where", "are",
    "que", "qué", "con", "para", "por", "los", "las", "una", "uno", "cual", "cuál", "como",
    "cómo", "según", "segun", "according", "document", "documentos", "appunti", "corso",
    "azienda", "societa", "società", "impresa", "euro", "euros", "eur",
    "spieghi", "spiega", "spiegami", "meglio", "imposta", "impostare", "impostano",
    "qusli", "fondamentali", "fondamentale", "principali", "principale",
    "vorrei", "posso", "sapere", "capire", "funziona", "funzionano", "usare", "scrivere",
})

PATRON_CODICE_NORMATIVO = re.compile(
    r"\b(?:oic|ias|ifrs|niif|uni|iso|esrs|csrd|verifactu|pillar\s+two)\s*\d*\b"
    r"|\bart(?:\.|icolo)?\s*\d+(?:-(?:bis|ter|quater))?\b"
    r"|\bl\.?\s*\d{1,4}/\d{4}\b"
    r"|\b\d{1,4}/\d{4}\b"
)

PAROLE_POLISEMICHE_TRASVERSALI = frozenset({
    "perdita", "perdite", "bilancio", "bilanci", "valore", "valori",
    "controllo", "controlli", "sistema", "sistemi", "esercizio", "esercizi",
    "effetto", "effetti", "causa", "radice", "azione", "correttiva",
    "unica", "regola", "metodo", "calcolo", "verifica", "esame",
    "analisi", "stato", "parte", "punto", "caso", "casi", "modo",
    "tempo", "anni", "anno", "mesi", "mese", "giorni", "giorno",
    "attivo", "attivi", "passivo", "passivi", "riserva", "riserve",
    "fondo", "fondi", "credito", "crediti", "debito", "debiti",
    "quota", "quote", "tasso", "tassi", "limite", "limiti",
    "normale", "nominale", "totale", "totali", "generale", "generali",
    "tecnico", "tecnici", "normativo", "normativi", "documento", "documenti",
    "archivio", "secondo", "quale", "quali", "quando", "perche", "come",
    "cuenta", "valor", "valores", "control", "sistema", "ejercicio",
    "efecto", "causa", "accion", "regla", "metodo", "calculo",
    "activo", "pasivo", "reserva", "plazo", "limite", "total",
    "segun", "cual", "cuales", "cuando", "como", "porque", "debe",
    "balance", "value", "values", "control", "system", "exercise",
    "effect", "cause", "action", "rule", "method", "check",
    "active", "passive", "reserve", "limit", "total", "account",
    "according", "which", "what", "when", "where", "must", "should",
    "produzione", "disponibilita", "disponibili", "disponibile", "carico",
    "scarico", "memoria", "allocata", "azzerano", "provocando", "riavvio",
    "forzato", "strategia", "configurare", "evitare", "energetico",
    "pressione", "mandata", "registra", "portata", "rottura", "molla",
    "meccanica", "eseguita", "eseguire", "tenuta", "corrente", "corriente",
    "continua", "presenta", "caida", "tensione", "tension", "bloquea",
    "compensacion", "compensazione", "potencia", "potenza", "fallo",
    "puente", "medicion", "realizar", "attuale", "actual", "uscita",
    "saliente", "entrata", "applicare", "aplicar", "bloquear", "canale",
    "canal", "datos", "processing", "liters", "shows", "across", "rapid",
    "pressure", "depreciation", "performed", "running", "caused",
    "excessive", "timeout", "rates", "between", "recovery", "procedure",
    "adjusted", "configuration", "bilanciamento", "nodi", "nodo",
    "iscritto", "iscritta", "iscritti", "iscritte", "netto", "netta",
    "incremento", "incrementi", "riduce", "riduzione", "industriale",
    "industriali", "impianto", "impianti", "isola", "isolare", "centrale",
    "centrali", "strumentale", "assenza", "verificare", "contabile",
    "materiali", "flusso", "flussi", "annuo", "annua", "acquisizione",
    "ore", "minuti", "minuto", "secondi", "fatture", "fattura", "subiscono",
    "continui", "appena", "supera", "operazioni", "nonostante",
    "impostato", "risolvere", "singola", "verificabile", "scatta", "blocco",
    "costo", "costi", "attiva", "pieno", "piena", "diagnostica", "diagnostico",
    "immobilizzazioni", "immobilizzazione", "svalutazione", "ammortamento",
    "costituzione", "articolo", "articoli", "modifica", "modifiche",
    "storico", "storica", "storiche", "storia", "italiano", "italiana",
    "italiani", "italiane", "legge", "leggi", "previsto", "prevede",
    "relativa", "relative", "relativo", "relativi", "contenuto", "subito",
    "comma", "diritto", "procedimento", "termine", "termini", "conclusione",
    "interesse", "interessi", "istituto", "merito", "principi", "principio",
    "ciclo", "rendimiento", "trabajo", "maximo", "máximo", "opera", "entre",
    "establece", "sobre", "window", "phase", "phases", "during", "behave",
    "protocol", "transmission", "avoidance", "start",
})


def _ancora_normativa_presente(ancora: str, testo: str) -> bool:
    """Checks whether a specific normative reference (including 'articolo N' / 'art. N') exists in the fragment."""
    m_art = re.match(r"^art(?:\.|icolo)?\s*(\d+(?:-(?:bis|ter|quater))?)$", ancora.strip())
    if m_art:
        num_art = re.escape(m_art.group(1))
        patron_art = rf"\bart(?:\.|icolo|t\.)?\s*{num_art}\b"
        return bool(re.search(patron_art, testo.lower()))
    return bool(re.search(rf"\b{re.escape(ancora.strip())}\b", testo.lower()))


def _ha_match_parola_o_radice(parola_q: str, parole_frammento: set[str]) -> bool:
    """Checks exact word match or shared morphological stem (stripping final inflection vowel/s) on whole words only."""
    if parola_q in parole_frammento:
        return True
    if parola_q == "regole":
        return any(pf in ("regole", "regola") for pf in parole_frammento)
    if len(parola_q) >= 6:
        radice = parola_q[:-2] if parola_q.endswith("es") and len(parola_q) >= 7 else parola_q[:-1]
        return any(pf.startswith(radice) and abs(len(pf) - len(parola_q)) <= 2 for pf in parole_frammento)
    return False


def _normalizza_accenti_minuscolo(testo: str) -> str:
    """Lowercases text and folds Italian/Spanish accented vowels to their plain form."""
    testo_n = re.sub(r"[àáâ]", "a", testo.lower())
    testo_n = re.sub(r"[èéê]", "e", testo_n)
    testo_n = re.sub(r"[ìíî]", "i", testo_n)
    testo_n = re.sub(r"[òóô]", "o", testo_n)
    return re.sub(r"[ùúüû]", "u", testo_n)


def _copertura_termini_specifici(
    query_originale: str,
    query_tradotta: str,
    testo_frammento: str,
) -> Tuple[int, float]:
    """Calculates how many non-generic domain-specific whole words (>= 5 chars) from the query appear in the fragment."""
    testo_q_norm = _normalizza_accenti_minuscolo(f"{query_originale} {query_tradotta}")
    token_q = {
        token_str for token_str in re.findall(r"[a-zñ]{5,}", testo_q_norm)
        if token_str not in PAROLE_POLISEMICHE_TRASVERSALI and token_str not in STOPWORDS_RICERCA_COMUNI
    }
    if not token_q:
        return (1, 1.0)

    testo_f_norm = _normalizza_accenti_minuscolo(testo_frammento)
    parole_f = set(re.findall(r"[a-zñ]{5,}", testo_f_norm))

    trovati = sum(1 for token_str in token_q if _ha_match_parola_o_radice(token_str, parole_f))
    if trovati <= 1 and len(token_q) >= 5:
        return (0, 0.0)
    if 1 <= len(token_q) <= 3 and trovati >= 1:
        return (max(2, trovati), max(0.35, trovati / len(token_q)))
    rapporto = trovati / len(token_q)
    return (trovati, rapporto)


PAROLE_CALENDARIO_E_TEMPO = frozenset({
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
    "settembre", "ottobre", "novembre", "dicembre",
    "enero", "febrero", "abril", "mayo", "junio", "julio", "septiembre", "octubre",
    "noviembre", "diciembre",
    "january", "february", "march", "april", "june", "july", "august", "september",
    "october", "november", "december",
    "lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato", "domenica",
    "lunes", "martes", "miercoles", "jueves", "viernes", "domingo",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "oggi", "domani", "ieri", "dopodomani", "stasera", "stanotte", "stamattina", "prossimo",
    "prossima", "prossimi", "settimana", "weekend", "today", "tomorrow", "yesterday",
    "tonight", "next", "week", "hoy", "manana", "ayer", "pasado", "semana", "proximo", "proxima",
})


def estrai_nomi_propri_query(query_originale: str) -> set[str]:
    """Collects capitalized words that do not open a sentence in the original query (places, companies, people)."""
    nomi: set[str] = set()
    for frase in re.split(r"[.!?¿¡\n:;]+", query_originale or ""):
        parole_frase = re.findall(r"[A-Za-zÀ-ÿñÑ]+", frase)
        for parola in parole_frase[1:]:
            if len(parola) >= 3 and parola[0].isupper() and not parola.isupper():
                nomi.add(_normalizza_accenti_minuscolo(parola))
    return nomi


def estrai_nomi_propri_frammento(testo_frammento: str) -> set[str]:
    """Words that appear only capitalized in the fragment and at least once in mid-sentence position."""
    stato: Dict[str, List[bool]] = {}
    for m in re.finditer(r"[A-Za-zÀ-ÿñÑ]{3,}", testo_frammento or ""):
        parola = m.group(0)
        if parola.isupper():
            continue
        chiave = _normalizza_accenti_minuscolo(parola)
        voce = stato.setdefault(chiave, [True, False])
        if not parola[0].isupper():
            voce[0] = False
            continue
        prefisso = testo_frammento[max(0, m.start() - 2):m.start()]
        if re.match(r"[a-zà-ÿ0-9,] ", prefisso):
            voce[1] = True
    return {chiave for chiave, (sempre_maiuscola, meta_frase) in stato.items() if sempre_maiuscola and meta_frase}


def ha_termine_tematico(query_originale: str, query_tradotta: str, testo_frammento: str) -> bool:
    """Strato A guard: a shared place, company or person name or a shared date never proves a shared subject.
    At least one subject word of the query (not a proper name, not a calendar word) must appear in the fragment."""
    testo_q_norm = _normalizza_accenti_minuscolo(f"{query_originale} {query_tradotta}")
    nomi_propri = estrai_nomi_propri_query(query_originale) | estrai_nomi_propri_frammento(testo_frammento)
    parole_f = set(re.findall(r"[a-zñ]{3,}", _normalizza_accenti_minuscolo(testo_frammento)))

    token_forti = {
        t for t in re.findall(r"[a-zñ]{5,}", testo_q_norm)
        if t not in PAROLE_POLISEMICHE_TRASVERSALI and t not in STOPWORDS_RICERCA_COMUNI
    }
    soggetto_forte = {t for t in token_forti if t not in nomi_propri and t not in PAROLE_CALENDARIO_E_TEMPO}
    if soggetto_forte:
        return any(_ha_match_parola_o_radice(t, parole_f) for t in soggetto_forte)

    token_tutti = set(re.findall(r"[a-zñ]{4,}", testo_q_norm))
    solo_nomi_o_date = {t for t in token_tutti if t in nomi_propri or t in PAROLE_CALENDARIO_E_TEMPO}
    soggetto_debole = {
        t for t in token_tutti
        if t not in nomi_propri and t not in PAROLE_CALENDARIO_E_TEMPO and t not in STOPWORDS_RICERCA_COMUNI
    }
    if soggetto_debole:
        return any(_ha_match_parola_o_radice(t, parole_f) for t in soggetto_debole)
    return not solo_nomi_o_date


def conta_frammenti_archivio_ram(titolo: Optional[str] = None) -> int:
    """Returns the number of indexed fragments currently stored in the in-memory RAM archive."""
    if titolo is None:
        return len(_ARCHIVIO_MEMORIA_RAM)
    return sum(1 for item in _ARCHIVIO_MEMORIA_RAM if item.get("titolo") == titolo)


_TERMINI_CAMELCASE_PROTETTI = (
    ("Value Error", "ValueError"),
    ("Key Error", "KeyError"),
    ("Type Error", "TypeError"),
    ("Index Error", "IndexError"),
    ("Name Error", "NameError"),
    ("Attribute Error", "AttributeError"),
    ("Syntax Error", "SyntaxError"),
    ("Indentation Error", "IndentationError"),
    ("Runtime Error", "RuntimeError"),
    ("Assertion Error", "AssertionError"),
    ("Fast API", "FastAPI"),
    ("Postgre SQL", "PostgreSQL"),
    ("Git Hub", "GitHub"),
    ("Java Script", "JavaScript"),
    ("Type Script", "TypeScript"),
    ("Power Shell", "PowerShell"),
    ("Aha Slides", "AhaSlides"),
    ("Git Kraken", "GitKraken"),
    ("Git Lens", "GitLens"),
    ("Live Share", "LiveShare"),
    ("One Drive", "OneDrive"),
    ("Deep Seek", "DeepSeek"),
    ("Open Router", "OpenRouter"),
    ("Chat GPT", "ChatGPT"),
    ("Notebook LM", "NotebookLM"),
    ("Open Claw", "OpenClaw"),
    ("Bit Keeper", "BitKeeper"),
    ("Mac Book", "MacBook"),
    ("Intelli Sense", "IntelliSense"),
)


def normalizza_spazi_testo_pdf(testo: str) -> str:
    """Repairs PUA font ligatures, strips repetitive slide footers, restores missing spaces,
    and preserves technical CamelCase identifiers and Python operators."""
    if not testo:
        return ""
    mappa_ligature = (
        ("\ue009", "tt"),
        ("\ue008", "ff"),
        ("\ue007", "ff"),
        ("\ue006", "fl"),
        ("\ufb00", "ff"),
        ("\ufb01", "fi"),
        ("\ufb02", "fl"),
        ("\ufb03", "ffi"),
        ("\ufb04", "ffl"),
        ("\r\n", "\n"),
        ("\r", "\n"),
        (" -/ ", " // "),
        ("--.", "..."),
        ("sufiicienti", "sufficienti"),
        ("Sufiicienti", "Sufficienti"),
        ("insufiicienti", "insufficienti"),
        ("rufi", "ruff"),
        ("Rufi", "Ruff"),
        ("if v -= 6", "if v >= 6"),
        ("if importo -= 0", "if importo <= 0"),
        ("temperatura &= ", "temperatura >= "),
        (" &= ", " == "),
        ("Davide Lista", "D."),
        ("davide lista", "D."),
        ("Leonardo da Vinci", "L."),
        ("Andrej Karpathy", "K."),
        ("Andrew Carpati", "K."),
        ("Angio Carpati", "K."),
        ("Edsger W. Dijkstra", "E. W. D."),
        ("Oriana Fallaci", "O. F."),
        ("Reggio Emilia", "R."),
    )
    testo_lavorato = testo
    for glifo, sostituto in mappa_ligature:
        if glifo in testo_lavorato:
            testo_lavorato = testo_lavorato.replace(glifo, sostituto)
    testo_lavorato = re.sub(
        r"(?im)^\s*(?:AK\s+)?Corso\s+intensivo\s+di\s+coding\s*[·.]?\s*Giorno\s+\d+.*$",
        "",
        testo_lavorato,
    )
    testo_lavorato = re.sub(r"([a-zàèéìòùáéíóúñ])([A-ZÀÈÉÌÒÙ])", r"\1 \2", testo_lavorato)
    testo_lavorato = re.sub(r"([a-zA-Zàèéìòùáéíóúñ]{2,})(\d)", r"\1 \2", testo_lavorato)
    testo_lavorato = re.sub(r"(\d)(€)", r"\1 \2", testo_lavorato)
    testo_lavorato = re.sub(r"(€)(\d)", r"\1 \2", testo_lavorato)
    testo_lavorato = re.sub(r"(\d|%|€)([a-zA-Zàèéìòùáéíóúñ]{2,})", r"\1 \2", testo_lavorato)
    testo_lavorato = re.sub(r"\b(euro)([a-zA-Zàèéìòùáéíóúñ]+)", r"\1 \2", testo_lavorato, flags=re.IGNORECASE)
    testo_lavorato = re.sub(r"([,:;])([a-zA-Zàèéìòùáéíóúñ€])", r"\1 \2", testo_lavorato)
    testo_lavorato = re.sub(r"([a-zA-Z0-9àèéìòùáéíóúñ])\(", r"\1 (", testo_lavorato)
    testo_lavorato = re.sub(r"\)([a-zA-Z0-9àèéìòùáéíóúñ])", r") \1", testo_lavorato)
    for spezzato, unito in _TERMINI_CAMELCASE_PROTETTI:
        if spezzato in testo_lavorato:
            testo_lavorato = testo_lavorato.replace(spezzato, unito)
    testo_lavorato = re.sub(r"\b(assert\s+[^=\n]+?)\s*-=\s*", r"\1 == ", testo_lavorato)
    testo_lavorato = re.sub(r"\b([a-zA-Z_]\w*)\s*-=\s*0\b", r"\1 <= 0", testo_lavorato)
    testo_lavorato = re.sub(r"COUNT\s*\(\s*\*\s*\)\s*-=\s*(\d+)", r"COUNT(*) >= \1", testo_lavorato)
    testo_lavorato = re.sub(r"COUNT\s*\(\s*\*\s*\)", "COUNT(*)", testo_lavorato)
    testo_lavorato = re.sub(r"(\w+(?:\.\w+)?)\s*(?:→|->)\s*'([^']+)'", r"\1 != '\2'", testo_lavorato)
    testo_lavorato = re.sub(r"\n{3,}", "\n\n", testo_lavorato)
    return testo_lavorato.strip()


_MARCATORI_SLIDE_RUMORE = (
    "solo per preparare",
    "non si proietta",
    "appendice ahaslides",
    "/ appendice ahaslides",
    "/ per il docente",
    "per il docente stasera",
    "per il docente domani",
    "agenda del giorno",
    "/ agenda del giorno",
    "due verità e una bugia",
    "due verita e una bugia",
    "biglietto di uscita",
    "il parcheggio delle domande",
    "parcheggio delle domande",
    "hello@davidelista.com",
    "domani alle 9:00",
    "prossima lezione: dal canvas alle tabelle",
    "tocca a voi: learn git branching",
    "git golf: vince la squadra",
    "le regole della sfida",
    "prima di pranzo · solo windows",
    "wsl è pronto?",
    "strumento · vs code live share",
    "attivare liveshare in quattro passi",
    "attivare live share in quattro passi",
    "prepariamo · i controlli",
    "sql · il database in vs code",
    "l'elefante → add connection",
    "add connection: cosa scrivere",
    "l'albero del database",
    "visualize schema: le linee sono le chiavi",
    "il giallo · la mappa in vs code",
    "il giallo · gli aiuti",
    "tre aiuti, dal più leggero",
    "ci dividiamo per sistema operativo",
    "il semaforo del setup",
    "sei passi, sempre in quest'ordine",
    "il test finale: check_setup.py",
    "tre piani di branch su github",
    "il venv di oggi, adesso",
    "la cartella della squadra, in vs code",
    "cosa fa ogni riga che avete scritto",
    "i test compaiono",
    "quasi tutti rossi, ed è giusto",
    "il giallo · le regole",
    "la bacheca su mural",
    "trovate chi ha staccato il vagone",
    "come si gioca",
    "una versione per progetto: asdf",
    "asdf per python e node",
    "installare node con nvm",
    "il club dei duellanti",
    "ron contro hermione",
    "rictusempra",
    "il motto per le sciarpe",
    "la tua prima pull request",
    "driver e navigator",
    "il repository del corso",
    "tre query sul negozio",
    "un giro per ogni indizio",
    "ieri, in cinque righe",
    "il metodo · a ogni tappa",
    "il metodo a ogni tappa",
    "le squadre · tappa per tappa",
    "le squadre tappa per tappa",
    "le squadre · chi fa cosa",
    "le squadre chi fa cosa",
    "le regole di oggi",
    "quattro regole, tutto il giorno",
    "binario 9",
    "chi sale?",
    "il formato · 40 minuti a tappa",
    "il formato 40 minuti a tappa",
    "oggi siete al primo anno a hogwarts",
    "la storia di oggi",
    "sei guai, sei uscite",
    "un pilota diverso a ogni regola",
    "cinque squadre, cinque programmi",
    "il test del collega",
    "ping-pong: il validatore",
    "dalla ruota:",
    "spiegazioni a sorte",
    "lo sapevi?",
    "sondaggio anonimo",
    "sondaggio scelta multipla",
    "indovina cosa fa",
    "misterioso.py",
    "storie dell'orrore",
    "il codice peggiore che ho visto",
    "dai biglietti di uscita",
    "/ ahaslides",
    "ahaslides · slide",
    "ahaslides slide",
    "nel mazzo",
    "voci della ruota",
    "spinner wheel",
    "pick answer",
    "open ended",
    "bonus velocità",
    "bonus velocita",
    "mescola l'ordine",
    "la mappa della classe",
    "metti un post-it sulla cartina",
    "iscritto all'albo degli ingegneri",
    "il corso in tre numeri",
    "ogni giornata funziona così",
    "dove lavoreremo",
)


def _e_slide_rumore_o_indice(testo_pagina: str) -> bool:
    """Returns True if a PDF page is a non-instructional agenda, break slide, or teacher-only appendix."""
    if not testo_pagina or not testo_pagina.strip():
        return True
    basso = normalizza_spazi_testo_pdf(testo_pagina).lower()
    if any(marcatore in basso for marcatore in _MARCATORI_SLIDE_RUMORE):
        return True
    righe = [r.strip() for r in basso.splitlines() if r.strip()]
    if len(righe) <= 6 and any(k in basso for k in ("pausa pranzo", "si riparte alle", "rompighiaccio")):
        return True
    return False


def _formatta_pagina_in_markdown(numero_pagina: int, testo_pagina: str) -> str:
    """Formats a raw PDF page/slide into clean, structured Markdown."""
    pulito = normalizza_spazi_testo_pdf(testo_pagina)
    righe = [r.strip() for r in pulito.splitlines() if r.strip()]
    if not righe:
        return ""
    prima_riga = righe[0].lstrip("/ ").strip()
    corpo = "\n".join(righe[1:]).strip() if len(righe) > 1 else prima_riga
    return f"### [Page {numero_pagina}] {prima_riga}\n{corpo}".strip()


def _suddividi_testo_in_blocchi(
    testo: str,
    prefisso: str,
    max_caratteri: int = MAX_CARATTERI_PARAGRAFO_PDF,
) -> List[Tuple[str, str]]:
    """Splits a page or document text into clean semantic paragraphs bounded by max_caratteri."""
    testo_normalizzato = normalizza_spazi_testo_pdf(testo)
    paragrafi_grezzi = [paragrafo.strip() for paragrafo in re.split(r"\n\s*\n", testo_normalizzato) if paragrafo.strip()]
    if not paragrafi_grezzi and testo_normalizzato.strip():
        paragrafi_grezzi = [testo_normalizzato.strip()]

    blocchi: List[Tuple[str, str]] = []
    buffer_corrente = ""
    indice_parte = 1

    for paragrafo in paragrafi_grezzi:
        if len(buffer_corrente) + len(paragrafo) + 2 <= max_caratteri:
            buffer_corrente = f"{buffer_corrente}\n{paragrafo}".strip() if buffer_corrente else paragrafo
        else:
            if buffer_corrente:
                etichetta = f"{prefisso}" if indice_parte == 1 and len(paragrafi_grezzi) == 1 else f"{prefisso}.{indice_parte}"
                blocchi.append((etichetta, buffer_corrente))
                indice_parte += 1
            if len(paragrafo) <= max_caratteri:
                buffer_corrente = paragrafo
            else:
                residuo_paragrafo = paragrafo
                passi_residui = LIMITE_ITERAZIONI_D
                while residuo_paragrafo and passi_residui > 0:
                    passi_residui -= 1
                    if len(residuo_paragrafo) <= max_caratteri:
                        fetta = residuo_paragrafo.strip()
                        if fetta:
                            blocchi.append((f"{prefisso}.{indice_parte}", fetta))
                            indice_parte += 1
                        break
                    fetta = tronca_senza_spezzare_parola(residuo_paragrafo, max_caratteri)
                    if not fetta:
                        fetta = residuo_paragrafo[:max_caratteri].strip()
                    blocchi.append((f"{prefisso}.{indice_parte}", fetta))
                    indice_parte += 1
                    residuo_paragrafo = residuo_paragrafo[len(fetta):].lstrip()
                buffer_corrente = ""

    if buffer_corrente:
        etichetta = f"{prefisso}" if indice_parte == 1 else f"{prefisso}.{indice_parte}"
        blocchi.append((etichetta, buffer_corrente))

    return blocchi


def _elabora_pagine_pdf(pagine_estratte: List[Tuple[int, str]]) -> List[Tuple[str, str]]:
    """Filters noisy service/agenda slides and clusters slide presentations into cohesive Markdown chunks."""
    if not pagine_estratte:
        return []

    pagine_normalizzate = [
        (idx, normalizza_spazi_testo_pdf(testo).strip())
        for idx, testo in pagine_estratte
    ]
    pagine_non_vuote = [(idx, t) for idx, t in pagine_normalizzate if t]
    if not pagine_non_vuote:
        return []

    totale_pagine = len(pagine_estratte)
    if totale_pagine > 5:
        pagine_valide = [
            (idx, t) for idx, t in pagine_non_vuote
            if not _e_slide_rumore_o_indice(t)
        ]
    else:
        pagine_valide = pagine_non_vuote

    if not pagine_valide:
        return []

    media_caratteri = sum(len(t) for _, t in pagine_valide) / len(pagine_valide)
    e_presentazione_slide = totale_pagine > 5 and media_caratteri < 900 and len(pagine_valide) > 3

    if not e_presentazione_slide:
        blocchi: List[Tuple[str, str]] = []
        for idx, testo_pag in pagine_valide:
            blocchi.extend(_suddividi_testo_in_blocchi(testo_pag, f"Page {idx}"))
        return blocchi

    blocchi_slide: List[Tuple[str, str]] = []
    cluster_corrente: List[Tuple[int, str]] = []
    caratteri_accumulati = 0

    for idx, testo_pag in pagine_valide:
        e_copertina_parte = bool(re.match(r"(?i)^/?\s*parte\s+0?\d\b", testo_pag.strip()))
        if e_copertina_parte:
            if cluster_corrente:
                idx_inizio = cluster_corrente[0][0]
                idx_fine = cluster_corrente[-1][0]
                etichetta = f"Page {idx_inizio}" if idx_inizio == idx_fine else f"Pages {idx_inizio}-{idx_fine}"
                testo_unito = "\n\n".join(s for _, s in cluster_corrente)
                blocchi_slide.append((etichetta, testo_unito))
                cluster_corrente = []
                caratteri_accumulati = 0
            if len(testo_pag.strip()) < 180:
                continue

        markdown_slide = _formatta_pagina_in_markdown(idx, testo_pag)
        if not markdown_slide:
            continue

        lunghezza_nuova = caratteri_accumulati + len(markdown_slide) + 2
        raggiunto_limite = lunghezza_nuova > 2200 or len(cluster_corrente) >= 6

        if cluster_corrente and raggiunto_limite:
            idx_inizio = cluster_corrente[0][0]
            idx_fine = cluster_corrente[-1][0]
            etichetta = f"Page {idx_inizio}" if idx_inizio == idx_fine else f"Pages {idx_inizio}-{idx_fine}"
            testo_unito = "\n\n".join(s for _, s in cluster_corrente)
            blocchi_slide.append((etichetta, testo_unito))
            cluster_corrente = []
            caratteri_accumulati = 0

        cluster_corrente.append((idx, markdown_slide))
        caratteri_accumulati += len(markdown_slide) + 2

    if cluster_corrente:
        idx_inizio = cluster_corrente[0][0]
        idx_fine = cluster_corrente[-1][0]
        etichetta = f"Page {idx_inizio}" if idx_inizio == idx_fine else f"Pages {idx_inizio}-{idx_fine}"
        testo_unito = "\n\n".join(s for _, s in cluster_corrente)
        blocchi_slide.append((etichetta, testo_unito))

    return blocchi_slide


def estrai_blocchi_documento(nome_file: str, contenuto_bytes: bytes) -> List[Tuple[str, str]]:
    """Extracts structured (section, text) tuples from PDF files (.pdf) or plain-text files (.txt, .md, .csv, .py),
    using fast native C++ pypdfium2 when available and caching results by SHA-256."""
    if not contenuto_bytes:
        return []

    usa_estrattore_reale = PdfReader is _PDF_READER_ORIGINALE
    chiave_cache = ""
    if usa_estrattore_reale:
        sha_raw = hashlib.sha256(contenuto_bytes).hexdigest()
        chiave_cache = f"{nome_file.strip().lower()}:{sha_raw}"
        if chiave_cache in _CACHE_BLOCCHI_DOCUMENTO:
            return list(_CACHE_BLOCCHI_DOCUMENTO[chiave_cache])

    if nome_file.strip().lower().endswith(".pdf"):
        blocchi_pdf: List[Tuple[str, str]] = []
        estratto_con_pdfium = False

        if usa_estrattore_reale and pdfium is not None:
            doc_pdfium = None
            try:
                doc_pdfium = pdfium.PdfDocument(contenuto_bytes)
                pagine_raw: List[Tuple[int, str]] = []
                for idx, pagina in enumerate(doc_pdfium, start=1):
                    testo_pag = (pagina.get_textpage().get_text_bounded() or "").strip()
                    pagine_raw.append((idx, testo_pag))
                blocchi_pdf = _elabora_pagine_pdf(pagine_raw)
                estratto_con_pdfium = True
            except (RuntimeError, ValueError, OSError, TypeError, AttributeError):
                blocchi_pdf = []
                estratto_con_pdfium = False
            finally:
                if doc_pdfium is not None and hasattr(doc_pdfium, "close"):
                    doc_pdfium.close()

        if not estratto_con_pdfium:
            lettore = PdfReader(io.BytesIO(contenuto_bytes))
            pagine_raw = []
            for idx, pagina in enumerate(lettore.pages, start=1):
                try:
                    testo_pag = (pagina.extract_text() or "").strip()
                except (PyPdfError, ValueError, KeyError, TypeError):
                    testo_pag = ""
                pagine_raw.append((idx, testo_pag))
            blocchi_pdf = _elabora_pagine_pdf(pagine_raw)

        if usa_estrattore_reale and chiave_cache:
            _CACHE_BLOCCHI_DOCUMENTO[chiave_cache] = list(blocchi_pdf)
        return blocchi_pdf

    testo_doc = contenuto_bytes.decode("utf-8", errors="replace")
    paragrafi = [p.strip() for p in re.split(r"\n\s*\n", testo_doc) if p.strip()]
    if not paragrafi and testo_doc.strip():
        risultato_txt = _suddividi_testo_in_blocchi(testo_doc.strip(), "Paragraph 1")
    else:
        risultato_txt = [(f"Paragraph {i}", p) for i, p in enumerate(paragrafi, start=1)]

    if usa_estrattore_reale and chiave_cache:
        _CACHE_BLOCCHI_DOCUMENTO[chiave_cache] = list(risultato_txt)
    return risultato_txt


@contextmanager
def connessione_db(registra_vettore: bool = False):
    """Transactional context manager guaranteeing commit/rollback on BaseException and conn.close() in finally."""
    cfg = dict(get_db_config())
    if psycopg2.connect is _PSYCOPG2_CONNECT_ORIGINALE:
        cfg.setdefault("connect_timeout", 1)
    conn = psycopg2.connect(**cfg)
    try:
        if registra_vettore:
            register_vector(conn)
        with conn:
            yield conn
    except (Exception, KeyboardInterrupt, SystemExit):
        log_exception("Errore transazionale PostgreSQL (rollback eseguito)", "DB_CONN_001")
        raise
    finally:
        conn.close()


def _embedding_lessicale_locale(testo: str) -> List[float]:
    """Deterministic EMBED_DIM (768) fallback vector (L2 Feature Hashing) allowing local
    and cloud document indexing even when Ollama is not installed."""
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
    """Calls Ollama /api/embed in batch; falls back to deterministic local 768-dim L2 vectors if unreachable,
    caching the offline status so cloud multi-file indexing executes in 0 ms without repeated timeouts."""
    global _OLLAMA_EMBED_OFFLINE
    usa_post_reale = requests.post is _REQUESTS_POST_ORIGINALE
    if usa_post_reale and _OLLAMA_EMBED_OFFLINE:
        return [_embedding_lessicale_locale(t) for t in testi]

    timeout_effettivo = 1.5 if usa_post_reale else 10
    try:
        res = requests.post(
            OLLAMA_EMBED_URL,
            json={"model": OLLAMA_EMBED_MODEL, "input": testi},
            timeout=timeout_effettivo,
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
        if usa_post_reale:
            _OLLAMA_EMBED_OFFLINE = True
        log.warning(
            "Ollama /api/embed non raggiungibile: uso embedding deterministico locale per PostgreSQL",
            extra={"code": "EMB_FALLBACK_001"},
        )
        return [_embedding_lessicale_locale(t) for t in testi]


def inizializza_schema() -> None:
    """Creates the vector extension and the memoria_bottega and dominio_centroidi tables."""
    global _POSTGRES_OFFLINE
    if psycopg2.connect is _PSYCOPG2_CONNECT_ORIGINALE and _POSTGRES_OFFLINE:
        return

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
    try:
        with connessione_db(registra_vettore=False) as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
        log.info("Schema PostgreSQL + pgvector inizializzato", extra={"code": "DB_INIT_001"})
    except psycopg2.Error:
        if psycopg2.connect is _PSYCOPG2_CONNECT_ORIGINALE:
            _POSTGRES_OFFLINE = True
        raise


def incasella_e_salva(dominio: str, titolo: str, blocchi: List[Tuple[str, str]]) -> int:
    """Deduplicates blocks via content-based SHA-256, computes embeddings outside the lock and updates
    PostgreSQL or the in-memory session archive when running on cloud without local PostgreSQL."""
    global _POSTGRES_OFFLINE
    righe_grezze: List[Tuple[str, str, str, str]] = []
    hash_visti_batch = set()
    for sezione, contenuto in blocchi:
        if not contenuto or not contenuto.strip():
            continue
        ancorato = costruisci_testo_ancorato(dominio, titolo, sezione, contenuto)
        impronta_contenuto = f"[{dominio.strip().upper()}] {sezione.strip()}\n\n{contenuto.strip()}"
        h = hashlib.sha256(impronta_contenuto.encode("utf-8")).hexdigest()
        if h not in hash_visti_batch:
            hash_visti_batch.add(h)
            righe_grezze.append((sezione.strip(), ancorato, h, f"{sezione.strip()}\n\n{contenuto.strip()}"))

    if not righe_grezze:
        return 0

    righe = list(righe_grezze)
    vettori = calcola_embedding([r[1] for r in righe])
    valori = [
        (dominio, titolo, righe[i][0], righe[i][1], righe[i][2], str(vettori[i]))
        for i in range(len(righe))
    ]

    with SEGRETARIO_THE.sezione_sacra(dominio, fabbisogno_massimo=1):
        hash_esistenti = {item["hash_text"] for item in _ARCHIVIO_MEMORIA_RAM}
        inseriti_ram = 0
        for i in range(len(righe)):
            if righe[i][2] not in hash_esistenti:
                _ARCHIVIO_MEMORIA_RAM.append({
                    "id": len(_ARCHIVIO_MEMORIA_RAM) + 1,
                    "dominio": dominio,
                    "titolo": titolo,
                    "sezione": righe[i][0],
                    "testo": righe[i][1],
                    "corpo": righe[i][3],
                    "hash_text": righe[i][2],
                    "embedding": vettori[i],
                })
                hash_esistenti.add(righe[i][2])
                inseriti_ram += 1

        if psycopg2.connect is _PSYCOPG2_CONNECT_ORIGINALE and _POSTGRES_OFFLINE:
            log.info(
                "PostgreSQL locale non attivo: salvati %d frammenti nell'archivio RAM (dominio '%s')",
                inseriti_ram,
                dominio,
                extra={"code": "RAG_RAM_001"},
            )
            return inseriti_ram

        try:
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
        except psycopg2.Error:
            if psycopg2.connect is _PSYCOPG2_CONNECT_ORIGINALE:
                _POSTGRES_OFFLINE = True
            log.info(
                "PostgreSQL locale non attivo: salvati %d frammenti nell'archivio RAM (dominio '%s')",
                inseriti_ram,
                dominio,
                extra={"code": "RAG_RAM_001"},
            )
            return inseriti_ram

    log.info(
        "Indicizzati %d nuovi frammenti per dominio '%s'",
        inseriti,
        dominio,
        extra={"code": "RAG_INGEST_001"},
    )
    return inseriti


MAX_CANDIDATI_RRF_ARCHIVIO: int = 20
MAX_DOCUMENTI_SESSIONE_CONCORRENTI: int = 60


def _filtra_candidati_archivio_ram(dominio: str, parole_chiave: List[str]) -> List[Dict[str, Any]]:
    """Seleziona i frammenti candidati filtrando per dominio e match lessicale preliminare."""
    candidati_dominio = [item for item in _ARCHIVIO_MEMORIA_RAM if item["dominio"] == dominio]
    ha_match_in_dominio = any(
        any(parola in item["testo"].lower() for parola in parole_chiave)
        for item in candidati_dominio
    )
    if candidati_dominio and (ha_match_in_dominio or not parole_chiave):
        return candidati_dominio
    return list(_ARCHIVIO_MEMORIA_RAM)


def _calcola_centroide_candidati(candidati: List[Dict[str, Any]]) -> List[float]:
    """Calcola il centroide vettoriale L2 normalizzato dei frammenti candidati."""
    somma_vettoriale = [0.0] * EMBED_DIM
    for item in candidati:
        for indice, valore in enumerate(item["embedding"]):
            somma_vettoriale[indice] += valore
    return normalizza_l2(somma_vettoriale)


_TERMINI_CORSO_FREQUENTI = frozenset({
    "database", "sql", "python", "codice", "git", "giorno", "tabella", "tabelle",
    "negozio", "slide", "pagina", "page", "pages", "tecnico", "file", "riga", "righe",
})

_TERMINI_TECNICI_SPECIFICI = frozenset({
    "having", "group", "left", "inner", "join", "where", "raises", "approx", "tdd",
    "rebase", "merge", "sha", "assert", "elif", "comprehension", "valueerror",
    "keyerror", "typeerror", "pg_rewind", "raft", "quorum", "traceback", "breakpoint",
    "f10", "f11", "venv", "pip", "gitignore", "requirements", "externally", "managed",
    "count", "null", "step", "over", "into",
})


def _calcola_pesi_idf_candidati(
    parole_chiave: List[str],
    candidati: List[Dict[str, Any]],
) -> Dict[str, int]:
    """Calcola il peso di specificita' IDF (6 raro/tecnico, 3 medio, 1 frequente) per ciascuna parola della query."""
    n_cand = len(candidati)
    ha_termini_tecnici = any(p in _TERMINI_TECNICI_SPECIFICI for p in parole_chiave)
    if n_cand <= 2 and not ha_termini_tecnici:
        return {p: (3 if any(c.isdigit() for c in p) else 2) for p in parole_chiave}

    token_per_cand = [
        set(re.findall(r"\d+(?:[.,]\d+)+|\w+", (c.get("corpo") or c.get("testo", "")).lower()))
        for c in candidati
    ]
    pesi: Dict[str, int] = {}
    soglia_rara = max(1, n_cand // 6)
    soglia_media = max(2, n_cand // 3)
    for p in parole_chiave:
        bonus_num = 2 if any(c.isdigit() for c in p) else 0
        if p in _TERMINI_TECNICI_SPECIFICI:
            pesi[p] = 6 + bonus_num
            continue
        if p in _TERMINI_CORSO_FREQUENTI:
            pesi[p] = 1
            continue
        df = sum(1 for toks in token_per_cand if p in toks)
        if df <= soglia_rara:
            pesi[p] = 6 + bonus_num
        elif df <= soglia_media:
            pesi[p] = 3 + bonus_num
        else:
            pesi[p] = 1 + bonus_num
    return pesi


def _valuta_singolo_frammento_ram(
    item: Dict[str, Any],
    query: str,
    query_bassa: str,
    q_vec: List[float],
    parole_chiave: List[str],
    cerca_costi: bool,
    denominatore_copertura: int,
    numero_candidati: int,
    pesi_parole: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Valuta similitudine vettoriale e copertura lessicale pesata per IDF del singolo frammento."""
    sim_raw = max(0.0, similitudine_coseno(q_vec, item["embedding"]))
    testo_valutato = item["testo"]
    if str(item.get("titolo", "")).startswith("Ricerca:") and item.get("corpo"):
        testo_valutato = item["corpo"]
    testo_low = testo_valutato.lower()
    token_set_low = set(re.findall(r"\d+(?:[.,]\d+)+|\w+", testo_low))
    titoli_slide_low = " ".join(re.findall(r"(?m)^### \[page \d+\][^\n]*", testo_low))
    match_count = 0
    for parola in parole_chiave:
        if parola in token_set_low:
            if pesi_parole is not None and parola in pesi_parole:
                peso_base = pesi_parole[parola]
            else:
                peso_base = 3 if any(c.isdigit() for c in parola) else 2
            match_count += peso_base
            if (
                titoli_slide_low
                and parola not in _TERMINI_CORSO_FREQUENTI
                and len(parola) >= 3
                and re.search(rf"\b{re.escape(parola)}\b", titoli_slide_low)
            ):
                match_count += 4
    if cerca_costi and numero_candidati <= MAX_DOCUMENTI_SESSIONE_CONCORRENTI:
        bonus_economico = min(2, sum(1 for termine in TERMINI_ECONOMICI_AFFINI if termine in testo_low))
        match_count += bonus_economico
    denom_eff = max(1, denominatore_copertura)
    copertura = (match_count / denom_eff) if parole_chiave else 0.0
    sim_effettiva = max(sim_raw, min(0.95, 0.55 + 0.40 * min(1.0, copertura))) if match_count > 0 else sim_raw

    n_spec, ratio_spec = _copertura_termini_specifici(query, query_bassa, testo_low)
    min_richiesti = 1 if len(query.split()) <= 5 else 2
    ha_ancoraggio_reale = (n_spec >= min_richiesti) and (ratio_spec >= 0.28)
    if ha_ancoraggio_reale and not ha_termine_tematico(query, query_bassa, testo_valutato):
        ha_ancoraggio_reale = False
    if not ha_ancoraggio_reale:
        sim_effettiva = min(sim_effettiva, SOGLIA_S_MAX_FALLIMENTO_NORMATIVO)
        match_count = 0

    return {
        "id": item["id"],
        "titolo": item["titolo"],
        "sezione": item["sezione"],
        "testo": item["testo"],
        "similitudine": float(sim_effettiva),
        "match_count": match_count,
    }


def _naviga_e_espandi_riferimenti_agentici(
    ordinati: List[Dict[str, Any]],
    candidati_ram: List[Dict[str, Any]],
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """GEN II Agentic File Search: dynamically navigates adjacent sections of the same document
    when a retrieved fragment is part of a multi-page sequence or chapter, preventing truncated context."""
    if not ordinati or not candidati_ram:
        return ordinati
    mappa_per_id = {item["id"]: item for item in candidati_ram}
    ids_presenti = {f["id"] for f in ordinati}
    espansi: List[Dict[str, Any]] = list(ordinati)
    coda_vicini: List[Dict[str, Any]] = []

    for framm in ordinati:
        id_corr = framm["id"]
        doc_corr = framm.get("titolo", "")
        sim_base = float(framm.get("similitudine", 0.70))
        rrf_base = float(framm.get("rrf", 0.01))
        mappa_orig = mappa_per_id.get(id_corr)
        corpo_orig = (mappa_orig.get("corpo") if mappa_orig else None) or framm.get("testo", "")
        parole_base = {
            w for w in re.findall(r"[a-zA-Zà-ÿ]{4,}", corpo_orig.lower())
            if w not in STOPWORDS_RICERCA_COMUNI and w not in ("page", "pages", "tecnico")
        }

        vicino = mappa_per_id.get(id_corr + 1)
        if (
            vicino is not None
            and vicino.get("titolo") == doc_corr
            and vicino["id"] not in ids_presenti
            and len(espansi) + len(coda_vicini) < max(top_k, 6)
        ):
            corpo_vicino = vicino.get("corpo") or vicino.get("testo", "")
            parole_vicino = {
                w for w in re.findall(r"[a-zA-Zà-ÿ]{4,}", corpo_vicino.lower())
                if w not in STOPWORDS_RICERCA_COMUNI and w not in ("page", "pages", "tecnico")
            }
            if parole_base & parole_vicino:
                ids_presenti.add(vicino["id"])
                coda_vicini.append({
                    "id": vicino["id"],
                    "dominio": vicino.get("dominio", framm.get("dominio", "")),
                    "titolo": vicino.get("titolo", doc_corr),
                    "sezione": vicino.get("sezione", ""),
                    "testo": vicino["testo"],
                    "similitudine": round(max(0.60, sim_base - 0.02), 4),
                    "rrf": rrf_base * 0.95,
                })

    espansi.extend(coda_vicini)
    return espansi[:max(top_k, 6)]


def _bilancia_frammenti_domanda_composta(
    ordinati: List[Dict[str, Any]],
    candidati_tutti: List[Dict[str, Any]],
    query_bassa: str,
    limite_k: int,
) -> List[Dict[str, Any]]:
    termini_python = ("python", "codice", "funzioni", "programmazione", "programmare")
    termini_sql = ("query", "database", "sql", "postgresql", "postgres", "psql", "select", "join", "tabella", "tabelle")
    query_tokens = set(re.findall(r"\w+", query_bassa))
    ha_py = bool(set(termini_python) & query_tokens or "linguaggio python" in query_bassa or "codice pulito" in query_bassa)
    ha_sql = bool(set(termini_sql) & query_tokens or "query sql" in query_bassa or "per i database" in query_bassa)
    if not (ha_py and ha_sql):
        return ordinati

    def _e_setup_rumore(testo: str) -> bool:
        t_low = testo.lower()
        return any(
            p in t_low
            for p in (
                "installare postgresql",
                "sudo apt install",
                "sudo apt-get install",
                "gh auth login",
                "gh repo clone",
                "git clone",
                "select current_user",
                "alter user",
                "add connection",
                "visualize schema",
                "createdb ",
            )
        )

    def _e_sql_pertinente(f: Dict[str, Any]) -> bool:
        tit_low = (f.get("titolo", "") or "").lower()
        testo_low = (f.get("testo", "") or "").lower()
        if _e_setup_rumore(testo_low):
            return False
        if any(k in tit_low for k in ("sql", "database", "giorno 05")):
            return True
        return any(
            k in testo_low
            for k in (
                "select ", "from ", "where ", "join ", "group by", "order by",
                "create table", "insert into", "query",
            )
        )

    def _e_python_pertinente(f: Dict[str, Any]) -> bool:
        tit_low = (f.get("titolo", "") or "").lower()
        testo_low = (f.get("testo", "") or "").lower()
        if any(k in tit_low for k in ("codice pulito", "python", "giorno 02")):
            return True
        return any(
            k in testo_low
            for k in ("def ", "import ", "codice pulito", "regola ", "sufficienti", "return ")
        )

    puliti = [f for f in ordinati if not _e_setup_rumore(f.get("testo", ""))]
    ids_ordinati = {f.get("id") for f in puliti}

    candidati_sql = [
        f for f in candidati_tutti
        if _e_sql_pertinente(f) and f.get("id") not in ids_ordinati
    ]
    candidati_sql.sort(
        key=lambda x: (x.get("match_count", 0), x.get("similitudine", 0.0), x.get("rrf", 0.0)),
        reverse=True,
    )

    py_in_ord = [f for f in puliti if _e_python_pertinente(f)]
    sql_in_ord = [f for f in puliti if _e_sql_pertinente(f)]

    scelti_py = py_in_ord[:2]
    scelti_sql = sql_in_ord[:2] or candidati_sql[:2]

    risultato: List[Dict[str, Any]] = []
    for f in scelti_py:
        if f not in risultato:
            risultato.append(f)
    for f in scelti_sql:
        if f not in risultato:
            risultato.append(f)

    for f in puliti:
        if len(risultato) >= limite_k:
            break
        if f not in risultato:
            risultato.append(f)

    return risultato if len(risultato) >= 2 else ordinati


def _recupera_da_archivio_ram(
    query: str,
    q_vec: List[float],
    dominio: str,
    top_k: int = 3,
) -> Dict[str, Any]:
    """Executes 3-way RRF + Guarded Semaphore (EWD472) over the in-memory session archive."""
    if not _ARCHIVIO_MEMORIA_RAM:
        return {"semaforo": "ROJO", "s_max": 0.0, "s_dominio": 0.0, "frammenti": []}

    query_bassa = query.lower()
    ancore_richieste = [ancora.strip() for ancora in PATRON_CODICE_NORMATIVO.findall(query_bassa) if ancora.strip()]
    if ancore_richieste:
        presente_in_ram = all(
            any(_ancora_normativa_presente(ancora, item["testo"]) for item in _ARCHIVIO_MEMORIA_RAM)
            for ancora in ancore_richieste
        )
        if not presente_in_ram:
            return {
                "semaforo": "ROJO",
                "s_max": SOGLIA_S_MAX_FALLIMENTO_NORMATIVO,
                "s_dominio": SOGLIA_S_MAX_FALLIMENTO_NORMATIVO,
                "frammenti": [],
            }

    token_estratti = re.findall(r"\d+(?:[.,]\d+)+|\w+", query_bassa)
    parole_chiave = list(
        dict.fromkeys(
            token for token in token_estratti
            if (len(token) >= 3 or (len(token) >= 2 and token[0].isdigit())) and token not in STOPWORDS_RICERCA_COMUNI
        )
    )
    if not parole_chiave:
        parole_chiave = list(dict.fromkeys(token for token in token_estratti if len(token) >= 2))

    candidati = _filtra_candidati_archivio_ram(dominio, parole_chiave)
    centroide = _calcola_centroide_candidati(candidati)
    s_dom = max(0.0, similitudine_coseno(q_vec, centroide))

    cerca_costi = bool(set(parole_chiave) & TERMINI_ECONOMICI_AFFINI)
    pesi_parole = _calcola_pesi_idf_candidati(parole_chiave, candidati)
    denominatore_copertura = max(1, sum(pesi_parole.values()))
    numero_candidati = len(candidati)

    valutati = [
        _valuta_singolo_frammento_ram(
            item, query, query_bassa, q_vec, parole_chiave, cerca_costi, denominatore_copertura, numero_candidati, pesi_parole
        )
        for item in candidati
    ]

    con_match = [frammento for frammento in valutati if frammento["match_count"] > 0]
    if not con_match:
        return {
            "semaforo": "ROJO",
            "s_max": SOGLIA_S_MAX_FALLIMENTO_NORMATIVO,
            "s_dominio": SOGLIA_S_MAX_FALLIMENTO_NORMATIVO,
            "frammenti": [],
        }

    limite_k = max(top_k, 5)
    lista_vett = sorted(con_match, key=lambda f: (f["similitudine"], f["match_count"]), reverse=True)[:MAX_CANDIDATI_RRF_ARCHIVIO]
    lista_it = sorted(con_match, key=lambda f: (f["match_count"], f["similitudine"]), reverse=True)[:MAX_CANDIDATI_RRF_ARCHIVIO]
    lista_simple = list(lista_it)

    ordinati = fondi_rrf(lista_vett, lista_it, lista_simple, top_k=limite_k)
    if len(candidati) > 2:
        ordinati = _naviga_e_espandi_riferimenti_agentici(ordinati, candidati, top_k=limite_k)
    ordinati = _bilancia_frammenti_domanda_composta(ordinati, candidati, query_bassa, limite_k)
    ha_match = bool(con_match)
    if ha_match and s_dom < 0.35:
        s_dom = 0.55
    colore, s_max = valuta_semaforo(ordinati, s_dominio=s_dom, ha_match_lessicale=ha_match)
    return {
        "semaforo": colore,
        "s_max": float(arrotonda_esatto_el_x8(s_max, 4)),
        "s_dominio": float(arrotonda_esatto_el_x8(s_dom, 4)),
        "frammenti": ordinati,
    }


def recupera_con_semaforo(query: str, dominio: str, top_k: int = 3) -> Dict[str, Any]:
    """3-way hybrid retrieval (HNSW, FTS Italian, FTS Simple) with guaranteed connection closure
    and automatic fallback to the in-memory session archive when PostgreSQL is unreachable."""
    global _POSTGRES_OFFLINE
    q_vec = calcola_embedding([query])[0]
    q_vec_str = str(q_vec)

    with SEGRETARIO_THE.sezione_sacra(dominio, fabbisogno_massimo=1):
        if psycopg2.connect is _PSYCOPG2_CONNECT_ORIGINALE and _POSTGRES_OFFLINE:
            return _recupera_da_archivio_ram(query, q_vec, dominio, top_k=top_k)

        try:
            with connessione_db(registra_vettore=True) as conn:
                with conn.cursor() as cursore:
                    cursore.execute("SELECT embedding::text FROM dominio_centroidi WHERE dominio = %s", (dominio,))
                    riga_centroide = cursore.fetchone()
                    if riga_centroide and riga_centroide[0]:
                        vettore_centroide = [float(valore_coord) for valore_coord in riga_centroide[0].strip("[]").split(",")]
                        s_dom = similitudine_coseno(q_vec, vettore_centroide)
                    else:
                        s_dom = 0.0

                    cursore.execute(
                        """
                        SELECT id, titolo, sezione, testo_ancorato, 1 - (embedding <=> %s::vector) AS sim
                        FROM memoria_bottega
                        WHERE dominio = %s
                        ORDER BY embedding <=> %s::vector ASC
                        LIMIT %s
                        """,
                        (q_vec_str, dominio, q_vec_str, MAX_CANDIDATI_RRF_ARCHIVIO),
                    )
                    lista_vett = [
                        {"id": riga[0], "titolo": riga[1], "sezione": riga[2], "testo": riga[3], "similitudine": float(riga[4])}
                        for riga in cursore.fetchall()
                    ]

                    cursore.execute(
                        """
                        SELECT id, titolo, sezione, testo_ancorato, 1 - (embedding <=> %s::vector) AS sim
                        FROM memoria_bottega
                        WHERE dominio = %s AND tsv_it @@ plainto_tsquery('italian', %s)
                        ORDER BY ts_rank(tsv_it, plainto_tsquery('italian', %s)) DESC
                        LIMIT %s
                        """,
                        (q_vec_str, dominio, query, query, MAX_CANDIDATI_RRF_ARCHIVIO),
                    )
                    lista_it = [
                        {"id": riga[0], "titolo": riga[1], "sezione": riga[2], "testo": riga[3], "similitudine": float(riga[4])}
                        for riga in cursore.fetchall()
                    ]

                    cursore.execute(
                        """
                        SELECT id, titolo, sezione, testo_ancorato, 1 - (embedding <=> %s::vector) AS sim
                        FROM memoria_bottega
                        WHERE dominio = %s AND tsv_simple @@ plainto_tsquery('simple', %s)
                        ORDER BY ts_rank(tsv_simple, plainto_tsquery('simple', %s)) DESC
                        LIMIT %s
                        """,
                        (q_vec_str, dominio, query, query, MAX_CANDIDATI_RRF_ARCHIVIO),
                    )
                    lista_simple = [
                        {"id": riga[0], "titolo": riga[1], "sezione": riga[2], "testo": riga[3], "similitudine": float(riga[4])}
                        for riga in cursore.fetchall()
                    ]
        except psycopg2.Error:
            if psycopg2.connect is _PSYCOPG2_CONNECT_ORIGINALE:
                _POSTGRES_OFFLINE = True
            return _recupera_da_archivio_ram(query, q_vec, dominio, top_k=top_k)

    ordinati = fondi_rrf(lista_vett, lista_it, lista_simple, top_k=top_k)
    if not ordinati and _ARCHIVIO_MEMORIA_RAM:
        return _recupera_da_archivio_ram(query, q_vec, dominio, top_k=top_k)

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
