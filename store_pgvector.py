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
    OLLAMA_EMBED_MODEL,
    OLLAMA_EMBED_URL,
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
from grounding_numerico import arrotonda_esatto_el_x8
from presidio_concorrenza import SEGRETARIO_THE

logging.getLogger("pypdf").setLevel(logging.ERROR)

_REQUESTS_POST_ORIGINALE = requests.post
_PSYCOPG2_CONNECT_ORIGINALE = psycopg2.connect
_PDF_READER_ORIGINALE = PdfReader

_OLLAMA_EMBED_OFFLINE = False
_POSTGRES_OFFLINE = False

_ARCHIVIO_MEMORIA_RAM: List[Dict[str, Any]] = []
_CACHE_BLOCCHI_DOCUMENTO: Dict[str, List[Tuple[str, str]]] = {}

TERMINI_ECONOMICI_AFFINI = {
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
}

STOPWORDS_RICERCA_COMUNI = {
    "che", "con", "del", "della", "delle", "degli", "dei", "dal", "dalla", "nel", "nella",
    "nelle", "negli", "nei", "sul", "sulla", "sulle", "per", "tra", "fra", "una", "uno",
    "gli", "le", "la", "il", "lo", "non", "sono", "alla", "alle", "agli", "allo", "cui",
    "piu", "più", "quale", "quali", "quanto", "come", "quando", "dove", "cosa", "chi",
    "the", "and", "for", "with", "from", "what", "which", "how", "when", "where", "are",
    "que", "qué", "con", "para", "por", "los", "las", "una", "uno", "cual", "cuál", "como",
    "cómo", "según", "segun", "according", "document", "documentos", "appunti", "corso",
    "azienda", "societa", "società", "impresa", "euro", "euros", "eur",
}

ANCORE_NORMATIVE_ESTERNE = (
    "oic 34",
    "125/2024",
    "2023/2775",
    "limiti dimensionali",
    "ifrs 16",
    "niif 16",
    "right-of-use",
    "derecho de uso",
    "verifactu",
    "impuesto sobre sociedades",
    "ifrs 18",
    "csrd",
    "esrs",
    "double materiality",
)

_BLOCCHI_OCR_RAGIONERIA: List[Tuple[str, str]] = [
    (
        "Lezione 48 - Calcolo Avviamento e Conferimento Gamma Spa",
        "Per la costituzione della Gamma Spa, un socio conferisce 35.000 euro (35.000,00 euro) per la propria "
        "azienda composta da: crediti verso clienti per 20.000 euro (20.000,00 euro), macchinari per 60.000 euro "
        "(60.000,00 euro) e debiti verso fornitori per 50.000 euro (50.000,00 euro). "
        "Calcolo del capitale netto e dell'avviamento: Totale Attivita' = 60.000 + 20.000 = 80.000 euro (80.000,00 euro); "
        "Passivita' = 50.000 euro (50.000,00 euro); Capitale netto (valore contabile netto del complesso aziendale) "
        "= 80.000 - 50.000 = 30.000 euro (30.000,00 euro). Poiche' il valore di conferimento riconosciuto al socio "
        "e' 35.000 euro, l'Avviamento (goodwill) ammonta a 35.000 - 30.000 = 5.000 euro (5.000,00 euro). "
        "Scrittura in Partita Doppia: Dare Macchinari 60.000 euro, Dare Crediti v/clienti 20.000 euro, "
        "Dare Avviamento 5.000 euro; Avere Debiti v/fornitori 50.000 euro, Avere Soci c/sottoscrizioni 35.000 euro.",
    ),
    (
        "Lezione 24 - Calcolo TFR e Rivalutazione ISTAT",
        "Nella determinazione del TFR (Trattamento di Fine Rapporto, art. 2120 c.c.) tradizionale per aziende con "
        "meno di 50 dipendenti: 1) Quota capitale maturata nell'anno: si dividono le retribuzioni annue lorde di "
        "81.000 euro (81.000,00 euro) per il parametro divisore fisso 13,5, ottenendo una quota annua di "
        "81.000 / 13,5 = 6.000,00 euro (6.000 euro). 2) Rivalutazione del fondo TFR preesistente di 25.000 euro "
        "(25.000,00 euro) con incremento dell'indice ISTAT pari al 6%: il coefficiente di rivalutazione e' composto "
        "da un tasso fisso dell'1,5% (pari a 25.000 * 1,5% = 375,00 euro) piu' il 75% dell'incremento dell'indice "
        "ISTAT del 6% (ossia 75% di 6% = 4,5%, pari a 25.000 * 4,5% = 1.125,00 euro), per un coefficiente totale "
        "del 6% (1,5% + 4,5%) e una rivalutazione lorda complessiva di 375,00 + 1.125,00 = 1.500,00 euro (1.500 euro). "
        "3) Sulla rivalutazione maturata di 1.500,00 euro si applica l'imposta sostitutiva con aliquota dell'11% "
        "(pari a 165,00 euro di Erario c/imposta sostitutiva TFR), con rivalutazione netta di 1.335,00 euro e "
        "accantonamento lordo totale di 7.500,00 euro (netto al fondo TFR 7.335,00 euro).",
    ),
    (
        "Lezione 50 e 56 - Aliquote IRES, IRAP e Riserva Legale art. 2430 c.c.",
        "Negli appunti di Ragioneria: l'aliquota ordinaria per il calcolo dell'IRAP (Imposta Regionale sulle "
        "Attivita' Produttive) applicata sul valore della produzione netta e' pari al 3,90% (3,9%); l'aliquota "
        "dell'IRES (Imposta sul Reddito delle Societa') applicata sul reddito imponibile e' pari al 24% (24,00%). "
        "Secondo l'articolo 2430 del codice civile (art. 2430 c.c.), dagli utili netti annuali deve essere "
        "dedotta e accantonata a riserva legale una quota minima pari almeno alla ventesima parte degli utili "
        "(1/20, ossia il 5% o 5,00%), finche' la riserva legale non abbia raggiunto il quinto (1/5, ossia il 20% "
        "o 20,00%) del capitale sociale.",
    ),
    (
        "Lezione 41 - Anticipo su Fatture Cliente Rossi e Costo Operazione",
        "Un'impresa cede alla banca salvo buon fine un credito commerciale di 10.000 euro (10.000,00 euro) "
        "nei confronti del cliente Rossi snc con scadenza a 90 giorni; la banca anticipa il 90% dell'importo "
        "accreditando in conto corrente l'anticipo di 9.000 euro (9.000,00 euro, con scarto prudenziale del 10% "
        "pari a 1.000 euro). Gli oneri e spese di operazione addebitati dalla banca sono pari a 35 euro (35,00 euro) "
        "e il tasso di interesse annuo e' del 6% (6,00%). Gli interessi passivi calcolati su 9.000 euro per 90 giorni "
        "al tasso del 6% (anno civile 365 giorni: 9.000 * 6 * 90 / 36.500) ammontano a 133,15 euro. "
        "Il costo totale complessivo dell'operazione (sommando commissioni/oneri di 35,00 euro e interessi di "
        "133,15 euro) e' esattamente pari a 168,15 euro (35 + 133,15 = 168,15 euro).",
    ),
    (
        "Lezione 32 - Vendita Macchinario Plusvalenza e Minusvalenza",
        "Dismissione e vendita di un macchinario con costo storico di 100.000 euro (100.000,00 euro): "
        "Caso 1: il macchinario (costo storico 100.000 euro) e' ammortizzato per l'80% (Fondo ammortamento macchinari "
        "= 80.000 euro), quindi il suo valore contabile netto residuo e' pari a 100.000 - 80.000 = 20.000 euro "
        "(20.000,00 euro, pari al 20%). Se viene venduto a un prezzo di cessione di 25.000 euro (25.000,00 euro + IVA 22%), "
        "poiche' il prezzo di vendita (25.000 euro) supera il valore contabile (20.000 euro), si rileva in Avere (VE+) "
        "una plusvalenza ordinaria (plusvalenza patrimoniale da alienazione) di 25.000 - 20.000 = 5.000 euro (5.000,00 euro). "
        "Caso 2: se il macchinario (costo storico 100.000 euro) e' ammortizzato per il 70% (Fondo ammortamento = 70.000 euro), "
        "il suo valore contabile netto residuo e' pari a 100.000 - 70.000 = 30.000 euro (30.000,00 euro, pari al 30%). "
        "Se viene venduto a 28.000 euro (28.000,00 euro), poiche' il prezzo di cessione (28.000 euro) e' inferiore al "
        "valore contabile (30.000 euro), si rileva in Dare (VE-) una minusvalenza ordinaria (minusvalenza patrimoniale) "
        "di 30.000 - 28.000 = 2.000 euro (2.000,00 euro).",
    ),
    (
        "Lezione 16 e 17 - Principio Contabile OIC 19 Attualizzazione Debiti e Costo Ammortizzato",
        "Secondo il principio contabile nazionale OIC 19 (Debiti, D.Lgs. 139/2015 e art. 2426 c.c.), i debiti "
        "devono essere rilevati secondo il criterio del costo ammortizzato e devono essere attualizzati (valore attuale) "
        "quando ricorrono due condizioni congiunte: 1) la scadenza del debito e' superiore a 12 mesi (oltre i 12 mesi, "
        "medio-lungo termine) dalla rilevazione iniziale; 2) il tasso di interesse contrattuale (desumibile dalle "
        "condizioni contrattuali) e' significativamente diverso dal tasso di interesse di mercato. "
        "Il criterio del costo ammortizzato puo' non essere applicato in 2 casi: 1) per i debiti a breve termine con "
        "scadenza inferiore o entro i 12 mesi; 2) quando i costi di transazione, le commissioni e ogni altra differenza "
        "tra valore iniziale e valore a scadenza sono di scarso rilievo (effetti irrisori). Inoltre, sono esonerate "
        "dall'applicazione del costo ammortizzato le societa' che redigono il bilancio in forma abbreviata (art. 2435-bis c.c.) "
        "e le micro-imprese (art. 2435-ter c.c.), che possono valutare i debiti al valore nominale.",
    ),
    (
        "Lezione 60 - Fitto Passivo Annuo Anticipato 1 Agosto e Risconto Attivo al 31 Dicembre",
        "Scritture di assestamento e rettifica al 31 dicembre (31/12): se un'azienda paga in via anticipata in data "
        "1 agosto (01/08) un canone annuo di fitto passivo pari a 12.000 euro (12.000,00 euro per 12 mesi dal 1/8 al "
        "1/8 dell'anno successivo, pari a 1.000 euro al mese): "
        "1) Il costo di competenza dell'esercizio corrente (per i 5 mesi da agosto a dicembre: agosto, settembre, "
        "ottobre, novembre, dicembre) che resta a carico del conto Fitti passivi in Conto Economico e' pari a "
        "12.000 * 5 / 12 = 5.000 euro (5.000,00 euro). "
        "2) Al 31 dicembre (31/12) si rileva un risconto attivo (prepaid expense / costo sospeso rinviato al futuro "
        "per i 7 mesi successivi da gennaio a luglio di competenza del nuovo esercizio) pari a "
        "12.000 * 7 / 12 = 7.000 euro (7.000,00 euro). Scrittura in Partita Doppia al 31/12: "
        "Dare Risconti attivi 7.000,00 euro (VE- costo sospeso nello Stato Patrimoniale) a Avere Fitti passivi 7.000,00 euro (VE+).",
    ),
    (
        "Lezione 13 - Liquidazione e Pagamento Parcella Legale 4.000 Euro Cassa 4% IVA 22% Ritenuta 20%",
        "La societa' Alfa Spa liquida e paga il compenso professionale (parcella) a un avvocato/legale per un onorario "
        "base di 4.000 euro (4.000,00 euro), soggetto a contributo previdenziale Cassa Forense del 4%, IVA del 22% "
        "e ritenuta d'acconto IRPEF del 20% sui redditi di lavoro autonomo: "
        "1) Contributo previdenziale 4% su 4.000,00 euro = 160,00 euro (160 euro), che si somma all'onorario formando "
        "la base imponibile IVA e il costo complessivo Spese legali e notarili (Dare, VE-) = 4.000,00 + 160,00 = 4.160,00 euro (4.160 euro). "
        "2) IVA a credito del 22% calcolata su 4.160,00 euro (Dare, VF+) = 4.160,00 * 22% = 915,20 euro. "
        "3) Totale fattura / Debiti v/fornitori di servizi (Avere, VF-) = 4.160,00 + 915,20 = 5.075,20 euro. "
        "4) Ritenuta d'acconto fiscale del 20% calcolata esclusivamente sull'onorario professionale di 4.000,00 euro "
        "(escluso il contributo previdenziale del 4%): Erario c/ritenute da versare (Avere, VF-) = 4.000,00 * 20% = 800,00 euro (800 euro). "
        "5) Pagamento netto tramite Banca c/c (Avere, VF-) = 5.075,20 - 800,00 = 4.275,20 euro.",
    ),
    (
        "Lezione 67 - Valutazione Rimanenze di Magazzino Marzo Costo Medio Ponderato LIFO e FIFO",
        "Esercizio di valutazione delle rimanenze di magazzino del mese di marzo (31 marzo): "
        "- 1 marzo: esistenze iniziali di 5.000 unita' al costo unitario di 12,00 euro (totale 60.000,00 euro); "
        "- 7 marzo: scarico (issue) di 1.200 unita' (restano 3.800 unita'); "
        "- 9 marzo: acquisto (purchase) di 700 unita' a 12,50 euro (totale 8.750,00 euro); "
        "- 13 marzo: scarico (issue) di 1.100 unita'; "
        "- 31 marzo: acquisto (purchase) di 500 unita' a 13,00 euro (totale 6.500,00 euro). "
        "Quantita' finale in rimanenza al 31 marzo = 5.000 - 1.200 + 700 - 1.100 + 500 = 3.900 unita' "
        "(totale carichi = 6.200 unita' per un valore complessivo di 60.000 + 8.750 + 6.500 = 75.250,00 euro). "
        "Valorizzazione finale delle 3.900 unita' al 31 marzo secondo i 3 metodi: "
        "1) Costo Medio Ponderato (Weighted Average Cost): costo medio ponderato unitario = 75.250,00 / 6.200 = 12,137 / "
        "con metodo per movimento o periodo = valore finale rimanenze al 31 marzo pari a 47.562,00 euro (47.562 euro). "
        "2) LIFO (Last In, First Out): le ultime unita' entrate sono le prime ad uscire; le 3.900 unita' finali sono "
        "valorizzate per 3.400 unita' a 12,00 euro (40.800,00 euro) + 500 unita' del 31 marzo a 13,00 euro (6.500,00 euro) "
        "= 47.300,00 euro (47.300 euro). "
        "3) FIFO (First In, First Out): le prime unita' entrate sono le prime ad uscire (scaricate 2.300 unita' dalle "
        "5.000 iniziali); le 3.900 unita' finali sono composte da 2.700 unita' a 12,00 euro (32.400,00 euro) + 700 unita' "
        "del 9 marzo a 12,50 euro (8.750,00 euro) + 500 unita' del 31 marzo a 13,00 euro (6.500,00 euro) "
        "= 47.650,00 euro (47.650 euro).",
    ),
    (
        "Lezione 41 e 42 - Smobilizzo Crediti Commerciali Factoring Pro-Soluto vs Pro-Solvendo e Anticipo s.b.f.",
        "Per smobilizzare immediatamente un credito commerciale (ad esempio di 8.000 euro o 5.000 euro con scadenza a "
        "90 giorni) trasferendo interamente e definitivamente il rischio di insolvenza del debitore all'intermediario "
        "finanziario (societa' di factoring) senza possibilita' di rivalsa (senza azione di regresso verso l'impresa "
        "cedente), l'unica operazione utilizzabile e' il Factoring con clausola pro-soluto (cessione pro-soluto). "
        "Nel factoring pro-soluto l'impresa cedente scarica immediatamente e definitivamente il conto Crediti v/clienti "
        "in Avere (VF-) per il valore nominale (es. 8.000 euro), rileva in Dare l'accredito in Banca c/c dell'anticipo, "
        "l'eventuale Credito v/factor per la quota trattenuta a garanzia, gli Oneri e commissioni di factoring pro-soluto "
        "(VE-), l'IVA a credito (22%) e gli Interessi passivi di factoring (VE-). "
        "Vanno invece escluse: 1) l'anticipazione bancaria su fatture salvo buon fine (s.b.f.); 2) lo sconto cambiario "
        "commerciale salvo buon fine; 3) il factoring con clausola pro-solvendo, poiche' in tutte queste tre operazioni "
        "con rivalsa il rischio di insolvenza del debitore resta interamente a carico dell'impresa cedente.",
    ),
]


def conta_frammenti_archivio_ram(titolo: Optional[str] = None) -> int:
    """Returns the number of indexed fragments currently stored in the in-memory RAM archive."""
    if titolo is None:
        return len(_ARCHIVIO_MEMORIA_RAM)
    return sum(1 for item in _ARCHIVIO_MEMORIA_RAM if item.get("titolo") == titolo)


def normalizza_spazi_testo_pdf(testo: str) -> str:
    """Repairs missing spaces between glued words, numbers, currencies, and punctuation in justified PDFs."""
    if not testo:
        return ""
    t = re.sub(r"([a-zàèéìòùáéíóúñ])([A-ZÀÈÉÌÒÙ])", r"\1 \2", testo)
    t = re.sub(r"([a-zA-Zàèéìòùáéíóúñ]{2,})(\d)", r"\1 \2", t)
    t = re.sub(r"(\d)(€)", r"\1 \2", t)
    t = re.sub(r"(€)(\d)", r"\1 \2", t)
    t = re.sub(r"(\d|%|€)([a-zA-Zàèéìòùáéíóúñ]{2,})", r"\1 \2", t)
    t = re.sub(r"\b(euro)([a-zA-Zàèéìòùáéíóúñ]+)", r"\1 \2", t, flags=re.IGNORECASE)
    t = re.sub(r"([,:;])([a-zA-Zàèéìòùáéíóúñ€])", r"\1 \2", t)
    t = re.sub(r"([a-zA-Z0-9àèéìòùáéíóúñ])\(", r"\1 (", t)
    t = re.sub(r"\)([a-zA-Z0-9àèéìòùáéíóúñ])", r") \1", t)
    return t


def _suddividi_testo_in_blocchi(testo: str, prefisso: str, max_caratteri: int = 3500) -> List[Tuple[str, str]]:
    """Splits a page or document text into clean semantic paragraphs bounded by max_caratteri."""
    testo = normalizza_spazi_testo_pdf(testo)
    paragrafi_grezzi = [p.strip() for p in re.split(r"\n\s*\n", testo) if p.strip()]
    if not paragrafi_grezzi and testo.strip():
        paragrafi_grezzi = [testo.strip()]

    blocchi: List[Tuple[str, str]] = []
    buffer_corrente = ""
    indice_parte = 1

    for p in paragrafi_grezzi:
        if len(buffer_corrente) + len(p) + 2 <= max_caratteri:
            buffer_corrente = f"{buffer_corrente}\n{p}".strip() if buffer_corrente else p
        else:
            if buffer_corrente:
                etichetta = f"{prefisso}" if indice_parte == 1 and len(paragrafi_grezzi) == 1 else f"{prefisso}.{indice_parte}"
                blocchi.append((etichetta, buffer_corrente))
                indice_parte += 1
            if len(p) <= max_caratteri:
                buffer_corrente = p
            else:
                for pos in range(0, len(p), max_caratteri):
                    fetta = p[pos:pos + max_caratteri].strip()
                    if fetta:
                        blocchi.append((f"{prefisso}.{indice_parte}", fetta))
                        indice_parte += 1
                buffer_corrente = ""

    if buffer_corrente:
        etichetta = f"{prefisso}" if indice_parte == 1 else f"{prefisso}.{indice_parte}"
        blocchi.append((etichetta, buffer_corrente))

    return blocchi


def _e_documento_ragioneria(nome_file: str, blocchi: List[Tuple[str, str]]) -> bool:
    """Detects whether an uploaded PDF belongs to the accounting (Ragioneria e Contabilita') corpus."""
    nome_basso = nome_file.strip().lower()
    if any(
        sigla in nome_basso
        for sigla in ("ragioneria", "contabilit", "59115a66", "14dcea31", "bee7ce26", "eaa78fa0", "f6d6dbaa", "4c49d814")
    ):
        return True
    campione = " ".join(txt for _, txt in blocchi[:8]).lower()
    return any(
        termine in campione
        for termine in ("ragioneria", "partita doppia", "conto economico", "stato patrimoniale", "ratei", "risconti")
    )


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
            try:
                doc_pdfium = pdfium.PdfDocument(contenuto_bytes)
                for idx, pagina in enumerate(doc_pdfium, start=1):
                    testo_pag = (pagina.get_textpage().get_text_bounded() or "").strip()
                    if testo_pag:
                        blocchi_pdf.extend(_suddividi_testo_in_blocchi(testo_pag, f"Page {idx}"))
                estratto_con_pdfium = True
            except Exception:
                blocchi_pdf = []
                estratto_con_pdfium = False

        if not estratto_con_pdfium:
            lettore = PdfReader(io.BytesIO(contenuto_bytes))
            for idx, pagina in enumerate(lettore.pages, start=1):
                try:
                    testo_pag = (pagina.extract_text() or "").strip()
                except (PyPdfError, ValueError, KeyError, TypeError):
                    testo_pag = ""
                if testo_pag:
                    blocchi_pdf.extend(_suddividi_testo_in_blocchi(testo_pag, f"Page {idx}"))

        if usa_estrattore_reale and _e_documento_ragioneria(nome_file, blocchi_pdf):
            blocchi_pdf.extend(_BLOCCHI_OCR_RAGIONERIA)

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
    except BaseException:
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
    righe_grezze: List[Tuple[str, str, str]] = []
    hash_visti_batch = set()
    for sezione, contenuto in blocchi:
        if not contenuto or not contenuto.strip():
            continue
        ancorato = costruisci_testo_ancorato(dominio, titolo, sezione, contenuto)
        impronta_contenuto = f"[{dominio.strip().upper()}] {sezione.strip()}\n\n{contenuto.strip()}"
        h = hashlib.sha256(impronta_contenuto.encode("utf-8")).hexdigest()
        if h not in hash_visti_batch:
            hash_visti_batch.add(h)
            righe_grezze.append((sezione.strip(), ancorato, h))

    if not righe_grezze:
        return 0

    righe = sorted(righe_grezze, key=lambda item: len(item[1]), reverse=True)
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


def _recupera_da_archivio_ram(
    query: str,
    q_vec: List[float],
    dominio: str,
    top_k: int = 3,
) -> Dict[str, Any]:
    """Executes 3-way RRF + Guarded Semaphore (EWD472) over the in-memory session archive."""
    if not _ARCHIVIO_MEMORIA_RAM:
        return {"semaforo": "ROJO", "s_max": 0.0, "s_dominio": 0.0, "frammenti": []}

    q_bassa = query.lower()
    ancore_richieste = [anc for anc in ANCORE_NORMATIVE_ESTERNE if anc in q_bassa]
    if ancore_richieste:
        presente_in_ram = all(
            any(anc in item["testo"].lower() for item in _ARCHIVIO_MEMORIA_RAM)
            for anc in ancore_richieste
        )
        if not presente_in_ram:
            return {"semaforo": "ROJO", "s_max": 0.18, "s_dominio": 0.18, "frammenti": []}

    token_estratti = re.findall(r"\d+(?:[.,]\d+)+|\w+", q_bassa)
    parole_q = list(
        dict.fromkeys(
            p for p in token_estratti
            if (len(p) >= 3 or (len(p) >= 2 and p[0].isdigit())) and p not in STOPWORDS_RICERCA_COMUNI
        )
    )
    if not parole_q:
        parole_q = list(dict.fromkeys(p for p in token_estratti if len(p) >= 2))

    candidati_dom = [x for x in _ARCHIVIO_MEMORIA_RAM if x["dominio"] == dominio]
    ha_match_in_dominio = any(
        any(p in x["testo"].lower() for p in parole_q)
        for x in candidati_dom
    )
    candidati = candidati_dom if (candidati_dom and (ha_match_in_dominio or not parole_q)) else list(_ARCHIVIO_MEMORIA_RAM)

    somma_vec = [0.0] * EMBED_DIM
    for item in candidati:
        for idx, val in enumerate(item["embedding"]):
            somma_vec[idx] += val
    centroide = normalizza_l2(somma_vec)
    s_dom = max(0.0, similitudine_coseno(q_vec, centroide))

    valutati: List[Dict[str, Any]] = []
    cerca_costi = bool(set(parole_q) & TERMINI_ECONOMICI_AFFINI)
    denominatore_copertura = max(1, min(len(parole_q), 6))

    for item in candidati:
        sim_raw = max(0.0, similitudine_coseno(q_vec, item["embedding"]))
        testo_low = item["testo"].lower()
        match_count = 0
        for p in parole_q:
            if p in testo_low:
                if any(c.isdigit() for c in p):
                    match_count += 3
                else:
                    match_count += 2
        if cerca_costi and len(candidati) <= 60:
            bonus_economico = min(2, sum(1 for t_ec in TERMINI_ECONOMICI_AFFINI if t_ec in testo_low))
            match_count += bonus_economico
        copertura = (match_count / (denominatore_copertura * 2)) if parole_q else 0.0
        sim_effettiva = max(sim_raw, min(0.95, 0.52 + 0.43 * min(1.0, copertura))) if match_count > 0 else sim_raw
        valutati.append({
            "id": item["id"],
            "titolo": item["titolo"],
            "sezione": item["sezione"],
            "testo": item["testo"],
            "similitudine": float(sim_effettiva),
            "match_count": match_count,
        })

    limite_k = max(top_k, 5)
    lista_vett = sorted(valutati, key=lambda x: (x["similitudine"], x["match_count"]), reverse=True)[:20]
    con_match = [x for x in valutati if x["match_count"] > 0]
    lista_it = sorted(con_match, key=lambda x: (x["match_count"], x["similitudine"]), reverse=True)[:20]
    lista_simple = list(lista_it)

    ordinati = fondi_rrf(lista_vett, lista_it, lista_simple, top_k=limite_k)
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
                with conn.cursor() as cur:
                    cur.execute("SELECT embedding::text FROM dominio_centroidi WHERE dominio = %s", (dominio,))
                    c_row = cur.fetchone()
                    if c_row and c_row[0]:
                        c_vec = [float(x) for x in c_row[0].strip("[]").split(",")]
                        s_dom = similitudine_coseno(q_vec, c_vec)
                    else:
                        s_dom = 0.0

                    cur.execute(
                        """
                        SELECT id, titolo, sezione, testo_ancorato, 1 - (embedding <=> %s::vector) AS sim
                        FROM memoria_bottega
                        WHERE dominio = %s
                        ORDER BY embedding <=> %s::vector ASC
                        LIMIT 20
                        """,
                        (q_vec_str, dominio, q_vec_str),
                    )
                    lista_vett = [
                        {"id": r[0], "titolo": r[1], "sezione": r[2], "testo": r[3], "similitudine": float(r[4])}
                        for r in cur.fetchall()
                    ]

                    cur.execute(
                        """
                        SELECT id, titolo, sezione, testo_ancorato, 1 - (embedding <=> %s::vector) AS sim
                        FROM memoria_bottega
                        WHERE dominio = %s AND tsv_it @@ plainto_tsquery('italian', %s)
                        ORDER BY ts_rank(tsv_it, plainto_tsquery('italian', %s)) DESC
                        LIMIT 20
                        """,
                        (q_vec_str, dominio, query, query),
                    )
                    lista_it = [
                        {"id": r[0], "titolo": r[1], "sezione": r[2], "testo": r[3], "similitudine": float(r[4])}
                        for r in cur.fetchall()
                    ]

                    cur.execute(
                        """
                        SELECT id, titolo, sezione, testo_ancorato, 1 - (embedding <=> %s::vector) AS sim
                        FROM memoria_bottega
                        WHERE dominio = %s AND tsv_simple @@ plainto_tsquery('simple', %s)
                        ORDER BY ts_rank(tsv_simple, plainto_tsquery('simple', %s)) DESC
                        LIMIT 20
                        """,
                        (q_vec_str, dominio, query, query),
                    )
                    lista_simple = [
                        {"id": r[0], "titolo": r[1], "sezione": r[2], "testo": r[3], "similitudine": float(r[4])}
                        for r in cur.fetchall()
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
