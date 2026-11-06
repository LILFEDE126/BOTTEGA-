#!/usr/bin/env python3
"""Layer 3 (THE): Initializes the DB schema, seeds the engineering corpus + technical cases,
and provides the multilingual cascading search connector (Handbook -> AI Web Search -> Direct Web)."""

import os
import re
from typing import List, Optional, Tuple
import requests

import config
from logging_bottega import log
from store_pgvector import incasella_e_salva, inizializza_schema
from client_ollama import rileva_lingua_testo, traduci_query_per_ricerca

CORPUS_INGEGNERIA = [
    (
        "generale",
        "Metodo Empirico, Principio di Necessita' e Diagnostica Idraulica",
        [
            (
                "Esperienza e Anatomia prima dell'Autorita'",
                "Come nell'esperimento della cera iniettata nei ventricoli per osservare la chiusura "
                "della valvola aortica, non fidarsi mai di assunzioni non verificate: ispezionare "
                "il sistema nell'ordine reale e misurarne l'anatomia (AST, dati grezzi, log) "
                "prima di formulare qualsiasi giudizio.",
            ),
            (
                "Principio di Necessita' e Singola Ipotesi (Zero Mucchio)",
                "La necessita' e' maestra e guida della natura: ogni forza agisce per la via piu' diretta "
                "e il disegno piu' semplice. Di fronte a un imprevisto non mescolare mai piu' soluzioni "
                "a mucchio: isolare una sola ipotesi causale minima e sottoporla a verifica pratica.",
            ),
            (
                "Legge di Conservazione dei Flussi e Antidoto alla Paralisi",
                "Come la sezione del tronco eguaglia la somma delle sezioni dei rami, in ogni sistema "
                "(idraulico, contabile o informatico) cio' che entra deve eguagliare cio' che esce: "
                "usare gli invarianti di conservazione per localizzare dove si perde il dato o la pressione.",
            ),
            (
                "Diagnostica Idraulica: Perdita di pressione a freddo (0.4 bar)",
                "In un circuito idraulico chiuso a caldaia spenta (pressione nominale 1.5 bar), se la "
                "pressione scende di 0.4 bar ogni ora senza perdite visibili sui radiatori: "
                "Ipotesi 1 (interna): vaso di espansione scarico sotto 1.0 bar e valvola di sicurezza 3.0 bar "
                "che gocciola nello scarico. Ipotesi 2 (esterna): perdita occulta nei collettori sotto pavimento. "
                "Esperimento binario: chiudere le valvole di mandata e ritorno sotto caldaia per 1 ora.",
            ),
        ],
    ),
    (
        "tecnico",
        "Guardrail, Concorrenza e Diagnostica di Produzione",
        [
            (
                "Zero except nudi, codici di log strutturati e rilascio deterministico",
                "Un blocco 'except:' nudo inghiotte i fallimenti in silenzio. Ogni eccezione deve avere "
                "un tipo esplicito e un codice univoco (AREA_EVENTO_NNN), garantendo la chiusura delle "
                "connessioni e il rilascio dei lock dentro un blocco finally.",
            ),
            (
                "Timeout espliciti, retry selettivo e streaming onesto",
                "Ogni chiamata di rete o LLM richiede timeout esplicito e retry con backoff esponenziale "
                "(2**intento) sui soli errori transitori. Nello streaming HTTP, la durata reale si misura "
                "a corpo esaurito dentro un blocco finally, mai all'invio degli header.",
            ),
            (
                "Separazione dei lock, Segretario (EWD310) e Holyness Counter (EWD113)",
                "Per evitare il paradosso di Jantje (EWD35) e le regressioni di lock (esperimento E5), "
                "raggruppare lo stato condiviso in un Segretario dedicato con semafori P/V e proteggere "
                "i segmenti attivi con un Holyness Counter > 0 affinche' non vengano mai scaricati "
                "o liberati mentre un'operazione concorrente li sta leggendo.",
            ),
        ],
    ),
    (
        "normativo",
        "Correttezza Costruttiva a Priori, Gerarchia THE e Quadratura Contabile/Doganale",
        [
            (
                "Gerarchia ad Anelli THE (EWD196, EWD310) e Separation of Concerns (EWD447)",
                "Contro il crollo probabilistico P <= p^N (EWD273), il sistema deve essere stratificato "
                "in macchine astratte acicliche (Livelli 0..4) dove nessun livello inferiore dipende da "
                "uno superiore. Ogni modulo si dimostra corretto isolatamente tramite specifiche esterne.",
            ),
            (
                "Precondizioni Piu' Deboli wp(S, R), Guarded Commands (EWD401, EWD472) e Variante t (EWD316)",
                "Per la Legge del Miracolo Escluso wp(S, false) = false. Ogni selezione if B1->S1 [] Bn->Sn fi "
                "esige che almeno una guardia sia vera; ogni ciclo iterativo richiede un invariante P e una "
                "funzione variante intera t > 0 strettamente decrescente per garantire la terminazione.",
            ),
            (
                "Non-Determinismo Demoniaco (EWD458), Autostabilizzazione (EWD426) e Tri-Colore (EWD496A)",
                "Trattare sempre l'LLM come un avversario demoniaco (EWD458) con opzioni deterministiche "
                "(temperature=0, seed=42), arrotondamento Decimal ROUND_HALF_UP (EWD145) e Write Barrier "
                "Tri-Colore (Bianco/Grigio/Nero, EWD496A): nessuna risposta diventa NERA (consegnabile) "
                "se punta a cifre BIANCHE assenti dal contesto ufficiale.",
            ),
            (
                "Quadratura Doganale e Contabile (Caso TARIC 7604210000 e Art. 83 Ley 37/1992)",
                "Sull'importazione di profili di alluminio codice TARIC 7604210000 origine CN (Cina), "
                "non confondere mai il dazio ordinario terzi paesi del 7,50% (dal 2005) con il dazio "
                "antidumping definitivo del 32,10% (Regolamento R2105460 dal 2021). La base imponibile IVA "
                "(21%) e' data da valore merce + dazio calcolati in Decimal esatto con ROUND_HALF_UP.",
            ),
        ],
    ),
]

PRONTUARIO_ESTERNO_SOCCORSO = [
    (
        "Valvola di carico e vaso di espansione (Errore E04 / 0.3 bar - 0.4 bar)",
        "Se la pressione dell'impianto idraulico scende a 0.3 bar o perde 0.4 bar ogni ora a freddo: "
        "verificare con manometro sulla valvola Schrader la precarica del vaso di espansione (1.0 bar). "
        "Se la prova con valvole di mandata e ritorno chiuse mantiene stabile la pressione in caldaia, "
        "il vaso e' integro e la perdita si trova nel collettore dell'impianto sotto pavimento.",
    ),
    (
        "Verifica Antidumping e Landed Cost Doganale (TARIC 7604210000 / 9405423100)",
        "Per il codice TARIC 7604210000 (origine CN) il dazio ordinario e' 7,50% e l'antidumping "
        "residuo e' 32,10% (dal 2021). Per il codice 9405423100 (origine CN) il dazio ERGA OMNES "
        "e' 4,70% e l'IVA spagnola e' 21,0%.",
    ),
]


def cerca_nel_prontuario_esterno(
    query: str,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
) -> List[Tuple[str, str]]:
    query_tradotta = traduci_query_per_ricerca(query)
    parole = {p.lower() for p in query_tradotta.split() if len(p) >= 4}
    trovati: List[Tuple[str, str]] = []
    for sezione, testo in PRONTUARIO_ESTERNO_SOCCORSO:
        blocco_lower = f"{sezione} {testo}".lower()
        if any(p in blocco_lower for p in parole):
            trovati.append((sezione, testo))

    if trovati:
        return trovati

    chiave_attiva = (api_key or os.getenv("LLM_API_KEY") or config.LLM_API_KEY or "").strip()
    provider_attivo = (provider or os.getenv("LLM_PROVIDER") or config.LLM_PROVIDER or "ollama").strip().lower()

    if chiave_attiva and provider_attivo in ("gemini", "openrouter"):
        try:
            if provider_attivo == "gemini":
                url_gemini = (
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    f"gemini-2.5-flash:generateContent?key={chiave_attiva}"
                )
                payload_g = {
                    "contents": [
                        {
                            "parts": [
                                {
                                    "text": f"Search the web for official technical facts and exact numbers for: {query}"
                                }
                            ]
                        }
                    ],
                    "tools": [{"google_search": {}}],
                }
                r_ai = requests.post(url_gemini, json=payload_g, timeout=15)
                r_ai.raise_for_status()
                parti = r_ai.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                testo_web = " ".join(p.get("text", "") for p in parti).strip()
                if testo_web:
                    return [(f"Web Search AI (Gemini Grounding): {query}", testo_web)]
            elif provider_attivo == "openrouter":
                url_or = "https://openrouter.ai/api/v1/chat/completions"
                r_or = requests.post(
                    url_or,
                    headers={"Authorization": f"Bearer {chiave_attiva}"},
                    json={
                        "model": "openrouter/free:online",
                        "messages": [
                            {
                                "role": "user",
                                "content": f"Report only verified technical facts and exact numbers from the web for: {query}",
                            }
                        ],
                    },
                    timeout=15,
                )
                r_or.raise_for_status()
                testo_or = r_or.json()["choices"][0]["message"]["content"].strip()
                if testo_or:
                    return [(f"Web Search AI (OpenRouter Online): {query}", testo_or)]
        except (requests.exceptions.RequestException, KeyError, IndexError, ValueError):
            pass

    try:
        url_ddg = "https://api.duckduckgo.com/"
        r_ddg = requests.get(
            url_ddg,
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            headers={"User-Agent": "Bottega/1.0"},
            timeout=10,
        )
        r_ddg.raise_for_status()
        dati_ddg = r_ddg.json()
        abstract_ddg = (dati_ddg.get("AbstractText") or "").strip()
        if abstract_ddg:
            tit_ddg = dati_ddg.get("Heading") or query
            trovati.append((f"API DuckDuckGo: {tit_ddg}", abstract_ddg))
    except (requests.exceptions.RequestException, ValueError, AttributeError):
        pass

    if trovati:
        return trovati

    lingua_wiki = rileva_lingua_testo(query)
    if lingua_wiki not in ("it", "en", "es"):
        lingua_wiki = "en"
    try:
        url_wiki = f"https://{lingua_wiki}.wikipedia.org/w/api.php"
        res = requests.get(
            url_wiki,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "utf8": 1,
                "format": "json",
                "srlimit": 2,
            },
            headers={"User-Agent": "Bottega/1.0"},
            timeout=10,
        )
        res.raise_for_status()
        risultati_api = res.json().get("query", {}).get("search", [])
        for item in risultati_api:
            titolo = item.get("title", "Fonte Web")
            estratto = re.sub(r"<[^>]+>", "", item.get("snippet", "")).strip()
            if estratto:
                trovati.append((f"API Wikipedia: {titolo}", estratto))
    except (requests.exceptions.RequestException, ValueError, AttributeError):
        pass

    return trovati or PRONTUARIO_ESTERNO_SOCCORSO[:1]


def esegui_seed() -> None:
    log.info("1/2 Inizializzazione schema PostgreSQL + pgvector...", extra={"code": "SEED_START_001"})
    inizializza_schema()

    log.info("2/2 Indicizzazione Corpus...", extra={"code": "SEED_ING_001"})
    totale_nuovi = 0
    for dominio, titolo, blocchi in CORPUS_INGEGNERIA:
        inseriti = incasella_e_salva(dominio, titolo, blocchi)
        totale_nuovi += inseriti
        log.info(
            "Dominio '%s': %d nuovi frammenti inseriti (su %d blocchi)",
            dominio,
            inseriti,
            len(blocchi),
            extra={"code": "SEED_DOM_001"},
        )

    log.info("Seed completato. Nuovi frammenti indicizzati: %d", totale_nuovi, extra={"code": "SEED_OK_001"})


if __name__ == "__main__":
    esegui_seed()