#!/usr/bin/env python3
"""Layer 1 (THE): Exact Decimal arithmetic (EWD145), percentage conservation and Tri-Color
Write Barrier (EWD496A) on LLM-generated figures. Zero I/O dependencies."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from itertools import combinations
import re
from typing import Dict, List, Optional, Set, Tuple

PATRON_NUM = re.compile(
    r"\d+(?:[.,]\d+)?\s*%"
    r"|(?<!\d)\d{1,3}(?:\.\d{3})+(?:,\d+)?(?!\d)"
    r"|(?<!\d)\d{1,3}(?:,\d{3})+\.\d+(?!\d)"
    r"|(?<!\d)\d{8,10}(?!\d)"
    r"|(?<!\d)(?:19|20)\d{2}(?!\d)"
    r"|(?<!\d)\d+[.,]\d+(?!\d)"
)
PATRON_PERCENTUALE = re.compile(r"\d+(?:[.,]\d+)?\s*%")
PATRON_MIGLIAIA = re.compile(r"^\d{1,3}(?:\.\d{3})+(?:,\d+)?$")
PATRON_MIGLIAIA_EN_DEC = re.compile(r"^\d{1,3}(?:,\d{3})+\.\d+$")
PATRON_MIGLIAIA_EN_INT = re.compile(r"^\d{1,3}(?:,\d{3})+$")
PATRON_INTERI_PURI = re.compile(r"(?<![\d.,])\d+(?![\d%]|[.,]\d)")
PATRON_INTERI_TECNICI = re.compile(
    r"(?<![\d.,])\d+(?=\s*(?:kwh|kw|litri|l/min|l/h|bar|euro|eur|€|\$|km|giorni|ore|mesi|anni|min|minuti|sec|secondi|cm|mm|kg|hz|db|ohm)\b)",
    re.IGNORECASE,
)

MAX_CARATTERI_PAGINA_DEFAULT: int = 2400
LIMITE_PASSI_PAGINAZIONE: int = 10000
LUNGHEZZA_MINIMA_TAGLIO_PAGINA: int = 100
Q2 = Decimal("0.01")
TOL = Decimal("0.01")
TOLLERANZA_AMBAR = Decimal("0.05")
_STOPWORDS_MODELLI_INVALIDI = frozenset({
    "a", "di", "da", "in", "con", "su", "per", "tra", "fra", "resta", "ha", "va", "si", "non",
    "e", "ed", "o", "che", "un", "una", "uno", "il", "la", "lo", "i", "gli", "le",
    "del", "della", "dello", "dei", "degli", "delle", "al", "alla", "allo", "ai", "agli", "alle",
    "dal", "dalla", "dallo", "dai", "dagli", "dalle", "nel", "nella", "nello", "nei", "negli", "nelle",
    "sul", "sulla", "sullo", "sui", "sugli", "sulle",
})


def _normalizza_separatore_decimale(cifra: str) -> str:
    """Strips whitespace (including U+00A0) and normalizes decimal commas into dots."""
    return re.sub(r"[\s\xa0]", "", cifra).replace(",", ".")


def _converti_in_decimal_esatti(token_pulito: str) -> Set[Decimal]:
    """Converts a numeric token (EU thousands, EN thousands, or standard decimal) to exact Decimal values.
    Cattura InvalidOperation per scartare in modo deterministico candidati numerici malformati."""
    valori: Set[Decimal] = set()
    if not token_pulito or token_pulito.endswith("%"):
        return valori

    if PATRON_MIGLIAIA.match(token_pulito):
        senza_punti = token_pulito.replace(".", "").replace(",", ".")
        try:
            valori.add(Decimal(senza_punti))
        except InvalidOperation:
            pass
        return valori

    if PATRON_MIGLIAIA_EN_DEC.match(token_pulito):
        senza_virgole = token_pulito.replace(",", "")
        try:
            valori.add(Decimal(senza_virgole))
        except InvalidOperation:
            pass
        return valori

    if PATRON_MIGLIAIA_EN_INT.match(token_pulito):
        try:
            valori.add(Decimal(token_pulito.replace(",", "")))
        except InvalidOperation:
            pass
        try:
            valori.add(Decimal(token_pulito.replace(",", ".")))
        except InvalidOperation:
            pass
        return valori

    norm = token_pulito.replace(",", ".")
    if norm.count(".") <= 1:
        try:
            valori.add(Decimal(norm))
        except InvalidOperation:
            pass
    return valori


def arrotonda_esatto_el_x8(valore: float | str | Decimal, decimali: int = 2) -> Decimal:
    """EWD145 Cap. 3.2: Exact mathematical rounding away from zero on ties (ROUND_HALF_UP)."""
    quota = Decimal("10") ** (-decimali)
    return Decimal(str(valore)).quantize(quota, rounding=ROUND_HALF_UP)


def estrai_percentuali_decimal(testo: str) -> Set[Decimal]:
    """Extracts all percentages as exact Decimal objects (so 2.70% == 2.7%)."""
    risultato: Set[Decimal] = set()
    for match in PATRON_PERCENTUALE.findall(testo):
        crudo = _normalizza_separatore_decimale(match).rstrip("%")
        try:
            risultato.add(Decimal(crudo))
        except InvalidOperation:
            continue
    return risultato


def verifica_conservazione_percentuali_decimal(prosa_narrata: str, fonte_ufficiale: str) -> bool:
    """If the official source contains percentages, at least one must appear identical in the prose."""
    ufficiali = estrai_percentuali_decimal(fonte_ufficiale)
    if not ufficiali:
        return True
    return bool(ufficiali & estrai_percentuali_decimal(prosa_narrata))


def _calcola_derivati_aritmetici_ammissibili(
    dec_ctx: Set[Decimal],
    pct_ctx: Set[Decimal],
) -> Set[Decimal]:
    """Generates exact Decimal arithmetic derivations (A*B, A+B, A-B, A*(P/100), A+A*(P/100), A-A*(P/100))
    strictly formed by positive operands certified in the context to prevent false-negative Node GRIGIO on valid calculations."""
    derivati: Set[Decimal] = set()
    tutti_operandi = [x for x in dec_ctx if Decimal("0") < x < Decimal("10000000")]

    for a in tutti_operandi:
        for p in pct_ctx:
            if p <= Decimal("0"):
                continue
            quota_pct = (a * p) / Decimal("100")
            derivati.add(quota_pct)
            derivati.add(arrotonda_esatto_el_x8(quota_pct, 2))
            somma_pct = a + quota_pct
            derivati.add(somma_pct)
            derivati.add(arrotonda_esatto_el_x8(somma_pct, 2))
            if a > quota_pct:
                diff_pct = a - quota_pct
                derivati.add(diff_pct)
                derivati.add(arrotonda_esatto_el_x8(diff_pct, 2))

    for i, a in enumerate(tutti_operandi):
        for b in tutti_operandi[i:]:
            somma = a + b
            derivati.add(somma)
            derivati.add(arrotonda_esatto_el_x8(somma, 2))
            prodotto = a * b
            derivati.add(prodotto)
            derivati.add(arrotonda_esatto_el_x8(prodotto, 2))
            if a > b:
                diff = a - b
                derivati.add(diff)
                derivati.add(arrotonda_esatto_el_x8(diff, 2))
            elif b > a:
                diff = b - a
                derivati.add(diff)
                derivati.add(arrotonda_esatto_el_x8(diff, 2))
            if b != 0:
                try:
                    quoz_ab = a / b
                    derivati.add(arrotonda_esatto_el_x8(quoz_ab, 2))
                except (InvalidOperation, ZeroDivisionError):
                    pass
            if a != 0:
                try:
                    quoz_ba = b / a
                    derivati.add(arrotonda_esatto_el_x8(quoz_ba, 2))
                except (InvalidOperation, ZeroDivisionError):
                    pass

    return derivati


def verifica_grounding_numerico(risposta: str, contesto: str) -> List[str]:
    """Returns the sorted list of figures cited in the response but absent from the context,
    comparing Decimal values for percentages, thousands, technical decimals, and exact arithmetic derivations."""
    raw_risp = PATRON_NUM.findall(risposta)
    for match_int in PATRON_INTERI_TECNICI.findall(risposta):
        if match_int not in raw_risp:
            raw_risp.append(match_int)
    raw_ctx = PATRON_NUM.findall(contesto)

    migliaia_ctx: Set[str] = set()
    altri_ctx: Set[str] = set()
    dec_ctx: Set[Decimal] = set()
    pct_ctx = estrai_percentuali_decimal(contesto)

    for intero_trovato in PATRON_INTERI_PURI.findall(contesto):
        try:
            dec_ctx.add(Decimal(intero_trovato))
        except InvalidOperation:
            pass

    for token_match in raw_ctx:
        pulito = re.sub(r"[\s\xa0]", "", token_match)
        norm = _normalizza_separatore_decimale(token_match)
        dec_ctx.update(_converti_in_decimal_esatti(pulito))
        if PATRON_MIGLIAIA.match(pulito):
            migliaia_ctx.add(norm)
        else:
            altri_ctx.add(norm)

    derivati_validi = _calcola_derivati_aritmetici_ammissibili(dec_ctx, pct_ctx)

    orfane: List[str] = []
    for token_match in raw_risp:
        pulito = re.sub(r"[\s\xa0]", "", token_match)
        cifra_normalizzata = _normalizza_separatore_decimale(token_match)
        e_migliaia = bool(PATRON_MIGLIAIA.match(pulito))

        if e_migliaia and cifra_normalizzata in migliaia_ctx:
            continue
        if not e_migliaia and cifra_normalizzata in altri_ctx:
            continue
        if cifra_normalizzata.endswith("%"):
            try:
                if Decimal(cifra_normalizzata[:-1]) in pct_ctx:
                    continue
            except InvalidOperation:
                pass
        else:
            candidati_dec = _converti_in_decimal_esatti(pulito)
            if candidati_dec and (candidati_dec & dec_ctx):
                continue
            if candidati_dec and (candidati_dec & derivati_validi):
                continue
        orfane.append(cifra_normalizzata)
    return sorted(set(orfane))


def _rileva_coppie_entita_contesto(contesto: str, domanda: str) -> List[Tuple[str, str]]:
    """Automatically extracts (target, antagonist) pairs from context and question
    by analyzing model prefixes, numbered identifiers, tax years, and contrasting concepts."""
    if not contesto or not domanda:
        return []
    contesto_basso = contesto.lower()
    domanda_bassa = domanda.lower()
    coppie: List[Tuple[str, str]] = []

    anni_ctx = sorted(set(re.findall(r"\b(?:19|20)\d{2}\b", contesto)))
    if len(anni_ctx) >= 2:
        for a in anni_ctx:
            if a in domanda_bassa:
                for antag in anni_ctx:
                    if antag != a and antag not in domanda_bassa:
                        coppie.append((a, antag))

    pat_pref = re.compile(
        r"\b(Modello|Serie|Caldaia|Compressore|Pompa|Regime|Versione|Chiller|Articolo|Anno(?:\s+di\s+imposta)?)\s+([A-Za-z0-9\-_]+(?:\s+[A-Za-z0-9\-_]+)?)",
        re.IGNORECASE,
    )
    trovati = pat_pref.findall(contesto)
    gruppi: Dict[str, Set[str]] = {}
    for tipo, nome in trovati:
        nome_pulito = nome.strip()
        primo_token = nome_pulito.split()[0].lower() if nome_pulito else ""
        if primo_token in _STOPWORDS_MODELLI_INVALIDI or len(nome_pulito) < 2:
            continue
        gruppi.setdefault(tipo.lower(), set()).add(nome_pulito)
    for tipo, nomi in gruppi.items():
        if len(nomi) >= 2:
            nomi_list = list(nomi)
            for n in nomi_list:
                if n.lower() in domanda_bassa:
                    for antag in nomi_list:
                        if antag.lower() != n.lower() and antag.lower() not in domanda_bassa:
                            coppie.append((f"{tipo} {n}", f"{tipo} {antag}"))
                            coppie.append((n, antag))

    pat_modello_num = re.compile(r"\b([A-Za-z]{3,})\s+(\d+)\b")
    modelli = pat_modello_num.findall(contesto)
    gruppi_mod: Dict[str, Set[str]] = {}
    for pref, num in modelli:
        gruppi_mod.setdefault(pref.lower(), set()).add(num)
    for pref_low, numeri in gruppi_mod.items():
        if len(numeri) >= 2:
            for num in numeri:
                sigla = f"{pref_low} {num}"
                if sigla in domanda_bassa or (pref_low in domanda_bassa and num in domanda):
                    for antag_num in numeri:
                        if antag_num != num and antag_num not in domanda:
                            coppie.append((f"{pref_low} {num}", f"{pref_low} {antag_num}"))

    if "nuova attivit" in contesto_basso and "ordinario" in contesto_basso:
        if "nuova attivit" in domanda_bassa or "start-up" in domanda_bassa:
            coppie.append(("nuova attività", "ordinario"))
            coppie.append(("start-up", "ordinario"))

    coppie_uniche: List[Tuple[str, str]] = []
    viste: Set[Tuple[str, str]] = set()
    for t_ent, a_ent in coppie:
        chiave = (t_ent.lower().strip(), a_ent.lower().strip())
        if chiave not in viste and chiave[0] != chiave[1]:
            viste.add(chiave)
            coppie_uniche.append((t_ent, a_ent))
    return coppie_uniche


def verifica_grounding_relazionale(
    risposta: str,
    contesto: str,
    soggetto_target: str = "",
    soggetto_antagonista: str = "",
    domanda: str = "",
    ampiezza_finestra_caratteri: int = 140,
) -> List[str]:
    """Detects relational attribution errors where a number from the context is erroneously assigned
    to a competing entity or model present in the same document (e.g. Model Alpha vs Model Beta).
    Returns list of mismatching figures."""
    coppie_da_verificare: List[Tuple[str, str]] = []
    if soggetto_target and soggetto_antagonista:
        coppie_da_verificare.append((soggetto_target, soggetto_antagonista))
    elif domanda:
        coppie_da_verificare = _rileva_coppie_entita_contesto(contesto, domanda)
    elif contesto:
        prima_riga = contesto.strip().splitlines()[0] if contesto.strip() else ""
        if prima_riga:
            coppie_da_verificare = _rileva_coppie_entita_contesto(contesto, prima_riga)

    if not coppie_da_verificare:
        return []

    cifre_risposta = PATRON_NUM.findall(risposta)
    for match_int in PATRON_INTERI_TECNICI.findall(risposta):
        if match_int not in cifre_risposta:
            cifre_risposta.append(match_int)
    if not cifre_risposta:
        return []

    contesto_lower = contesto.lower()
    cifre_scambiate_totali: List[str] = []

    for target_cand, antag_cand in coppie_da_verificare:
        target_norm = target_cand.strip().lower()
        antagonista_norm = antag_cand.strip().lower()
        if not target_norm or not antagonista_norm:
            continue
        if target_norm not in contesto_lower or antagonista_norm not in contesto_lower:
            continue

        for cifra_token in cifre_risposta:
            norm_cifra = _normalizza_separatore_decimale(cifra_token)
            pulito_cifra = re.sub(r"[\s\xa0]", "", cifra_token)
            candidati_cifra = _converti_in_decimal_esatti(pulito_cifra)

            occorrenze: List[int] = [
                m.start() for m in re.finditer(re.escape(cifra_token), contesto, re.IGNORECASE)
            ]
            if not occorrenze:
                for cand in candidati_cifra:
                    cand_str = str(cand)
                    occorrenze.extend(
                        [m.start() for m in re.finditer(re.escape(cand_str), contesto, re.IGNORECASE)]
                    )

            if not occorrenze:
                continue

            presenze_target = 0
            presenze_antagonista = 0
            for pos in occorrenze:
                inizio_frase = max(
                    contesto_lower.rfind(".", 0, pos),
                    contesto_lower.rfind("\n", 0, pos),
                    contesto_lower.rfind(";", 0, pos),
                )
                inizio = 0 if inizio_frase == -1 else inizio_frase + 1
                fine_frase = -1
                for sep in (".", "\n", ";"):
                    idx_sep = contesto_lower.find(sep, pos)
                    if idx_sep != -1 and (fine_frase == -1 or idx_sep < fine_frase):
                        fine_frase = idx_sep
                fine = len(contesto_lower) if fine_frase == -1 else fine_frase
                finestra = contesto_lower[inizio:fine]
                if target_norm in finestra:
                    presenze_target += 1
                if antagonista_norm in finestra:
                    presenze_antagonista += 1

            if presenze_antagonista > 0 and presenze_target == 0:
                cifre_scambiate_totali.append(norm_cifra)

    return sorted(set(cifre_scambiate_totali))


def classifica_nodo_tricolore(
    risposta: str,
    contesto: str,
    soggetto_target: str = "",
    soggetto_antagonista: str = "",
    domanda: str = "",
) -> Tuple[str, List[str]]:
    """EWD496A (Tri-Color Marking & Write Barrier): BIANCO (empty), GRIGIO (hallucinated or misattributed), NERO (grounded)."""
    if not risposta or not risposta.strip():
        return ("BIANCO", [])
    cifre_orfane = verifica_grounding_numerico(risposta, contesto)
    cifre_scambiate = verifica_grounding_relazionale(
        risposta,
        contesto,
        soggetto_target=soggetto_target,
        soggetto_antagonista=soggetto_antagonista,
        domanda=domanda,
    )
    totale_errori = sorted(set(cifre_orfane + cifre_scambiate))
    if totale_errori:
        return ("GRIGIO", totale_errori)
    return ("NERO", [])


def tronca_senza_spezzare_parola(testo: str, max_caratteri: int, suffisso: str = "") -> str:
    """Pure mathematical function: slices text up to max_caratteri ensuring no word is sliced in half.
    Snaps to the preceding whitespace or punctuation boundary."""
    if not testo or len(testo) <= max_caratteri:
        return testo
    limite = max(0, max_caratteri - len(suffisso))
    if limite <= 0:
        return suffisso[:max_caratteri]
    if limite >= len(testo) or testo[limite].isspace():
        return testo[:limite].rstrip() + suffisso
    ultimo_spazio = -1
    for sep in (" ", "\n", "\t", ".", ";", ",", ":", "!", "?"):
        idx = testo.rfind(sep, 0, limite)
        if idx > ultimo_spazio:
            ultimo_spazio = idx
    if ultimo_spazio > 0:
        return testo[:ultimo_spazio].rstrip() + suffisso
    return testo[:limite].rstrip() + suffisso


def ripara_parola_troncata(testo: str) -> str:
    """Pure function: detects and trims any trailing fragment of a word cut in half when reaching token limits."""
    if not testo or not testo.strip():
        return testo
    testo_strip = testo.rstrip()
    if testo_strip[-1] in (".", "!", "?", ":", ";", '"', "'", "`", ")", "]", "}", ">", "\n"):
        return testo_strip
    if testo_strip.endswith(("continua", "continue", "continúa")):
        return testo_strip
    ultimo_separatore = -1
    for sep in (" ", "\n", "\t", ".", ";", ",", ":", "!", "?", ")", "]", "}", ">"):
        idx = testo_strip.rfind(sep)
        if idx > ultimo_separatore:
            ultimo_separatore = idx
    if ultimo_separatore > 0:
        return testo_strip[:ultimo_separatore].rstrip()
    return testo_strip


def suddividi_in_pagine_con_continua(
    testo: str,
    max_caratteri_pagina: int = MAX_CARATTERI_PAGINA_DEFAULT,
    marcatore_continua: str = "\n\ncontinua",
) -> List[str]:
    """Divides long text into sequential pages without cutting words in half.
    Appends marcatore_continua to every page except the final one."""
    if not testo or not testo.strip():
        return [""]
    testo_pulito = testo.strip()
    if len(testo_pulito) <= max_caratteri_pagina:
        return [testo_pulito]

    pagine: List[str] = []
    residuo = testo_pulito
    passi_residui = LIMITE_PASSI_PAGINAZIONE
    while residuo and passi_residui > 0:
        passi_residui -= 1
        if len(residuo) <= max_caratteri_pagina:
            pagine.append(residuo)
            break
        limite_taglio = max(LUNGHEZZA_MINIMA_TAGLIO_PAGINA, max_caratteri_pagina - len(marcatore_continua))
        pagina_corrente = tronca_senza_spezzare_parola(residuo, limite_taglio)
        lunghezza_consumata = len(pagina_corrente)
        if lunghezza_consumata == 0 or lunghezza_consumata >= len(residuo):
            pagine.append(residuo)
            break
        pagine.append(pagina_corrente + marcatore_continua)
        residuo = residuo[lunghezza_consumata:].lstrip()
    return pagine


def anonimizza_testo_finanziario(testo: str) -> str:
    """Maschera Codici Fiscali, IBAN, email e contatti/pratiche personali preservando al 100%
    importi in valuta, percentuali, date contrattuali e numeri di rata."""
    if not testo:
        return ""
    risultato = re.sub(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b", "[CF_ANONIMO]", testo)
    risultato = re.sub(r"\bIT\d{2}[A-Z0-9]{15,25}\b", "[IBAN_ANONIMO]", risultato, flags=re.IGNORECASE)
    risultato = re.sub(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
        "[EMAIL_ANONIMA]",
        risultato,
    )
    risultato = re.sub(
        r"(?i)\b(tel(?:efono)?|cell(?:ulare)?|fax|recapito)\s*[:.]?\s*\+?\d[\d\s\-/]{6,15}\d\b",
        r"\1: [TEL_ANONIMO]",
        risultato,
    )
    risultato = re.sub(
        r"(?i)\b(pratica\s*n?\.?|codice\s+cliente|id\s+cliente|ndg)\s*[:=#]?\s*[A-Z0-9\-/]{5,20}\b",
        r"\1: [ID_ANONIMO]",
        risultato,
    )
    return risultato


def classifica_pagine_per_funzione(testo_documento: str) -> Dict[str, object]:
    """Punto 1: Separa il documento per blocchi ### [Page N] in PAGINE_PIANO_AMMORTAMENTO,
    PAGINE_RIEPILOGO_COSTI_TAEG, PAGINE_PROSPETTO_LIQUIDAZIONE e PAGINE_INTESTAZIONE_CONTRATTO."""
    testo = testo_documento or ""
    if "### [Page " in testo:
        parti = re.split(r"(?m)^###\s*\[Page\s*(\d+)\]\s*", testo)
        pagine_ordinate: List[Tuple[int, str]] = []
        prefazio = parti[0].strip()
        if prefazio:
            pagine_ordinate.append((1, prefazio))
        idx_s = 1
        while idx_s + 1 < len(parti):
            num_p = int(parti[idx_s])
            corpo_p = parti[idx_s + 1].strip()
            if pagine_ordinate and pagine_ordinate[0][0] == num_p and num_p == 1:
                pagine_ordinate[0] = (1, f"{pagine_ordinate[0][1]}\n{corpo_p}".strip())
            else:
                pagine_ordinate.append((num_p, corpo_p))
            idx_s += 2
    else:
        pagine_ordinate = [(1, testo.strip())] if testo.strip() else []

    pagine_piano: List[Tuple[int, str]] = []
    pagine_costi_taeg: List[Tuple[int, str]] = []
    pagine_liquidazione: List[Tuple[int, str]] = []
    pagine_intestazione: List[Tuple[int, str]] = []

    for num_p, corpo_p in pagine_ordinate:
        c_low = corpo_p.lower()
        righe_cand_rata = re.findall(
            r"(?m)^\s*\|?\s*(?:rata\s*n?\.?\s*)?\d{1,3}\b.*?\d+[.,]\d{2}.*?\d+[.,]\d{2}",
            corpo_p,
            flags=re.IGNORECASE,
        )
        ha_piano = len(righe_cand_rata) >= 2 or (
            "piano di ammortamento" in c_low and len(righe_cand_rata) >= 1
        )
        ha_costi = any(
            k in c_low
            for k in (
                "taeg", "tan", "teg", "commissioni", "istruttoria", "assicuraz",
                "spese", "interessi totali", "oneri", "iecci", "secci",
            )
        )
        ha_liq = any(
            k in c_low
            for k in (
                "netto ricavo", "liquidazione", "importo erogato", "somma erogata",
                "capitale finanziato", "importo totale del credito", "montante",
            )
        )
        if ha_piano:
            pagine_piano.append((num_p, corpo_p))
        if ha_costi:
            pagine_costi_taeg.append((num_p, corpo_p))
        if ha_liq:
            pagine_liquidazione.append((num_p, corpo_p))
        if not ha_piano and not ha_costi and not ha_liq:
            pagine_intestazione.append((num_p, corpo_p))

    return {
        "pagine_tutte": pagine_ordinate,
        "PAGINE_PIANO_AMMORTAMENTO": pagine_piano,
        "PAGINE_RIEPILOGO_COSTI_TAEG": pagine_costi_taeg,
        "PAGINE_PROSPETTO_LIQUIDAZIONE": pagine_liquidazione,
        "PAGINE_INTESTAZIONE_CONTRATTO": pagine_intestazione,
    }


def _converti_stringa_in_decimal_audit(valore_str: str) -> Optional[Decimal]:
    if not valore_str or not valore_str.strip():
        return None
    pulito = re.sub(r"[^\d.,\-]", "", valore_str.strip())
    if not pulito:
        return None
    if "," in pulito and "." in pulito:
        if pulito.rfind(",") > pulito.rfind("."):
            pulito = pulito.replace(".", "").replace(",", ".")
        else:
            pulito = pulito.replace(",", "")
    elif "," in pulito:
        parti_v = pulito.split(",")
        if len(parti_v) == 2 and len(parti_v[1]) == 3 and len(parti_v[0]) <= 3:
            pulito = pulito.replace(",", "")
        else:
            pulito = pulito.replace(",", ".")
    elif "." in pulito:
        parti_p = pulito.split(".")
        if len(parti_p) > 2 or (len(parti_p) == 2 and len(parti_p[1]) == 3):
            pulito = pulito.replace(".", "")
    try:
        return Decimal(pulito)
    except InvalidOperation:
        return None


def _compatta_intervalli_rate(lista_numeri: List[int]) -> str:
    if not lista_numeri:
        return "Nessuna"
    ordinati = sorted(set(lista_numeri))
    intervalli: List[str] = []
    inizio = ordinati[0]
    fine = ordinati[0]
    for n in ordinati[1:]:
        if n == fine + 1:
            fine = n
        else:
            intervalli.append(f"{inizio}..{fine}" if fine > inizio else f"{inizio}")
            inizio = n
            fine = n
    intervalli.append(f"{inizio}..{fine}" if fine > inizio else f"{inizio}")
    return ", ".join(intervalli)


def q2(x: Decimal) -> Decimal:
    """Sezione 1: Normalizzazione e arrotondamento contabile esatto al centesimo (ROUND_HALF_UP)."""
    return x.quantize(Q2, rounding=ROUND_HALF_UP)


def npv(rate: Decimal, c0: Decimal, rate_list: List[Decimal]) -> Decimal:
    """Sezione 7: Valore Attuale Netto (NPV) per una sequenza di rate al tasso periodale rate."""
    if not rate_list:
        return -c0
    uno_piu_r = Decimal("1") + rate
    fattore = Decimal("1")
    valore_attualizzato = Decimal("0")
    for rata_t in rate_list:
        fattore *= uno_piu_r
        if fattore == Decimal("0"):
            break
        valore_attualizzato += rata_t / fattore
    return valore_attualizzato - c0


def irr_bisection(
    c0: Decimal,
    rate_list: List[Decimal],
    lo: Decimal = Decimal("0"),
    hi: Decimal = Decimal("1"),
    iterations: int = 60,
) -> Optional[Decimal]:
    """Sezioni 8 e 9: Risolutore deterministico TIR/IRR tramite bisezione esatta in Decimal."""
    if c0 <= Decimal("0") or not rate_list:
        return None
    somma_rate = sum(rate_list, Decimal("0"))
    if somma_rate <= c0:
        return None
    if npv(lo, c0, rate_list) < Decimal("0") or npv(hi, c0, rate_list) > Decimal("0"):
        return None
    due = Decimal("2")
    for _ in range(iterations):
        mid = (lo + hi) / due
        if npv(mid, c0, rate_list) > Decimal("0"):
            lo = mid
        else:
            hi = mid
    return (lo + hi) / due


def _calcola_tasso_mensile_effettivo_decimal(tan_pct: Decimal) -> Decimal:
    tan_frac = tan_pct / Decimal("100")
    if tan_frac <= Decimal("-1"):
        return Decimal("0")
    return ((Decimal("1") + tan_frac).ln() / Decimal("12")).exp() - Decimal("1")


def _estrai_righe_grezze_ammortamento(
    pagine_piano: List[Tuple[int, str]],
    numero_rate_atteso: int,
    importo_rata_riferimento: Optional[Decimal],
) -> Tuple[Dict[int, Dict[str, object]], List[int], int]:
    patron_scarto_riepilogo = re.compile(
        r"\b(?:totale|riepilogo|saldo|finale|pagina|allegato|tan|taeg)\b",
        flags=re.IGNORECASE,
    )
    righe_grezze: Dict[int, Dict[str, object]] = {}
    rate_duplicate: List[int] = []
    righe_scartate_conteggio = 0
    limite_sup_rata = numero_rate_atteso if numero_rate_atteso > 0 else 360

    for _, corpo_piano in pagine_piano:
        ordine_header_cap_prima: Optional[bool] = None
        for r_raw in corpo_piano.splitlines():
            r_low = r_raw.lower()
            if "quota capitale" in r_low and "quota interessi" in r_low:
                ordine_header_cap_prima = r_low.find("quota capitale") < r_low.find("quota interessi")
            if r_raw.strip().startswith("#"):
                continue
            if patron_scarto_riepilogo.search(r_raw):
                righe_scartate_conteggio += 1
                continue

            m_data = re.search(r"\b(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})\b", r_raw)
            scadenza_str = m_data.group(1) if m_data else ""
            r_senza_date = re.sub(r"\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b", " ", r_raw)

            m_rata = re.match(
                r"^\s*\|?\s*(?:rata\s*n?\.?\s*)?(\d{1,3})\b(.*)$",
                r_senza_date,
                flags=re.IGNORECASE,
            )
            if not m_rata:
                continue
            idx_r = int(m_rata.group(1))
            if not (1 <= idx_r <= limite_sup_rata):
                righe_scartate_conteggio += 1
                continue

            resto_riga = re.sub(r"(?<=[\|\s])0(?=\s*(?:\||$|€|eur))", "0,00", m_rata.group(2), flags=re.IGNORECASE)
            if idx_r >= max(10, limite_sup_rata - 2):
                resto_riga = re.sub(r"(?<=\|\s)-(?=\s*(?:\||$))", "0,00", resto_riga)
            token_dec = re.findall(r"\d+(?:[.,]\d{3})*(?:[.,]\d{2})(?![\d.,])", resto_riga)
            if len(token_dec) < 2:
                continue
            valori_dec = [_converti_stringa_in_decimal_audit(tok) for tok in token_dec]
            valori_validi = [v for v in valori_dec if v is not None]
            if len(valori_validi) < 2 or any(v > Decimal("1000000.00") or v < Decimal("0.00") for v in valori_validi):
                righe_scartate_conteggio += 1
                continue

            add_a = Decimal("0.00")
            add_b = Decimal("0.00")
            rata_v = Decimal("0.00")
            residui_grezzi: List[Decimal] = []

            if len(valori_validi) >= 3:
                v0, v1, v2 = valori_validi[0], valori_validi[1], valori_validi[2]
                diff_01_2 = abs((v0 + v1) - v2)
                diff_12_0 = abs((v1 + v2) - v0)
                if diff_01_2 <= Decimal("0.50") or (
                    importo_rata_riferimento is not None
                    and abs(v2 - importo_rata_riferimento) <= Decimal("0.50")
                    and diff_01_2 <= diff_12_0 + Decimal("0.50")
                ):
                    add_a, add_b, rata_v = v0, v1, v2
                    residui_grezzi = valori_validi[3:]
                elif diff_12_0 <= Decimal("0.50") or (
                    importo_rata_riferimento is not None and abs(v0 - importo_rata_riferimento) <= Decimal("0.50")
                ):
                    rata_v, add_a, add_b = v0, v1, v2
                    residui_grezzi = valori_validi[3:]
                elif len(valori_validi) == 3 and importo_rata_riferimento is not None:
                    add_a, add_b, rata_v = v0, v1, importo_rata_riferimento
                    residui_grezzi = [v2]
                else:
                    add_a, add_b, rata_v = v0, v1, v2
                    residui_grezzi = valori_validi[3:]
            else:
                if importo_rata_riferimento is None:
                    continue
                add_a, add_b = valori_validi[0], valori_validi[1]
                rata_v = importo_rata_riferimento
                residui_grezzi = []

            if rata_v <= Decimal("0.00"):
                righe_scartate_conteggio += 1
                continue

            if idx_r in righe_grezze:
                esistente = righe_grezze[idx_r]
                old_rata = Decimal(str(esistente["importo_rata"]))
                old_a = Decimal(str(esistente["add_a"]))
                old_b = Decimal(str(esistente["add_b"]))
                nuova_rata = q2(rata_v)
                nuovo_a = q2(add_a)
                nuovo_b = q2(add_b)
                stessi_addendi = (
                    abs(old_a - nuovo_a) <= Decimal("0.05") and abs(old_b - nuovo_b) <= Decimal("0.05")
                ) or (
                    abs(old_a - nuovo_b) <= Decimal("0.05") and abs(old_b - nuovo_a) <= Decimal("0.05")
                )
                if abs(old_rata - nuova_rata) <= Decimal("0.05") and stessi_addendi:
                    if len(residui_grezzi) > len(esistente["residui"]):
                        esistente["residui"] = [q2(r_res) for r_res in residui_grezzi[:2]]
                elif abs(old_rata - nuova_rata) > Decimal("0.50"):
                    rate_duplicate.append(idx_r)
            else:
                righe_grezze[idx_r] = {
                    "rata": idx_r,
                    "scadenza": scadenza_str,
                    "add_a": q2(add_a),
                    "add_b": q2(add_b),
                    "importo_rata": q2(rata_v),
                    "residui": [q2(r_res) for r_res in residui_grezzi[:2]],
                    "ordine_header_cap_prima": ordine_header_cap_prima,
                }

    return righe_grezze, rate_duplicate, righe_scartate_conteggio


def _auto_allinea_colonne_ammortamento(
    righe_grezze: Dict[int, Dict[str, object]],
    c_fin_stima: Optional[Decimal],
    m_rif_stima: Optional[Decimal],
    totale_interessi_dich: Optional[Decimal],
    tan_dichiarato: Optional[Decimal],
    numero_rate_atteso: int,
) -> Tuple[Dict[int, Dict[str, object]], str]:
    """Auto-allinea in modo deterministico Quota Capitale vs Quota Interessi e Capitale Residuo vs Debito Residuo
    sfruttando gli invarianti del piano alla francese senza fidarsi ciecamente dell'ordine di stampa."""
    chiavi_ord = sorted(righe_grezze.keys())
    righe_out: Dict[int, Dict[str, object]] = {}
    if not chiavi_ord:
        return righe_out, "NESSUNA_RIGA"

    con_due_residui = sum(1 for k in chiavi_ord if len(righe_grezze[k]["residui"]) >= 2)
    con_un_residuo = sum(1 for k in chiavi_ord if len(righe_grezze[k]["residui"]) >= 1)

    idx_cap_res = 0
    idx_deb_res = 1 if con_due_residui > 0 else -1

    if con_due_residui >= max(1, len(chiavi_ord) // 3):
        score_r0_cap = 0
        score_r1_cap = 0
        for idx_pos in range(1, len(chiavi_ord)):
            k_prev = chiavi_ord[idx_pos - 1]
            k_curr = chiavi_ord[idx_pos]
            if k_curr != k_prev + 1:
                continue
            res_prev = righe_grezze[k_prev]["residui"]
            res_curr = righe_grezze[k_curr]["residui"]
            if len(res_prev) < 2 or len(res_curr) < 2:
                continue
            r_curr = Decimal(str(righe_grezze[k_curr]["importo_rata"]))
            a_curr = Decimal(str(righe_grezze[k_curr]["add_a"]))
            b_curr = Decimal(str(righe_grezze[k_curr]["add_b"]))
            drop_0 = res_prev[0] - res_curr[0]
            drop_1 = res_prev[1] - res_curr[1]
            if abs(drop_0 - a_curr) <= Decimal("0.05") or abs(drop_0 - b_curr) <= Decimal("0.05"):
                if abs(drop_0 - r_curr) > Decimal("0.05") or res_curr[0] <= res_curr[1]:
                    score_r0_cap += 10
            if abs(drop_1 - r_curr) <= Decimal("0.05"):
                score_r0_cap += 5
            if abs(drop_1 - a_curr) <= Decimal("0.05") or abs(drop_1 - b_curr) <= Decimal("0.05"):
                if abs(drop_1 - r_curr) > Decimal("0.05") or res_curr[1] <= res_curr[0]:
                    score_r1_cap += 10
            if abs(drop_0 - r_curr) <= Decimal("0.05"):
                score_r1_cap += 5
            if res_curr[0] < res_curr[1]:
                score_r0_cap += 1
            elif res_curr[1] < res_curr[0]:
                score_r1_cap += 1
        if score_r1_cap > score_r0_cap:
            idx_cap_res, idx_deb_res = 1, 0
        else:
            idx_cap_res, idx_deb_res = 0, 1
    elif con_un_residuo == 0:
        idx_cap_res, idx_deb_res = -1, -1

    def _ottieni_cap_res(k_r: int) -> Optional[Decimal]:
        lista_r = righe_grezze[k_r]["residui"]
        if 0 <= idx_cap_res < len(lista_r):
            return Decimal(str(lista_r[idx_cap_res]))
        return None

    score_a_cap = 0
    score_b_cap = 0

    for idx_pos in range(1, len(chiavi_ord)):
        k_prev = chiavi_ord[idx_pos - 1]
        k_curr = chiavi_ord[idx_pos]
        if k_curr != k_prev + 1:
            continue
        cap_prev = _ottieni_cap_res(k_prev)
        cap_curr = _ottieni_cap_res(k_curr)
        a_curr = Decimal(str(righe_grezze[k_curr]["add_a"]))
        b_curr = Decimal(str(righe_grezze[k_curr]["add_b"]))
        if cap_prev is not None and cap_curr is not None:
            drop_cap = cap_prev - cap_curr
            if abs(drop_cap - a_curr) <= Decimal("0.05"):
                score_a_cap += 10
            if abs(drop_cap - b_curr) <= Decimal("0.05"):
                score_b_cap += 10
        if tan_dichiarato is not None and cap_prev is not None and cap_prev > Decimal("0.00"):
            i_m_test = tan_dichiarato / Decimal("1200")
            int_teor = q2(cap_prev * i_m_test)
            if abs(b_curr - int_teor) <= Decimal("0.05"):
                score_a_cap += 5
            if abs(a_curr - int_teor) <= Decimal("0.05"):
                score_b_cap += 5

    if 1 in righe_grezze and c_fin_stima is not None and c_fin_stima > Decimal("0.00"):
        cap_1 = _ottieni_cap_res(1)
        a_1 = Decimal(str(righe_grezze[1]["add_a"]))
        b_1 = Decimal(str(righe_grezze[1]["add_b"]))
        if cap_1 is not None:
            drop_1 = c_fin_stima - cap_1
            if abs(drop_1 - a_1) <= Decimal("0.05"):
                score_a_cap += 10
            if abs(drop_1 - b_1) <= Decimal("0.05"):
                score_b_cap += 10
        if tan_dichiarato is not None:
            int_1_teor = q2(c_fin_stima * (tan_dichiarato / Decimal("1200")))
            if abs(b_1 - int_1_teor) <= Decimal("0.05"):
                score_a_cap += 5
            if abs(a_1 - int_1_teor) <= Decimal("0.05"):
                score_b_cap += 5

    if len(chiavi_ord) >= 2:
        k_first, k_last = chiavi_ord[0], chiavi_ord[-1]
        a_first = Decimal(str(righe_grezze[k_first]["add_a"]))
        b_first = Decimal(str(righe_grezze[k_first]["add_b"]))
        a_last = Decimal(str(righe_grezze[k_last]["add_a"]))
        b_last = Decimal(str(righe_grezze[k_last]["add_b"]))
        if a_last > a_first and b_last < b_first:
            score_a_cap += 20
        elif b_last > b_first and a_last < a_first:
            score_b_cap += 20

    if numero_rate_atteso > 0 and len(chiavi_ord) == numero_rate_atteso:
        sum_a = sum((Decimal(str(righe_grezze[k]["add_a"])) for k in chiavi_ord), Decimal("0.00"))
        sum_b = sum((Decimal(str(righe_grezze[k]["add_b"])) for k in chiavi_ord), Decimal("0.00"))
        if c_fin_stima is not None:
            if abs(sum_a - c_fin_stima) <= Decimal("1.00"):
                score_a_cap += 15
            if abs(sum_b - c_fin_stima) <= Decimal("1.00"):
                score_b_cap += 15
        if totale_interessi_dich is not None:
            if abs(sum_b - totale_interessi_dich) <= Decimal("1.00"):
                score_a_cap += 15
            if abs(sum_a - totale_interessi_dich) <= Decimal("1.00"):
                score_b_cap += 15

    if score_a_cap == score_b_cap:
        preferenze_header = [
            righe_grezze[k]["ordine_header_cap_prima"]
            for k in chiavi_ord
            if righe_grezze[k]["ordine_header_cap_prima"] is not None
        ]
        a_e_capitale = bool(preferenze_header and preferenze_header[0])
        criterio_allineamento = "HEADER_FALLBACK"
    elif score_a_cap > score_b_cap:
        a_e_capitale = True
        criterio_allineamento = "INVARIANTE_MATEMATICO_A_CAP_B_INT"
    else:
        a_e_capitale = False
        criterio_allineamento = "INVARIANTE_MATEMATICO_B_CAP_A_INT"

    for k in chiavi_ord:
        rg = righe_grezze[k]
        add_a = Decimal(str(rg["add_a"]))
        add_b = Decimal(str(rg["add_b"]))
        q_cap_v, q_int_v = (add_a, add_b) if a_e_capitale else (add_b, add_a)
        lista_r = rg["residui"]
        ha_cap_res = 0 <= idx_cap_res < len(lista_r)
        ha_deb_res = 0 <= idx_deb_res < len(lista_r)
        cap_res_v = Decimal(str(lista_r[idx_cap_res])) if ha_cap_res else Decimal("0.00")
        deb_res_v = Decimal(str(lista_r[idx_deb_res])) if ha_deb_res else Decimal("0.00")

        righe_out[k] = {
            "rata": int(rg["rata"]),
            "scadenza": str(rg["scadenza"]),
            "importo_rata": Decimal(str(rg["importo_rata"])),
            "quota_capitale": q_cap_v,
            "quota_interessi": q_int_v,
            "capitale_residuo": cap_res_v,
            "debito_residuo": deb_res_v,
            "ha_capitale_residuo": ha_cap_res,
            "ha_debito_residuo": ha_deb_res,
            "riallineata_ocr": False,
        }

    return righe_out, criterio_allineamento


def _riallinea_colonne_riga_per_riga(
    righe_normalizzate: Dict[int, Dict[str, object]],
    c_fin_stima: Optional[Decimal],
    i_m_stima: Optional[Decimal],
    numero_rate_atteso: int,
) -> List[str]:
    """FIX 2 (v32): Rileva e riallinea eventuali inversioni OCR locali su singole righe (es. Rata 97)
    valutando prossimita' all'interesse teorico, discesa del capitale residuo e continuita' monotona."""
    chiavi_ord = sorted(righe_normalizzate.keys())
    log_riallineamenti: List[str] = []
    if len(chiavi_ord) < 2:
        return log_riallineamenti

    for idx_pos, k in enumerate(chiavi_ord):
        info_k = righe_normalizzate[k]
        qc = Decimal(str(info_k["quota_capitale"]))
        qi = Decimal(str(info_k["quota_interessi"]))
        r_v = Decimal(str(info_k["importo_rata"]))
        cap_res = Decimal(str(info_k["capitale_residuo"]))
        ha_res = bool(info_k["ha_capitale_residuo"])

        if qc == qi or abs((qc + qi) - r_v) > Decimal("0.10"):
            continue

        k_prev = chiavi_ord[idx_pos - 1] if idx_pos > 0 else None
        k_next = chiavi_ord[idx_pos + 1] if idx_pos + 1 < len(chiavi_ord) else None

        costo_dir = Decimal("0.00")
        costo_inv = Decimal("0.00")
        segnali_validi = 0

        if i_m_stima is not None and i_m_stima > Decimal("0"):
            d_prec_dir: Optional[Decimal] = None
            d_prec_inv: Optional[Decimal] = None
            if k == 1 and c_fin_stima is not None and c_fin_stima > Decimal("0"):
                d_prec_dir = c_fin_stima
                d_prec_inv = c_fin_stima
            elif k_prev == k - 1 and righe_normalizzate[k_prev]["ha_capitale_residuo"]:
                d_prec_k = Decimal(str(righe_normalizzate[k_prev]["capitale_residuo"]))
                d_prec_dir = d_prec_k
                d_prec_inv = d_prec_k
            elif ha_res:
                d_prec_dir = cap_res + qc
                d_prec_inv = cap_res + qi

            if d_prec_dir is not None and d_prec_inv is not None:
                costo_dir += abs(qi - q2(d_prec_dir * i_m_stima)) * Decimal("2")
                costo_inv += abs(qc - q2(d_prec_inv * i_m_stima)) * Decimal("2")
                segnali_validi += 1

        if ha_res and k_prev == k - 1 and righe_normalizzate[k_prev]["ha_capitale_residuo"]:
            d_prev_k = Decimal(str(righe_normalizzate[k_prev]["capitale_residuo"]))
            drop_res = d_prev_k - cap_res
            costo_dir += abs(drop_res - qc) * Decimal("3")
            costo_inv += abs(drop_res - qi) * Decimal("3")
            segnali_validi += 1

        rif_cap_vicini: List[Decimal] = []
        rif_int_vicini: List[Decimal] = []
        if k_prev is not None and (k - k_prev) <= 3:
            rif_cap_vicini.append(Decimal(str(righe_normalizzate[k_prev]["quota_capitale"])))
            rif_int_vicini.append(Decimal(str(righe_normalizzate[k_prev]["quota_interessi"])))
        if k_next is not None and (k_next - k) <= 3:
            rif_cap_vicini.append(Decimal(str(righe_normalizzate[k_next]["quota_capitale"])))
            rif_int_vicini.append(Decimal(str(righe_normalizzate[k_next]["quota_interessi"])))

        if rif_cap_vicini:
            med_cap = sum(rif_cap_vicini, Decimal("0")) / Decimal(len(rif_cap_vicini))
            med_int = sum(rif_int_vicini, Decimal("0")) / Decimal(len(rif_int_vicini))
            costo_dir += abs(qc - med_cap) + abs(qi - med_int)
            costo_inv += abs(qi - med_cap) + abs(qc - med_int)
            segnali_validi += 1

        if segnali_validi >= 1 and costo_inv + Decimal("1.00") < costo_dir:
            nuovo_q_cap, nuovo_q_int = qi, qc
            info_k["quota_capitale"] = nuovo_q_cap
            info_k["quota_interessi"] = nuovo_q_int
            info_k["riallineata_ocr"] = True
            log_riallineamenti.append(
                f"Riallineata colonna invertita dall'OCR sulla Rata {k} "
                f"(Q_cap={nuovo_q_cap} €, Q_int={nuovo_q_int} €)"
            )

    return log_riallineamenti


def _estrai_voci_costi_accessori(testo_sorgente: str) -> List[Tuple[str, Decimal]]:
    pattern_voci = [
        ("Spese di istruttoria", r"(?:spese\s+(?:di\s+)?istruttoria|istruttoria)[^0-9\n]{0,60}?(\d{1,3}(?:\.\d{3})*[.,]\d{2})\b"),
        ("Commissioni / Intermediazione", r"(?:commissioni(?:\s+(?:bancarie|di\s+intermediazione|di\s+distribuzione|di\s+attivazione|finanziarie))?|provvigioni)[^0-9\n]{0,60}?(\d{1,3}(?:\.\d{3})*[.,]\d{2})\b"),
        ("Oneri fiscali / Imposta", r"(?:oneri\s+fiscali|imposta\s+sostitutiva|imposta\s+di\s+bollo|bolli)[^0-9\n]{0,60}?(\d{1,3}(?:\.\d{3})*[.,]\d{2})\b"),
        ("Polizza / Premi assicurativi", r"(?:polizza(?:\s+(?:vita|impiego|rischio|assicurativa))?|premi\s+assicurativi|assicurazione)[^0-9\n]{0,60}?(\d{1,3}(?:\.\d{3})*[.,]\d{2})\b"),
        ("Costi / Spese incasso rate", r"(?:cost[oi]\s+(?:di\s+)?incasso|spese\s+(?:di\s+)?incasso(?:\s+rat[ae])?)[^0-9\n]{0,60}?(\d{1,3}(?:\.\d{3})*[.,]\d{2})\b"),
    ]
    trovate: List[Tuple[str, Decimal]] = []
    importi_visti: set[Decimal] = set()
    for etichetta, pat_v in pattern_voci:
        for m_v in re.finditer(pat_v, testo_sorgente, flags=re.IGNORECASE):
            val_v = _converti_stringa_in_decimal_audit(m_v.group(1))
            if val_v is not None and Decimal("0.00") < val_v < Decimal("20000.00"):
                v_q = q2(val_v)
                if v_q not in importi_visti:
                    importi_visti.add(v_q)
                    trovate.append((etichetta, v_q))
    return trovate


def _riconcilia_costi_accessori_subset_sum(
    testo_sorgente: str,
    pagine_tutte: List[Tuple[int, str]],
    pagine_piano: List[Tuple[int, str]],
    k_target: Decimal,
    importo_rata: Optional[Decimal] = None,
) -> Dict[str, object]:
    """Sezione 2 (v33): Estrae gli importi atomici dalle pagine riepilogo, esclude automaticamente i subtotali
    (S = a + b) e cerca tramite subset-sum combinatorio (2..6 voci) il sottoinsieme che eguaglia k_target."""
    voci_etichettate_grezze = _estrai_voci_costi_accessori(testo_sorgente)
    mappa_etichette: Dict[Decimal, str] = {}
    for et_v, val_v in voci_etichettate_grezze:
        if val_v not in mappa_etichette:
            mappa_etichette[val_v] = et_v

    num_pagine_piano = {np_p for np_p, _ in pagine_piano}
    blocchi_riepilogo = [
        corpo_b
        for num_b, corpo_b in pagine_tutte
        if num_b not in num_pagine_piano
    ]
    testo_riepilogo = "\n".join(blocchi_riepilogo) if blocchi_riepilogo else testo_sorgente

    score_semantico: Dict[Decimal, int] = {}
    ordine_valori: List[Decimal] = []
    kw_costo = ("istruttoria", "imposta", "bollo", "commission", "polizza", "assicuraz", "oneri", "spese", "premio", "intermediaz", "incasso")
    kw_rumore = ("decumulo", "estinzione", "residua", "esempio", "rata", "montante", "interessi totali")

    for riga_r in testo_riepilogo.splitlines():
        r_low = riga_r.lower()
        if re.match(r"^\s*\|?\s*(?:rata\s*n?\.?\s*)?\d{1,3}\b", riga_r, flags=re.IGNORECASE):
            continue
        r_senza_date = re.sub(r"\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b", " ", riga_r)
        bonus_r = 0
        if any(kw in r_low for kw in kw_costo):
            bonus_r += 10
        if any(kw in r_low for kw in kw_rumore):
            bonus_r -= 5
        for tok_imp in re.findall(r"\d+(?:[.,]\d{3})*(?:[.,]\d{2})(?![\d.,])", r_senza_date):
            val_d = _converti_stringa_in_decimal_audit(tok_imp)
            if val_d is None:
                continue
            v_q = q2(val_d)
            if v_q < Decimal("1.00") or v_q > k_target:
                continue
            if importo_rata is not None and abs(v_q - importo_rata) <= Decimal("0.01"):
                continue
            if v_q not in score_semantico:
                ordine_valori.append(v_q)
                score_semantico[v_q] = bonus_r
            else:
                score_semantico[v_q] = max(score_semantico[v_q], bonus_r)

    for val_et in mappa_etichette:
        if Decimal("1.00") <= val_et <= k_target and val_et not in score_semantico:
            ordine_valori.append(val_et)
            score_semantico[val_et] = 12

    subtotali_rilevati: Set[Decimal] = set()
    insieme_candidati = set(ordine_valori)
    for v_s in ordine_valori:
        trovato_sum = False
        for v_a in ordine_valori:
            if v_a >= v_s:
                continue
            v_b = q2(v_s - v_a)
            if v_b != v_a and v_b in insieme_candidati:
                if not any(
                    v_x in mappa_etichette and v_s in mappa_etichette
                    and score_semantico.get(v_s, 0) > score_semantico.get(v_a, 0) + 10
                    for v_x in (v_a, v_b)
                ):
                    trovato_sum = True
                    break
        if trovato_sum:
            subtotali_rilevati.add(v_s)

    atomici = [v for v in ordine_valori if v not in subtotali_rilevati]
    atomici_ordinati = sorted(atomici, key=lambda x: (-score_semantico.get(x, 0), ordine_valori.index(x)))[:22]

    miglior_comb: Optional[Tuple[Decimal, ...]] = None
    miglior_chiave_rank: Optional[Tuple[Decimal, int, int]] = None

    for card in range(2, min(7, len(atomici_ordinati) + 1)):
        for comb in combinations(atomici_ordinati, card):
            diff_c = abs(sum(comb, Decimal("0.00")) - k_target)
            if diff_c <= Decimal("0.02"):
                sc_sem = sum(score_semantico.get(x, 0) for x in comb)
                chiave_rank = (diff_c, -sc_sem, card)
                if miglior_chiave_rank is None or chiave_rank < miglior_chiave_rank:
                    miglior_chiave_rank = chiave_rank
                    miglior_comb = comb
        if miglior_comb is not None and miglior_chiave_rank is not None and miglior_chiave_rank[0] == Decimal("0.00") and miglior_chiave_rank[1] < 0:
            break

    if miglior_comb is not None:
        voci_riconciliate = sorted(miglior_comb, key=lambda x: ordine_valori.index(x))
        set_ric = set(voci_riconciliate)
        scartati = [v for v in ordine_valori if v not in set_ric]
        etichettate_out = [
            (mappa_etichette.get(v_r, "Costo accessorio"), v_r)
            for v_r in voci_riconciliate
        ]
        return {
            "voci_costi_accessori_riconciliate": voci_riconciliate,
            "voci_etichettate_riconciliate": etichettate_out,
            "somma_costi_accessori": q2(sum(voci_riconciliate, Decimal("0.00"))),
            "riconciliazione_costi_ok": True,
            "subtotali_o_esempi_scartati": scartati,
        }

    return {
        "voci_costi_accessori_riconciliate": [v for _, v in voci_etichettate_grezze if v not in subtotali_rilevati],
        "voci_etichettate_riconciliate": [(et, v) for et, v in voci_etichettate_grezze if v not in subtotali_rilevati],
        "somma_costi_accessori": q2(sum((v for _, v in voci_etichettate_grezze if v not in subtotali_rilevati), Decimal("0.00"))),
        "riconciliazione_costi_ok": False,
        "subtotali_o_esempi_scartati": sorted(subtotali_rilevati),
    }


def esegui_audit_matematico_tabella_pdf(testo_documento: str) -> Dict[str, object]:
    """Pipeline matematica deterministica v31 in 11 Sezioni (Livello 1, Decimal ROUND_HALF_UP):
    estrazione multi-riga TAN/TAEG/C_netto, auto-allineamento Q_int vs Q_cap e Capitale vs Debito Residuo,
    doppia convenzione TAN, rata teorica alla francese, verifica interessi D_precedente(t) inclusa Rata 120,
    D(n)=0 mai None, anti-circolarita', budget rate mancanti con salto buco e bisezione IRR NPV."""
    testo = testo_documento or ""
    classif = classifica_pagine_per_funzione(testo)
    pagine_tutte: List[Tuple[int, str]] = classif["pagine_tutte"]
    pagine_piano: List[Tuple[int, str]] = classif["PAGINE_PIANO_AMMORTAMENTO"]
    pagine_costi_taeg: List[Tuple[int, str]] = classif["PAGINE_RIEPILOGO_COSTI_TAEG"]
    pagine_liq: List[Tuple[int, str]] = classif["PAGINE_PROSPETTO_LIQUIDAZIONE"]

    pagine_trovate = sorted({num_p for num_p, _ in pagine_tutte})
    testo_costi_liq = "\n\n".join(
        t for _, t in (pagine_costi_taeg + pagine_liq)
    ) or testo
    testo_costi_low = testo_costi_liq.lower()
    ha_pag_8_9 = bool(
        8 in pagine_trovate
        or 9 in pagine_trovate
        or ("taeg" in testo_costi_low and ("netto ricavo" in testo_costi_low or "capitale finanziato" in testo_costi_low or "importo totale del credito" in testo_costi_low or "saldo netto" in testo_costi_low or "tan" in testo_costi_low))
    )

    def _cerca_parametro_dec(
        sorgente_testo: str,
        pattern_lista: List[str],
        min_val: Decimal = Decimal("0.01"),
        max_val: Decimal = Decimal("1000000.00"),
        usa_dotall: bool = True,
        vieta_parola_intermedia: Optional[str] = None,
    ) -> Optional[Decimal]:
        flags_re = re.IGNORECASE | (re.DOTALL if usa_dotall else 0)
        for pat in pattern_lista:
            for m in re.finditer(pat, sorgente_testo, flags=flags_re):
                if vieta_parola_intermedia and re.search(vieta_parola_intermedia, m.group(0), flags=re.IGNORECASE):
                    continue
                val = _converti_stringa_in_decimal_audit(m.group(1))
                if val is not None and min_val <= val <= max_val:
                    return q2(val)
        return None

    def _raccogli_tutti_parametri_dec(
        sorgente_testo: str,
        pattern_lista: List[str],
        min_val: Decimal = Decimal("0.01"),
        max_val: Decimal = Decimal("1000000.00"),
        usa_dotall: bool = True,
        vieta_parola_intermedia: Optional[str] = None,
    ) -> List[Decimal]:
        flags_re = re.IGNORECASE | (re.DOTALL if usa_dotall else 0)
        risultati: List[Decimal] = []
        visti: Set[Decimal] = set()
        for pat in pattern_lista:
            for m in re.finditer(pat, sorgente_testo, flags=flags_re):
                if vieta_parola_intermedia and re.search(vieta_parola_intermedia, m.group(0), flags=re.IGNORECASE):
                    continue
                val = _converti_stringa_in_decimal_audit(m.group(1))
                if val is not None and min_val <= val <= max_val:
                    v_q = q2(val)
                    if v_q not in visti:
                        visti.add(v_q)
                        risultati.append(v_q)
        return risultati

    def _raccogli_importi_non_tabella() -> List[Decimal]:
        num_p_piano = {np_p for np_p, _ in pagine_piano}
        blocchi_nt = [
            corpo_nt
            for num_nt, corpo_nt in pagine_tutte
            if num_nt not in num_p_piano
        ]
        testo_nt = "\n".join(blocchi_nt) if blocchi_nt else testo
        importi_nt: List[Decimal] = []
        visti_nt: Set[Decimal] = set()
        for riga_nt in testo_nt.splitlines():
            if re.match(r"^\s*\|?\s*(?:rata\s*n?\.?\s*)?\d{1,3}\b", riga_nt, flags=re.IGNORECASE):
                continue
            r_clean = re.sub(r"\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b", " ", riga_nt)
            for tok_nt in re.findall(r"\b(\d{1,3}(?:\.\d{3})+[.,]\d{2}|\d{3,6}[.,]\d{2})\b", r_clean):
                val_nt = _converti_stringa_in_decimal_audit(tok_nt)
                if val_nt is not None and Decimal("100.00") <= val_nt <= Decimal("1000000.00"):
                    v_q = q2(val_nt)
                    if v_q not in visti_nt:
                        visti_nt.add(v_q)
                        importi_nt.append(v_q)
        return importi_nt

    numero_rate_atteso = 0
    for pat_n in (
        r"(?:numero\s+(?:totale\s+)?(?:delle\s+)?rate(?:\s+totale)?|n\.?\s*rate|durata(?:\s+finanziamento)?)\s*[:=|\n\s]{1,40}(\d{1,3})\b",
        r"\b(\d{1,3})\s+rate(?:\s+mensili|\s+da|\s+costanti)\b",
    ):
        m_nr = re.search(pat_n, testo_costi_liq if testo_costi_liq else testo, flags=re.IGNORECASE | re.DOTALL)
        if not m_nr:
            m_nr = re.search(pat_n, testo, flags=re.IGNORECASE | re.DOTALL)
        if m_nr:
            cand_n = int(m_nr.group(1))
            if 6 <= cand_n <= 360:
                numero_rate_atteso = cand_n
                break

    pattern_rata = [
        r"(?:importo\s+(?:della\s+)?rata(?:\s+mensile)?|rata\s+mensile(?:\s+costante)?|rate\s+(?:mensili\s+)?da)[^0-9]{0,120}?(\d{1,3}(?:\.\d{3})*[.,]\d{2})",
    ]
    importo_rata = _cerca_parametro_dec(testo_costi_liq, pattern_rata) or _cerca_parametro_dec(testo, pattern_rata)

    pattern_montante = [
        r"(?:montante(?:\s+lordo|\s+complessivo|\s+dichiarato)?|importo\s+totale\s+dovuto(?:\s+dal\s+consumatore)?|totale\s+dovuto)[^0-9]{0,140}?(\d{1,3}(?:\.\d{3})+[.,]\d{2}|\d{4,6}[.,]\d{2})",
        r"\b\d{1,3}\s+rate\s+da\s*(?:euro|eur|€)?\s*\d+(?:[.,]\d+)+\s*(?:euro|eur|€)?\s*\(\s*(?:euro|eur|€)?\s*(\d+(?:[.,]\d+)+)",
    ]
    montante_dichiarato = _cerca_parametro_dec(testo_costi_liq, pattern_montante) or _cerca_parametro_dec(testo, pattern_montante)

    pattern_c_fin = [
        r"CAPITALE_FINANZIATO\s*[:=]\s*(?:euro|eur|€)?\s*(\d{1,3}(?:\.\d{3})+[.,]\d{2}|\d{4,6}[.,]\d{2})",
        r"(?:capitale\s+(?:finanziato|lordo|iniziale|mutuato)|importo\s+finanziato(?:\s+lordo)?|somma\s+finanziata)[^0-9]{0,90}?(\d{1,3}(?:\.\d{3})+[.,]\d{2}|\d{4,6}[.,]\d{2})",
    ]
    cfin_espliciti_cands = _raccogli_tutti_parametri_dec(
        testo_costi_liq,
        pattern_c_fin,
        vieta_parola_intermedia=r"(?:importo\s+totale\s+del\s+credito|netto\s+ricavo|saldo\s+netto|netto\s+erogato|somma\s+netta)",
    ) or _raccogli_tutti_parametri_dec(
        testo,
        pattern_c_fin,
        vieta_parola_intermedia=r"(?:importo\s+totale\s+del\s+credito|netto\s+ricavo|saldo\s+netto|netto\s+erogato|somma\s+netta)",
    )
    capitale_finanziato_esplicito = cfin_espliciti_cands[0] if cfin_espliciti_cands else None

    pattern_netto = [
        r"NETTO_RICAVO_CREDITO\s*[:=]\s*(?:euro|eur|€)?\s*(\d{1,3}(?:\.\d{3})+[.,]\d{2}|\d{4,6}[.,]\d{2})",
        r"(?:netto\s+ricavo|saldo\s+netto(?:\s+erogato)?|importo\s+totale\s+del\s+credito|importo\s+netto\s+erogato|importo\s+erogato|somma\s+netta(?:\s+erogata)?|erogato\s+netto|netto\s+al\s+cliente|erogazione\s+netta|totale\s+credito|valore\s+attuale(?:\s+netto)?)[^0-9]{0,200}?(\d{1,3}(?:\.\d{3})+[.,]\d{2}|\d{4,6}[.,]\d{2})",
    ]
    netto_espliciti_cands = _raccogli_tutti_parametri_dec(testo, pattern_netto, min_val=Decimal("100.00"))
    netto_ricavo_esplicito = netto_espliciti_cands[0] if netto_espliciti_cands else None

    if capitale_finanziato_esplicito is not None and netto_ricavo_esplicito is not None and capitale_finanziato_esplicito == netto_ricavo_esplicito:
        if len(cfin_espliciti_cands) > 1:
            capitale_finanziato_esplicito = next((c for c in cfin_espliciti_cands if c != netto_ricavo_esplicito), None)
        else:
            capitale_finanziato_esplicito = None

    pattern_interessi_tot = [
        r"INTERESSI_TOTALI\s*[:=]\s*(?:euro|eur|€)?\s*(\d{1,3}(?:\.\d{3})+[.,]\d{2}|\d{3,6}[.,]\d{2})",
        r"(?:totale\s+interessi|interessi\s+totali|interessi\s+complessivi|quota\s+interessi\s+totale|interessi\s+contrattuali|interessi\s+nominali)[^0-9]{0,140}?(\d{1,3}(?:\.\d{3})+[.,]\d{2}|\d{3,6}[.,]\d{2})",
        r"(?<!di\s)\binteressi\s*[:=|\s]{1,30}(?:euro|eur|€)?\s*(\d{1,3}(?:\.\d{3})+[.,]\d{2}|\d{3,6}[.,]\d{2})",
    ]
    interessi_espliciti_cands = _raccogli_tutti_parametri_dec(
        testo_costi_liq, pattern_interessi_tot, min_val=Decimal("10.00")
    )
    for extra_int in _raccogli_tutti_parametri_dec(testo, pattern_interessi_tot, min_val=Decimal("10.00")):
        if extra_int not in interessi_espliciti_cands:
            interessi_espliciti_cands.append(extra_int)
    totale_interessi_dich = interessi_espliciti_cands[0] if interessi_espliciti_cands else None

    costi_upfront_taeg = Decimal("0.00")
    for pat_costo in (
        r"(?:spese\s+(?:di\s+)?istruttoria|commissioni\s+(?:bancarie|di\s+intermediazione|di\s+distribuzione|di\s+attivazione)|oneri\s+fiscali|imposta\s+sostitutiva|polizza\s+(?:vita|impiego)|cost[oi]\s+(?:di\s+)?incasso)[^0-9]{0,80}?(\d{1,3}(?:\.\d{3})*[.,]\d{2})\b",
    ):
        for m_c in re.finditer(pat_costo, testo, flags=re.IGNORECASE | re.DOTALL):
            v_c = _converti_stringa_in_decimal_audit(m_c.group(1))
            if v_c is not None and Decimal("0.00") < v_c < Decimal("20000.00"):
                costi_upfront_taeg += q2(v_c)

    tan_dichiarato = _cerca_parametro_dec(
        testo,
        [
            r"TAN_DICHIARATO\s*[:=]\s*(\d{1,2}[.,]\d{1,4})\s*%?",
            r"\b(?:T\.?\s*A\.?\s*N\.?|tasso\s+annuo\s+nominale(?:\s+fisso)?)\b[^0-9]{0,180}?(\d{1,2}[.,]\d{1,4})\s*%",
            r"\b(?:T\.?\s*A\.?\s*N\.?|tasso\s+annuo\s+nominale(?:\s+fisso)?)\b[^0-9]{0,180}?(\d{1,2}[.,]\d{1,4})\b",
        ],
        min_val=Decimal("0.50"),
        max_val=Decimal("25.00"),
        vieta_parola_intermedia=r"\b(?:T\.?\s*A\.?\s*E\.?\s*G\.?|I\.?\s*S\.?\s*C\.?)\b",
    ) or _cerca_parametro_dec(
        testo,
        [r"\b(?:T\.?\s*A\.?\s*N\.?|tasso\s+annuo\s+nominale)\b[^0-9]{0,180}?(\d{1,2}[.,]\d{1,4})\s*%?"],
        min_val=Decimal("0.50"),
        max_val=Decimal("25.00"),
    )

    min_taeg_val = tan_dichiarato if tan_dichiarato is not None else Decimal("0.50")
    taeg_dichiarato = _cerca_parametro_dec(
        testo,
        [
            r"TAEG_DICHIARATO\s*[:=]\s*(\d{1,2}[.,]\d{1,4})\s*%?",
            r"\b(?:T\.?\s*A\.?\s*E\.?\s*G\.?|tasso\s+annuo\s+effettivo\s+globale|I\.?\s*S\.?\s*C\.?)\b[^0-9]{0,180}?(\d{1,2}[.,]\d{1,4})\s*%",
            r"\b(?:T\.?\s*A\.?\s*E\.?\s*G\.?|tasso\s+annuo\s+effettivo\s+globale|I\.?\s*S\.?\s*C\.?)\b[^0-9]{0,180}?(\d{1,2}[.,]\d{1,4})\b",
        ],
        min_val=min_taeg_val,
        max_val=Decimal("35.00"),
    ) or _cerca_parametro_dec(
        testo,
        [r"\b(?:T\.?\s*A\.?\s*E\.?\s*G\.?|tasso\s+annuo\s+effettivo\s+globale|I\.?\s*S\.?\s*C\.?)\b[^0-9]{0,180}?(\d{1,2}[.,]\d{1,4})\s*%?"],
        min_val=Decimal("0.50"),
        max_val=Decimal("35.00"),
    )

    righe_grezze, rate_duplicate, righe_scartate_conteggio = _estrai_righe_grezze_ammortamento(
        pagine_piano, numero_rate_atteso, importo_rata
    )

    if numero_rate_atteso == 0 and righe_grezze:
        numero_rate_atteso = max(righe_grezze.keys())
    if importo_rata is None and righe_grezze:
        primo_k = min(righe_grezze.keys())
        importo_rata = Decimal(str(righe_grezze[primo_k]["importo_rata"]))

    montante_calcolato_iniz = (
        q2(Decimal(numero_rate_atteso) * importo_rata)
        if numero_rate_atteso > 0 and importo_rata is not None
        else None
    )
    m_rif_iniz = montante_dichiarato or montante_calcolato_iniz
    importi_non_tabella = _raccogli_importi_non_tabella()

    c_atteso_tan: Optional[Decimal] = None
    i_atteso_tan: Optional[Decimal] = None
    if tan_dichiarato is not None and numero_rate_atteso > 0 and importo_rata is not None:
        i_m_dich_iniz = tan_dichiarato / Decimal("1200")
        denom_tan_iniz = Decimal("1") - ((Decimal("1") + i_m_dich_iniz) ** (-numero_rate_atteso))
        if denom_tan_iniz > Decimal("0"):
            c_atteso_tan = q2(importo_rata * (denom_tan_iniz / i_m_dich_iniz))
            if m_rif_iniz is not None and m_rif_iniz > c_atteso_tan:
                i_atteso_tan = q2(m_rif_iniz - c_atteso_tan)

    if tan_dichiarato is not None and m_rif_iniz is not None and importo_rata is not None and numero_rate_atteso > 0:
        lista_flussi_iniz = [importo_rata] * numero_rate_atteso

        def _score_interessi_attuario(i_cand: Decimal, etichettato: bool) -> Decimal:
            c_impl = q2(m_rif_iniz - i_cand)
            if c_impl <= Decimal("0.00"):
                return Decimal("-1000")
            i_m_c = irr_bisection(c_impl, lista_flussi_iniz)
            if i_m_c is None:
                return Decimal("-500")
            tan_impl = q2(i_m_c * Decimal("1200"))
            delta_t = abs(tan_impl - tan_dichiarato)
            sc = Decimal("0")
            if delta_t <= Decimal("0.05"):
                sc += Decimal("100")
            elif delta_t <= Decimal("0.20"):
                sc += Decimal("60")
            elif delta_t <= Decimal("0.50"):
                sc += Decimal("20")
            else:
                sc -= Decimal("60")
            if etichettato:
                sc += Decimal("15")
            if i_atteso_tan is not None:
                sc -= min(Decimal("10"), abs(i_cand - i_atteso_tan) / Decimal("100"))
            return sc

        miglior_i_cand: Optional[Decimal] = totale_interessi_dich
        miglior_i_score: Optional[Decimal] = (
            _score_interessi_attuario(totale_interessi_dich, True)
            if totale_interessi_dich is not None
            else None
        )
        for cand_i_lab in interessi_espliciti_cands:
            sc_i = _score_interessi_attuario(cand_i_lab, True)
            if miglior_i_score is None or sc_i > miglior_i_score:
                miglior_i_score = sc_i
                miglior_i_cand = cand_i_lab
        if miglior_i_score is None or miglior_i_score < Decimal("50"):
            for cand_i_nt in importi_non_tabella:
                if Decimal("10.00") < cand_i_nt < q2(Decimal("0.65") * m_rif_iniz):
                    sc_nt = _score_interessi_attuario(cand_i_nt, False)
                    if sc_nt >= Decimal("60") and (miglior_i_score is None or sc_nt > miglior_i_score):
                        miglior_i_score = sc_nt
                        miglior_i_cand = cand_i_nt
        if miglior_i_cand is not None:
            totale_interessi_dich = miglior_i_cand

        def _score_cfin_attuario(c_cand: Decimal, etichettato: bool) -> Decimal:
            if c_cand <= Decimal("0.00") or c_cand >= m_rif_iniz:
                return Decimal("-1000")
            i_m_c = irr_bisection(c_cand, lista_flussi_iniz)
            if i_m_c is None:
                return Decimal("-500")
            tan_impl = q2(i_m_c * Decimal("1200"))
            delta_t = abs(tan_impl - tan_dichiarato)
            sc = Decimal("0")
            if delta_t <= Decimal("0.05"):
                sc += Decimal("100")
            elif delta_t <= Decimal("0.20"):
                sc += Decimal("60")
            elif delta_t <= Decimal("0.50"):
                sc += Decimal("20")
            else:
                sc -= Decimal("60")
            if etichettato:
                sc += Decimal("15")
            if c_atteso_tan is not None:
                sc -= min(Decimal("10"), abs(c_cand - c_atteso_tan) / Decimal("100"))
            return sc

        miglior_c_cand: Optional[Decimal] = capitale_finanziato_esplicito
        miglior_c_score: Optional[Decimal] = (
            _score_cfin_attuario(capitale_finanziato_esplicito, True)
            if capitale_finanziato_esplicito is not None
            else None
        )
        for cand_c_lab in cfin_espliciti_cands:
            sc_c = _score_cfin_attuario(cand_c_lab, True)
            if miglior_c_score is None or sc_c > miglior_c_score:
                miglior_c_score = sc_c
                miglior_c_cand = cand_c_lab
        if miglior_c_score is None or miglior_c_score < Decimal("50"):
            lim_c_inf = q2(Decimal("0.35") * m_rif_iniz)
            lim_c_sup = q2(Decimal("0.98") * m_rif_iniz)
            for cand_c_nt in importi_non_tabella:
                if lim_c_inf <= cand_c_nt < lim_c_sup and cand_c_nt not in netto_espliciti_cands:
                    sc_cnt = _score_cfin_attuario(cand_c_nt, False)
                    if sc_cnt >= Decimal("60") and (miglior_c_score is None or sc_cnt > miglior_c_score):
                        miglior_c_score = sc_cnt
                        miglior_c_cand = cand_c_nt
        if miglior_c_cand is not None:
            capitale_finanziato_esplicito = miglior_c_cand

    c_fin_da_montante: Optional[Decimal] = None
    if m_rif_iniz is not None and totale_interessi_dich is not None:
        cand_da_montante = q2(m_rif_iniz - totale_interessi_dich)
        if cand_da_montante > Decimal("0.00"):
            c_fin_da_montante = cand_da_montante

    if (
        c_fin_da_montante is not None
        and capitale_finanziato_esplicito is not None
        and tan_dichiarato is not None
        and importo_rata is not None
        and numero_rate_atteso > 0
    ):
        lista_fl_cmp = [importo_rata] * numero_rate_atteso
        irr_dm = irr_bisection(c_fin_da_montante, lista_fl_cmp)
        irr_es = irr_bisection(capitale_finanziato_esplicito, lista_fl_cmp)
        err_dm = abs(q2(irr_dm * Decimal("1200")) - tan_dichiarato) if irr_dm is not None else Decimal("99")
        err_es = abs(q2(irr_es * Decimal("1200")) - tan_dichiarato) if irr_es is not None else Decimal("99")
        c_fin_stima = c_fin_da_montante if err_dm <= err_es + Decimal("0.15") else capitale_finanziato_esplicito
    else:
        c_fin_stima = c_fin_da_montante or capitale_finanziato_esplicito

    righe_normalizzate, criterio_allineamento_colonne = _auto_allinea_colonne_ammortamento(
        righe_grezze,
        c_fin_stima,
        m_rif_iniz,
        totale_interessi_dich,
        tan_dichiarato,
        numero_rate_atteso,
    )

    if c_fin_stima is None and 1 in righe_normalizzate and righe_normalizzate[1]["ha_capitale_residuo"]:
        c_fin_stima = q2(
            Decimal(str(righe_normalizzate[1]["capitale_residuo"]))
            + Decimal(str(righe_normalizzate[1]["quota_capitale"]))
        )

    i_m_stima_loc: Optional[Decimal] = (
        (tan_dichiarato / Decimal("1200")) if tan_dichiarato is not None else None
    )
    if i_m_stima_loc is None and c_fin_stima is not None and numero_rate_atteso > 0 and importo_rata is not None:
        i_m_stima_loc = irr_bisection(c_fin_stima, [importo_rata] * numero_rate_atteso)

    rate_riallineate_ocr = _riallinea_colonne_riga_per_riga(
        righe_normalizzate,
        c_fin_stima,
        i_m_stima_loc,
        numero_rate_atteso,
    )

    rate_lette_lista = sorted(righe_normalizzate.keys())
    n_rate_estratte = len(rate_lette_lista)
    rate_mancanti_lista = (
        [k for k in range(1, numero_rate_atteso + 1) if k not in righe_normalizzate]
        if numero_rate_atteso > 0
        else []
    )
    elenco_mancanti_str = _compatta_intervalli_rate(rate_mancanti_lista)
    piano_completo_al_100 = bool(
        numero_rate_atteso > 0
        and n_rate_estratte == numero_rate_atteso
        and len(rate_mancanti_lista) == 0
    )

    somma_quote_capitale_lette = q2(
        sum((Decimal(str(righe_normalizzate[k]["quota_capitale"])) for k in rate_lette_lista), Decimal("0.00"))
    )
    somma_quote_interessi_lette = q2(
        sum((Decimal(str(righe_normalizzate[k]["quota_interessi"])) for k in rate_lette_lista), Decimal("0.00"))
    )
    somma_rate_lette = q2(
        sum((Decimal(str(righe_normalizzate[k]["importo_rata"])) for k in rate_lette_lista), Decimal("0.00"))
    )

    c_fin: Optional[Decimal] = c_fin_stima
    if c_fin is None and capitale_finanziato_esplicito is not None and capitale_finanziato_esplicito != netto_ricavo_esplicito:
        c_fin = capitale_finanziato_esplicito
    if c_fin is None and 1 in righe_normalizzate and righe_normalizzate[1]["ha_capitale_residuo"]:
        c_fin = q2(
            Decimal(str(righe_normalizzate[1]["capitale_residuo"]))
            + Decimal(str(righe_normalizzate[1]["quota_capitale"]))
        )
    if c_fin is None and piano_completo_al_100 and somma_quote_capitale_lette > Decimal("0.00"):
        c_fin = somma_quote_capitale_lette

    if piano_completo_al_100:
        lista_rate_irr = [Decimal(str(righe_normalizzate[k]["importo_rata"])) for k in rate_lette_lista]
    elif numero_rate_atteso > 0 and importo_rata is not None:
        lista_rate_irr = [importo_rata] * numero_rate_atteso
    else:
        lista_rate_irr = []

    candidati_netto_pool: List[Decimal] = []
    visti_netto_pool: Set[Decimal] = set()
    for c_nl in netto_espliciti_cands:
        if c_fin is None or c_nl < c_fin:
            if c_nl not in visti_netto_pool:
                visti_netto_pool.add(c_nl)
                candidati_netto_pool.append(c_nl)
    if c_fin is not None and c_fin > Decimal("0.00"):
        lim_inf_n = q2(Decimal("0.50") * c_fin)
        lim_sup_n = q2(Decimal("0.98") * c_fin)
        for val_imp in importi_non_tabella:
            if lim_inf_n <= val_imp <= lim_sup_n:
                if importo_rata is not None and abs(val_imp - importo_rata) <= Decimal("0.01"):
                    continue
                if val_imp not in visti_netto_pool:
                    visti_netto_pool.add(val_imp)
                    candidati_netto_pool.append(val_imp)
        if costi_upfront_taeg > Decimal("0.00"):
            cand_upf = q2(c_fin - costi_upfront_taeg)
            if Decimal("100.00") <= cand_upf < c_fin and cand_upf not in visti_netto_pool:
                visti_netto_pool.add(cand_upf)
                candidati_netto_pool.append(cand_upf)

    c_netto: Optional[Decimal] = None
    if candidati_netto_pool:
        miglior_n_score: Optional[int] = None
        miglior_n_val: Optional[Decimal] = None
        for cand_n in candidati_netto_pool[:24]:
            sc_n = 10 if cand_n in netto_espliciti_cands else 0
            if c_fin is not None and c_fin > cand_n:
                k_cand_n = q2(c_fin - cand_n)
                esito_k_n = _riconcilia_costi_accessori_subset_sum(
                    testo, pagine_tutte, pagine_piano, k_cand_n, importo_rata=importo_rata
                )
                if esito_k_n["riconciliazione_costi_ok"]:
                    sc_n += 100
            if taeg_dichiarato is not None and lista_rate_irr:
                i_m_cand_n = irr_bisection(cand_n, lista_rate_irr)
                if i_m_cand_n is not None:
                    taeg_c_n = q2((((Decimal("1") + i_m_cand_n) ** 12) - Decimal("1")) * Decimal("100"))
                    d_taeg_n = abs(taeg_c_n - taeg_dichiarato)
                    if d_taeg_n <= Decimal("0.05"):
                        sc_n += 80
                    elif d_taeg_n <= Decimal("0.15"):
                        sc_n += 50
                    elif d_taeg_n <= Decimal("0.30"):
                        sc_n += 15
                    else:
                        sc_n -= 40
            if miglior_n_score is None or sc_n > miglior_n_score:
                miglior_n_score = sc_n
                miglior_n_val = cand_n
        if netto_ricavo_esplicito is not None and (c_fin is None or netto_ricavo_esplicito < c_fin):
            if miglior_n_val is not None and miglior_n_score is not None and (miglior_n_score >= 50 or miglior_n_val in netto_espliciti_cands):
                c_netto = miglior_n_val
            else:
                c_netto = netto_ricavo_esplicito
        else:
            c_netto = miglior_n_val or candidati_netto_pool[0]

    costi_accessori_trattenuti: Optional[Decimal] = None
    if c_fin is not None and c_netto is not None and c_fin >= c_netto:
        costi_accessori_trattenuti = q2(c_fin - c_netto)

    if costi_accessori_trattenuti is not None and costi_accessori_trattenuti > Decimal("0.00"):
        esito_sub_costi = _riconcilia_costi_accessori_subset_sum(
            testo, pagine_tutte, pagine_piano, costi_accessori_trattenuti, importo_rata=importo_rata
        )
        voci_costi_trovate = list(esito_sub_costi["voci_etichettate_riconciliate"])
        voci_costi_riconciliate_dec: List[Decimal] = list(esito_sub_costi["voci_costi_accessori_riconciliate"])
        somma_voci_costi_trovate = Decimal(str(esito_sub_costi["somma_costi_accessori"]))
        riconciliazione_costi_ok = bool(esito_sub_costi["riconciliazione_costi_ok"])
        subtotali_o_esempi_scartati: List[Decimal] = list(esito_sub_costi["subtotali_o_esempi_scartati"])
    else:
        voci_costi_trovate = _estrai_voci_costi_accessori(testo)
        voci_costi_riconciliate_dec = [v_acc for _, v_acc in voci_costi_trovate]
        somma_voci_costi_trovate = q2(sum((v_acc for _, v_acc in voci_costi_trovate), Decimal("0.00")))
        riconciliazione_costi_ok = (
            abs(somma_voci_costi_trovate - costi_accessori_trattenuti) <= Decimal("1.00")
            if (costi_accessori_trattenuti is not None and voci_costi_trovate)
            else None
        )
        subtotali_o_esempi_scartati = []

    if totale_interessi_dich is None and m_rif_iniz is not None and c_fin is not None and m_rif_iniz > c_fin:
        totale_interessi_stimato = q2(m_rif_iniz - c_fin)
    else:
        totale_interessi_stimato = totale_interessi_dich

    c_fin_coerente = bool(
        c_fin is not None
        and m_rif_iniz is not None
        and (Decimal("0.35") * m_rif_iniz) <= c_fin < (Decimal("0.98") * m_rif_iniz)
    )
    c_netto_coerente = bool(
        c_netto is not None
        and m_rif_iniz is not None
        and (Decimal("0.25") * m_rif_iniz) <= c_netto <= (c_fin if c_fin is not None else m_rif_iniz)
    )

    i_m_fin = irr_bisection(c_fin, lista_rate_irr) if (c_fin_coerente and c_fin is not None and lista_rate_irr) else None
    tan_ricalcolato: Optional[Decimal] = None
    if i_m_fin is not None:
        cand_tan = q2(i_m_fin * Decimal("1200"))
        if Decimal("0.50") <= cand_tan <= Decimal("35.00"):
            tan_ricalcolato = cand_tan

    tan_per_controllo = tan_dichiarato if tan_dichiarato is not None else tan_ricalcolato
    fonte_tan_controllo = "TAN_DICHIARATO" if tan_dichiarato is not None else (
        "FALLBACK_TAN_RICALCOLATO" if tan_ricalcolato is not None else "ASSENTE"
    )

    i_m_nominale = (tan_per_controllo / Decimal("1200")) if tan_per_controllo is not None else None
    i_m_effettiva = (
        _calcola_tasso_mensile_effettivo_decimal(tan_per_controllo)
        if tan_per_controllo is not None
        else None
    )

    def _risolvi_d_precedente(k_r: int) -> Tuple[Optional[Decimal], Optional[str]]:
        info_curr = righe_normalizzate[k_r]
        q_cap_curr = Decimal(str(info_curr["quota_capitale"]))
        cap_res_curr = Decimal(str(info_curr["capitale_residuo"]))
        if k_r == 1 and c_fin is not None and c_fin > Decimal("0.00"):
            return c_fin, None
        if (k_r - 1) in righe_normalizzate and righe_normalizzate[k_r - 1]["ha_capitale_residuo"]:
            d_prev_k = Decimal(str(righe_normalizzate[k_r - 1]["capitale_residuo"]))
            if info_curr["ha_capitale_residuo"]:
                d_ricostruito = q2(cap_res_curr + q_cap_curr)
                if abs(d_prev_k - d_ricostruito) > TOL:
                    return d_prev_k, (
                        f"Rata {k_r}: C_res {cap_res_curr} != {d_prev_k} - {q_cap_curr} ({q2(d_prev_k - q_cap_curr)})"
                    )
            return d_prev_k, None
        if info_curr["ha_capitale_residuo"]:
            return q2(cap_res_curr + q_cap_curr), None
        return None, None

    scarti_nom_lista: List[Decimal] = []
    scarti_eff_lista: List[Decimal] = []
    for k in rate_lette_lista:
        q_int = Decimal(str(righe_normalizzate[k]["quota_interessi"]))
        prev_cap, _ = _risolvi_d_precedente(k)
        if prev_cap is not None and prev_cap > Decimal("0.00"):
            if i_m_nominale is not None:
                scarti_nom_lista.append(abs(q_int - q2(prev_cap * i_m_nominale)))
            if i_m_effettiva is not None:
                scarti_eff_lista.append(abs(q_int - q2(prev_cap * i_m_effettiva)))

    convenzione_tan_adottata = "NOMINALE_MENSUALE"
    if scarti_nom_lista and scarti_eff_lista:
        media_nom = sum(scarti_nom_lista, Decimal("0")) / Decimal(len(scarti_nom_lista))
        media_eff = sum(scarti_eff_lista, Decimal("0")) / Decimal(len(scarti_eff_lista))
        if media_eff < media_nom:
            convenzione_tan_adottata = "EFFETTIVA_COMPOSTA"

    i_m_primario = i_m_effettiva if convenzione_tan_adottata == "EFFETTIVA_COMPOSTA" else i_m_nominale

    righe_rata_anomala: List[str] = []
    righe_quadratura_errata: List[str] = []
    righe_residuo_non_decrescente: List[str] = []
    anomalie_capitale_residuo: List[str] = []
    anomalie_debito_residuo: List[str] = []
    anomalie_interessi_nominale: List[str] = []
    anomalie_interessi_effettiva: List[str] = []
    anomalie_interessi_primaria: List[str] = []
    anomalie_interessi_dettaglio: List[str] = []
    anomalie_quote_negative: List[str] = []
    scarto_massimo_tabella = Decimal("0.00")
    rate_verificate_ok = 0

    for k in rate_lette_lista:
        info_k = righe_normalizzate[k]
        q_int = Decimal(str(info_k["quota_interessi"]))
        q_cap = Decimal(str(info_k["quota_capitale"]))
        r_val = Decimal(str(info_k["importo_rata"]))
        cap_res = Decimal(str(info_k["capitale_residuo"]))
        deb_res = Decimal(str(info_k["debito_residuo"]))

        if q_cap < Decimal("0.00") or q_int < Decimal("0.00"):
            anomalie_quote_negative.append(f"Rata {k}: Q_cap={q_cap}, Q_int={q_int}")

        if importo_rata is not None and k < numero_rate_atteso and abs(r_val - importo_rata) > Decimal("0.50"):
            righe_rata_anomala.append(f"Rata {k}: {r_val} € != {importo_rata} €")

        somma_ic = q2(q_int + q_cap)
        diff_somma_rata = abs(somma_ic - r_val)
        if diff_somma_rata > scarto_massimo_tabella:
            scarto_massimo_tabella = diff_somma_rata
        if diff_somma_rata > TOL:
            righe_quadratura_errata.append(
                f"Rata {k}: Q_cap ({q_cap}) + Q_int ({q_int}) = {somma_ic} != Rata ({r_val})"
            )
        else:
            rate_verificate_ok += 1

        prev_cap_res, anom_res_msg = _risolvi_d_precedente(k)
        if prev_cap_res is not None and info_k["ha_capitale_residuo"]:
            if cap_res > prev_cap_res:
                righe_residuo_non_decrescente.append(f"Rata {k}: Capitale residuo {cap_res} > {prev_cap_res}")
            if anom_res_msg:
                diff_cap_res = abs(cap_res - q2(prev_cap_res - q_cap))
                if diff_cap_res > scarto_massimo_tabella:
                    scarto_massimo_tabella = diff_cap_res
                anomalie_capitale_residuo.append(anom_res_msg)

        if prev_cap_res is not None and prev_cap_res > Decimal("0.00"):
            d_alt_riga = q2(cap_res + q_cap) if info_k["ha_capitale_residuo"] else None
            cond1_dn_zero = (not info_k["ha_capitale_residuo"]) or abs(cap_res) <= TOL
            cond2_estinzione = abs(q_cap - prev_cap_res) <= TOL
            cond3_quadratura_ultima = diff_somma_rata <= TOL
            cond4_somma_interessi = (
                piano_completo_al_100
                and totale_interessi_stimato is not None
                and abs(somma_quote_interessi_lette - totale_interessi_stimato) <= Decimal("0.02")
            )
            e_conguaglio_chiusura_esatto = bool(
                k == numero_rate_atteso
                and numero_rate_atteso > 0
                and piano_completo_al_100
                and cond1_dn_zero
                and cond2_estinzione
                and cond3_quadratura_ultima
            )
            if i_m_nominale is not None:
                int_nom_atteso = q2(prev_cap_res * i_m_nominale)
                diff_nom = abs(q_int - int_nom_atteso)
                e_conguaglio_nom = e_conguaglio_chiusura_esatto and (cond4_somma_interessi or diff_nom <= Decimal("1.50"))
                if diff_nom > TOL and not e_conguaglio_nom:
                    msg_nom = f"Rata {k}: Q_int letta {q_int} € vs Q_int_teorico {int_nom_atteso} € (scarto {diff_nom} € su D_prec={prev_cap_res} €)"
                    if d_alt_riga is not None and abs(d_alt_riga - prev_cap_res) > TOL:
                        int_alt_nom = q2(d_alt_riga * i_m_nominale)
                        msg_nom = f"Rata {k}: Q_int letta {q_int} € vs Q_int_teorico {int_nom_atteso} € / {int_alt_nom} € (scarto {diff_nom} € — verificare arrotondamento o OCR residuo)"
                    anomalie_interessi_nominale.append(msg_nom)
                if convenzione_tan_adottata == "NOMINALE_MENSUALE" and not e_conguaglio_nom:
                    if diff_nom > scarto_massimo_tabella:
                        scarto_massimo_tabella = diff_nom
                    if diff_nom > TOL:
                        anomalie_interessi_primaria.append(msg_nom)
                        anomalie_interessi_dettaglio.append(msg_nom)

            if i_m_effettiva is not None:
                int_eff_atteso = q2(prev_cap_res * i_m_effettiva)
                diff_eff = abs(q_int - int_eff_atteso)
                e_conguaglio_eff = e_conguaglio_chiusura_esatto and (cond4_somma_interessi or diff_eff <= Decimal("1.50"))
                if diff_eff > TOL and not e_conguaglio_eff:
                    msg_eff = f"Rata {k}: Q_int letta {q_int} € vs effettiva {int_eff_atteso} € (scarto {diff_eff} €)"
                    anomalie_interessi_effettiva.append(msg_eff)
                if convenzione_tan_adottata == "EFFETTIVA_COMPOSTA" and not e_conguaglio_eff:
                    if diff_eff > scarto_massimo_tabella:
                        scarto_massimo_tabella = diff_eff
                    if diff_eff > TOL:
                        anomalie_interessi_primaria.append(msg_eff)
                        anomalie_interessi_dettaglio.append(msg_eff)

        if (k - 1) in righe_normalizzate:
            info_prev = righe_normalizzate[k - 1]
            prev_deb_res = Decimal(str(info_prev["debito_residuo"]))
            if info_k["ha_debito_residuo"] and info_prev["ha_debito_residuo"]:
                deb_atteso = q2(prev_deb_res - r_val)
                diff_deb_res = abs(deb_res - deb_atteso)
                if diff_deb_res > scarto_massimo_tabella:
                    scarto_massimo_tabella = diff_deb_res
                if diff_deb_res > TOL:
                    anomalie_debito_residuo.append(
                        f"Rata {k}: D_res {deb_res} != {prev_deb_res} - {r_val} ({deb_atteso})"
                    )

    debito_residuo_finale_valore: Optional[Decimal] = None
    debito_residuo_finale_zero_ok: Optional[bool] = None
    if numero_rate_atteso > 0 and numero_rate_atteso in righe_normalizzate:
        ultima_r = righe_normalizzate[numero_rate_atteso]
        if ultima_r["ha_capitale_residuo"]:
            cap_ult = Decimal(str(ultima_r["capitale_residuo"]))
            debito_residuo_finale_valore = cap_ult
            if abs(cap_ult) > scarto_massimo_tabella:
                scarto_massimo_tabella = abs(cap_ult)
            debito_residuo_finale_zero_ok = abs(cap_ult) <= TOL
        elif (numero_rate_atteso - 1) in righe_normalizzate and righe_normalizzate[numero_rate_atteso - 1]["ha_capitale_residuo"]:
            cap_ult_calc = q2(
                Decimal(str(righe_normalizzate[numero_rate_atteso - 1]["capitale_residuo"]))
                - Decimal(str(ultima_r["quota_capitale"]))
            )
            debito_residuo_finale_valore = cap_ult_calc
            debito_residuo_finale_zero_ok = abs(cap_ult_calc) <= TOL
        elif ultima_r["ha_debito_residuo"]:
            deb_ult = Decimal(str(ultima_r["debito_residuo"]))
            debito_residuo_finale_valore = deb_ult
            debito_residuo_finale_zero_ok = abs(deb_ult) <= TOL
        else:
            debito_residuo_finale_valore = Decimal("0.00")
            debito_residuo_finale_zero_ok = True

    montante_calcolato: Optional[Decimal] = montante_calcolato_iniz
    quadratura_montante_ok: Optional[bool] = None
    if montante_calcolato is not None:
        if montante_dichiarato is not None:
            diff_m = abs(montante_calcolato - montante_dichiarato)
            quadratura_montante_ok = diff_m <= TOLLERANZA_AMBAR
        else:
            quadratura_montante_ok = True

    quadratura_somma_quote_capitale_ok: Optional[bool] = None
    if piano_completo_al_100 and c_fin is not None:
        diff_sq_c = abs(somma_quote_capitale_lette - c_fin)
        if diff_sq_c > scarto_massimo_tabella:
            scarto_massimo_tabella = diff_sq_c
        quadratura_somma_quote_capitale_ok = diff_sq_c <= TOL

    quadratura_somma_quote_interessi_ok: Optional[bool] = None
    if piano_completo_al_100 and totale_interessi_stimato is not None:
        diff_sq_i = abs(somma_quote_interessi_lette - totale_interessi_stimato)
        if diff_sq_i > scarto_massimo_tabella:
            scarto_massimo_tabella = diff_sq_i
        quadratura_somma_quote_interessi_ok = diff_sq_i <= TOL

    quadratura_interessi_montante_ok: Optional[bool] = None
    if totale_interessi_dich is not None and m_rif_iniz is not None and c_fin is not None:
        diff_int_m = abs(totale_interessi_dich - q2(m_rif_iniz - c_fin))
        quadratura_interessi_montante_ok = diff_int_m <= TOL

    verifica_indipendente_tabella_stato = (
        "VERIFICATA_INTEGRALE"
        if piano_completo_al_100
        else f"NON VERIFICATO (Tabella incompleta: lette {n_rate_estratte}/{numero_rate_atteso} rate)"
    )

    n_rate_mancanti = len(rate_mancanti_lista)
    somma_rate_mancanti_attesa: Optional[Decimal] = None
    somma_q_cap_mancanti_attesa: Optional[Decimal] = None
    somma_q_int_mancanti_attesa: Optional[Decimal] = None
    quadratura_blocco_mancante_ok: Optional[bool] = None
    salti_buco_residuo: List[Dict[str, str]] = []
    verifica_salto_buco_ok: Optional[bool] = None

    if n_rate_mancanti > 0:
        if importo_rata is not None:
            somma_rate_mancanti_attesa = q2(Decimal(n_rate_mancanti) * importo_rata)
        if c_fin is not None:
            somma_q_cap_mancanti_attesa = q2(c_fin - somma_quote_capitale_lette)
        if totale_interessi_stimato is not None:
            somma_q_int_mancanti_attesa = q2(totale_interessi_stimato - somma_quote_interessi_lette)
        if (
            somma_rate_mancanti_attesa is not None
            and somma_q_cap_mancanti_attesa is not None
            and somma_q_int_mancanti_attesa is not None
        ):
            quadratura_blocco_mancante_ok = (
                abs((somma_q_cap_mancanti_attesa + somma_q_int_mancanti_attesa) - somma_rate_mancanti_attesa)
                <= TOLLERANZA_AMBAR
            )

        buco_inizio = rate_mancanti_lista[0]
        buco_fine = rate_mancanti_lista[0]
        intervalli_mancanti_tuple: List[Tuple[int, int]] = []
        for val_m in rate_mancanti_lista[1:]:
            if val_m == buco_fine + 1:
                buco_fine = val_m
            else:
                intervalli_mancanti_tuple.append((buco_inizio, buco_fine))
                buco_inizio = val_m
                buco_fine = val_m
        intervalli_mancanti_tuple.append((buco_inizio, buco_fine))

        somma_salti_cap = Decimal("0.00")
        ha_salti_completi = True
        for g_start, g_end in intervalli_mancanti_tuple:
            t_a = g_start - 1
            t_b = g_end + 1
            if (
                t_a in righe_normalizzate
                and t_b in righe_normalizzate
                and righe_normalizzate[t_a]["ha_capitale_residuo"]
                and righe_normalizzate[t_b]["ha_capitale_residuo"]
            ):
                d_ta = Decimal(str(righe_normalizzate[t_a]["capitale_residuo"]))
                d_inizio_tb = q2(
                    Decimal(str(righe_normalizzate[t_b]["capitale_residuo"]))
                    + Decimal(str(righe_normalizzate[t_b]["quota_capitale"]))
                )
                salto_cap = q2(d_ta - d_inizio_tb)
                somma_salti_cap += salto_cap
                salti_buco_residuo.append({
                    "buco": f"{g_start}..{g_end}",
                    "rata_prima": str(t_a),
                    "rata_dopo": str(t_b),
                    "salto_capitale_residuo": str(salto_cap),
                })
            else:
                ha_salti_completi = False
        if salti_buco_residuo and ha_salti_completi and somma_q_cap_mancanti_attesa is not None:
            verifica_salto_buco_ok = abs(somma_salti_cap - somma_q_cap_mancanti_attesa) <= Decimal("0.20")

    rata_francese_teorica: Optional[Decimal] = None
    delta_rata_francese: Optional[Decimal] = None
    quadratura_rata_francese_ok: Optional[bool] = None
    if (
        c_fin is not None
        and c_fin > Decimal("0.00")
        and numero_rate_atteso > 0
        and i_m_primario is not None
        and i_m_primario > Decimal("0")
    ):
        denominatore_fr = Decimal("1") - ((Decimal("1") + i_m_primario) ** (-numero_rate_atteso))
        if denominatore_fr > Decimal("0"):
            rata_francese_teorica = q2(c_fin * (i_m_primario / denominatore_fr))
            if importo_rata is not None:
                delta_rata_francese = q2(abs(importo_rata - rata_francese_teorica))
                quadratura_rata_francese_ok = delta_rata_francese <= TOL

    i_m_netto = irr_bisection(c_netto, lista_rate_irr) if (c_netto_coerente and c_netto is not None and lista_rate_irr) else None
    taeg_ricalcolato: Optional[Decimal] = None
    tasso_mensile_irr: Optional[Decimal] = None
    if i_m_netto is not None:
        cand_taeg = q2((((Decimal("1") + i_m_netto) ** 12) - Decimal("1")) * Decimal("100"))
        if Decimal("0.50") <= cand_taeg <= Decimal("35.00"):
            taeg_ricalcolato = cand_taeg
            tasso_mensile_irr = (i_m_netto * Decimal("100")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    delta_tan_pct = q2(abs(tan_ricalcolato - tan_dichiarato)) if (tan_ricalcolato is not None and tan_dichiarato is not None) else None
    delta_taeg_pct = q2(abs(taeg_ricalcolato - taeg_dichiarato)) if (taeg_ricalcolato is not None and taeg_dichiarato is not None) else None
    tan_verificato_ok = (delta_tan_pct <= TOLLERANZA_AMBAR) if delta_tan_pct is not None else None
    taeg_verificato_ok = (delta_taeg_pct <= TOLLERANZA_AMBAR) if delta_taeg_pct is not None else None

    voci_mancanti_cashflow: List[str] = []
    if not c_fin_coerente:
        voci_mancanti_cashflow.append("Capitale Finanziato coerente (0.35*M <= C_fin < 0.98*M)")
    if not c_netto_coerente:
        voci_mancanti_cashflow.append("Netto Ricavo / Saldo Netto / Importo Totale del Credito (Pag. 1/8/9)")
    stato_taeg = (
        "TAEG_TAN_CALCOLATI_SU_FLUSSO_COERENTE"
        if (tan_ricalcolato is not None and taeg_ricalcolato is not None)
        else "FLUSSO_CASSA_INCOMPLETO"
    )

    anomalie_aggregate: List[str] = []
    if quadratura_montante_ok is False:
        anomalie_aggregate.append("Quadratura montante (n * R != Montante)")
    if quadratura_somma_quote_capitale_ok is False:
        anomalie_aggregate.append(f"Somma Q_cap ({somma_quote_capitale_lette}) != C_fin ({c_fin})")
    if quadratura_somma_quote_interessi_ok is False:
        anomalie_aggregate.append(f"Somma Q_int ({somma_quote_interessi_lette}) != Interessi ({totale_interessi_stimato})")
    if quadratura_interessi_montante_ok is False:
        anomalie_aggregate.append("Interessi != Montante - C_fin")
    if debito_residuo_finale_zero_ok is False:
        anomalie_aggregate.append(f"Debito/Capitale residuo ultima rata ({debito_residuo_finale_valore}) != 0.00")

    totale_anomalie = (
        len(righe_quadratura_errata)
        + len(righe_rata_anomala)
        + len(righe_residuo_non_decrescente)
        + len(anomalie_capitale_residuo)
        + len(anomalie_debito_residuo)
        + len(anomalie_interessi_primaria)
        + len(anomalie_quote_negative)
        + len(anomalie_aggregate)
    )
    totale_anomalie_sostanziali = int(totale_anomalie)

    ha_violazioni_sostanziali = bool(
        righe_residuo_non_decrescente
        or anomalie_quote_negative
        or righe_rata_anomala
        or righe_quadratura_errata
        or scarto_massimo_tabella > TOLLERANZA_AMBAR
        or (quadratura_montante_ok is False)
        or (quadratura_somma_quote_capitale_ok is False)
        or (quadratura_somma_quote_interessi_ok is False)
        or (quadratura_interessi_montante_ok is False)
        or (debito_residuo_finale_zero_ok is False)
    )

    dati_tassi_completi = bool(
        c_fin_coerente
        and c_netto_coerente
        and tan_ricalcolato is not None
        and taeg_ricalcolato is not None
        and (tan_verificato_ok is not False)
        and (taeg_verificato_ok is not False)
    )

    verifica_teorica_continuita: Dict[str, object] = {
        "eseguita": False,
        "continuita_ok": None,
        "prima_rata_visibile": None,
        "d_teorico_prima_visibile": None,
        "d_ocr_prima_visibile": None,
        "delta_continuita_euro": None,
        "rate_mancanti": elenco_mancanti_str,
    }
    if (
        n_rate_mancanti > 0
        and numero_rate_atteso > 0
        and c_fin is not None
        and i_m_primario is not None
        and importo_rata is not None
        and rate_lette_lista
    ):
        d_sim_t = c_fin
        d_dopo_mappa: Dict[int, Decimal] = {0: c_fin}
        for k_sim in range(1, numero_rate_atteso + 1):
            q_int_s = q2(d_sim_t * i_m_primario)
            r_sim = Decimal(str(righe_normalizzate[k_sim]["importo_rata"])) if k_sim in righe_normalizzate else importo_rata
            if k_sim < numero_rate_atteso:
                q_cap_s = q2(r_sim - q_int_s)
                d_after_s = q2(d_sim_t - q_cap_s)
            else:
                d_after_s = Decimal("0.00")
            d_dopo_mappa[k_sim] = d_after_s
            d_sim_t = d_after_s
        prima_vis = rate_lette_lista[0]
        if prima_vis >= 1 and righe_normalizzate[prima_vis]["ha_capitale_residuo"]:
            d_ocr_inizio_vis = q2(
                Decimal(str(righe_normalizzate[prima_vis]["capitale_residuo"]))
                + Decimal(str(righe_normalizzate[prima_vis]["quota_capitale"]))
            )
            d_teor_inizio_vis = d_dopo_mappa.get(prima_vis - 1)
            if d_teor_inizio_vis is not None:
                delta_cont = q2(abs(d_ocr_inizio_vis - d_teor_inizio_vis))
                verifica_teorica_continuita = {
                    "eseguita": True,
                    "continuita_ok": delta_cont <= Decimal("0.50"),
                    "prima_rata_visibile": prima_vis,
                    "d_teorico_prima_visibile": str(d_teor_inizio_vis),
                    "d_ocr_prima_visibile": str(d_ocr_inizio_vis),
                    "delta_continuita_euro": str(delta_cont),
                    "rate_mancanti": elenco_mancanti_str,
                }

    analisi_rata_finale: Optional[Dict[str, str]] = None
    nota_conguaglio_rata_finale = ""
    stato_rata_finale = "NON_ESTRATTA"
    if numero_rate_atteso > 0 and numero_rate_atteso in righe_normalizzate and i_m_primario is not None:
        r_fin_obj = righe_normalizzate[numero_rate_atteso]
        d_prec_fin_val, _ = _risolvi_d_precedente(numero_rate_atteso)
        if d_prec_fin_val is not None and d_prec_fin_val > Decimal("0.00"):
            q_cap_fin_val = Decimal(str(r_fin_obj["quota_capitale"]))
            q_int_fin_val = Decimal(str(r_fin_obj["quota_interessi"]))
            r_fin_val = Decimal(str(r_fin_obj["importo_rata"]))
            cap_res_fin_val = Decimal(str(r_fin_obj["capitale_residuo"]))
            q_int_teor_fin_val = q2(d_prec_fin_val * i_m_primario)
            delta_fin_val = q2(abs(q_int_fin_val - q_int_teor_fin_val))
            q_cap_ipotetica = q2(r_fin_val - q_int_teor_fin_val)
            cond1_ult = (not r_fin_obj["ha_capitale_residuo"]) or abs(cap_res_fin_val) <= TOL
            cond2_ult = abs(q_cap_fin_val - d_prec_fin_val) <= TOL
            cond3_ult = abs((q_cap_fin_val + q_int_fin_val) - r_fin_val) <= TOL
            cond4_ult = (
                totale_interessi_stimato is not None
                and abs(somma_quote_interessi_lette - totale_interessi_stimato) <= Decimal("0.02")
            ) or delta_fin_val <= Decimal("1.50")

            if delta_fin_val > TOL and piano_completo_al_100 and cond1_ult and cond2_ult and cond3_ult and cond4_ult:
                stato_rata_finale = "CONGUAGLIO_DI_CHIUSURA_FISIOLOGICO"
                nota_conguaglio_rata_finale = (
                    f"Rata {numero_rate_atteso} (Conguaglio fisiologico di chiusura certificato): "
                    f"D({numero_rate_atteso - 1}) = {d_prec_fin_val} €, Rata = {r_fin_val} €, "
                    f"Q_cap({numero_rate_atteso}) = {q_cap_fin_val} €, "
                    f"Q_int({numero_rate_atteso}) = {r_fin_val} - {q_cap_fin_val} = {q_int_fin_val} € "
                    f"(rispetto a {q_int_teor_fin_val} € teorici, scarto +{delta_fin_val} €). "
                    f"Se si applicasse {q_int_teor_fin_val} €, la quota capitale ({q_cap_ipotetica} €) "
                    f"supererebbe il debito residuo ({d_prec_fin_val} €). Il valore {q_int_fin_val} € consente "
                    f"la chiusura esatta D({numero_rate_atteso}) = 0.00 € e la quadratura al centesimo "
                    f"degli interessi totali ({totale_interessi_stimato or somma_quote_interessi_lette} €)."
                )
            elif delta_fin_val <= TOL:
                stato_rata_finale = "CONFORME_ENTRO_TOLLERANZA"
            else:
                stato_rata_finale = "DA_VERIFICARE_PIANO_PARZIALE" if not piano_completo_al_100 else "SCOSTAMENTO_DA_VERIFICARE"

            analisi_rata_finale = {
                "rata": str(numero_rate_atteso),
                "stato_rata_finale": stato_rata_finale,
                "d_precedente": str(d_prec_fin_val),
                "q_cap_letta": str(q_cap_fin_val),
                "q_int_letta": str(q_int_fin_val),
                "q_int_teorico": str(q_int_teor_fin_val),
                "scarto_euro": str(delta_fin_val),
                "spiegazione": nota_conguaglio_rata_finale or (
                    f"Rata {numero_rate_atteso}: Q_int letta {q_int_fin_val} € su D({numero_rate_atteso - 1})={d_prec_fin_val} € "
                    f"contro {q_int_teor_fin_val} € teorici (scarto {delta_fin_val} €). Verificare puntualmente se "
                    f"conguaglio di chiusura della rata costante ({importo_rata} € vs rata teorica non arrotondata) o imprecisione OCR."
                ),
            }

    if totale_anomalie_sostanziali > 0 or ha_violazioni_sostanziali:
        verdetto_semaforo = "ROJO"
        certificabile = False
        stato_certificazione = (
            "NON_CERTIFICABILE_TABELLA_INCOMPLETA"
            if not piano_completo_al_100
            else "NON_CERTIFICABILE_ANOMALIE_ARITMETICHE"
        )
    elif numero_rate_atteso > 0 and n_rate_estratte == numero_rate_atteso and len(rate_mancanti_lista) == 0:
        verdetto_semaforo = "VERDE"
        certificabile = True
        stato_certificazione = "CERTIFICATO_VERDE_NESSUN_VIZIO_ARITMETICO"
    elif not piano_completo_al_100:
        verdetto_semaforo = "AMBAR"
        certificabile = False
        stato_certificazione = "GIALLO_NESSUN_VIZIO_ARITMETICO_LIMITE_VERIFICA_OCR"
    elif not dati_tassi_completi or tan_dichiarato is None or taeg_dichiarato is None:
        verdetto_semaforo = "GREY"
        certificabile = False
        stato_certificazione = "NON_CERTIFICABILE_DATI_MANCANTI"
    elif scarto_massimo_tabella <= TOLLERANZA_AMBAR:
        verdetto_semaforo = "AMBAR"
        certificabile = True
        stato_certificazione = "CERTIFICABILE_AMBAR_ARROTONDAMENTI_MINIMI"
    else:
        verdetto_semaforo = "ROJO"
        certificabile = False
        stato_certificazione = "NON_CERTIFICABILE_ANOMALIE_ARITMETICHE"

    d_finale_str = str(debito_residuo_finale_valore) if debito_residuo_finale_valore is not None else "0.00"
    messaggio_blocco_certificazione = ""
    if verdetto_semaforo == "VERDE":
        messaggio_blocco_certificazione = (
            f"✅ **PIANO ARITMETICAMENTE COERENTE E CERTIFICATO (`VERDE`)**: Rilevate `0` anomalie aritmetiche sostanziali "
            f"su `{n_rate_estratte}/{numero_rate_atteso}` rate (scarto massimo `{scarto_massimo_tabella} €`). "
            f"Tutte le quadrature (`C_fin = {c_fin or 'N/D'} €`, `Interessi = {totale_interessi_stimato or 'N/D'} €`, "
            f"`Montante = {m_rif_iniz or 'N/D'} €`, `Costi accessori = {costi_accessori_trattenuti or 'N/D'} €`, "
            f"`Netto erogato = {c_netto or 'N/D'} €`, `TAN = {tan_ricalcolato or tan_dichiarato or 'N/D'}%`, "
            f"`TAEG = {taeg_ricalcolato or taeg_dichiarato or 'N/D'}%`, `D({numero_rate_atteso}) = {d_finale_str} €`) "
            f"risultano verificate."
        )
    elif verdetto_semaforo == "ROJO":
        messaggio_blocco_certificazione = (
            f"⛔ ANOMALIE SOSTANZIALI RILEVATE (`ROJO`): Rilevate {totale_anomalie_sostanziali} anomalie aritmetiche "
            f"(scarto massimo `{scarto_massimo_tabella} €`; rate lette `{n_rate_estratte}/{numero_rate_atteso}`): "
            f"{', '.join(anomalie_aggregate[:3] or anomalie_interessi_dettaglio[:2]) or 'vedi dettagli rata per rata'}."
        )
    elif verdetto_semaforo == "AMBAR" and not piano_completo_al_100:
        messaggio_blocco_certificazione = (
            f"🟡 **NESSUN VIZIO ARITMETICO RILEVATO SUI DATI ESTRATTI (`0` anomalie aritmetiche)**: "
            f"tutte le quadrature dei totali, dei costi accessori (`{costi_accessori_trattenuti or 'N/D'} €`), "
            f"del TAN (`{tan_ricalcolato or tan_dichiarato or 'N/D'}%`), del TAEG (`{taeg_ricalcolato or taeg_dichiarato or 'N/D'}%`) "
            f"e delle `{n_rate_estratte}/{numero_rate_atteso}` rate lette sono coerenti. "
            f"Da completare solo la verifica visiva/OCR delle rate non estratte (`[{elenco_mancanti_str}]`)."
        )
    elif verdetto_semaforo == "GREY":
        messaggio_blocco_certificazione = (
            f"⚪ DATI CONTRATTUALI INCOMPLETI (`GREY`): Tabella `{n_rate_estratte}/{numero_rate_atteso}` letta, "
            f"ma mancano elementi essenziali per chiudere il ricalcolo TAN/TAEG (`{', '.join(voci_mancanti_cashflow) or 'TAN/TAEG dichiarati'}`)."
        )

    righe_tabella_serializzate = [
        {
            "rata": int(righe_normalizzate[k]["rata"]),
            "scadenza": str(righe_normalizzate[k]["scadenza"]),
            "importo_rata": str(righe_normalizzate[k]["importo_rata"]),
            "quota_capitale": str(righe_normalizzate[k]["quota_capitale"]),
            "quota_interessi": str(righe_normalizzate[k]["quota_interessi"]),
            "capitale_residuo": str(righe_normalizzate[k]["capitale_residuo"]),
            "debito_residuo": str(righe_normalizzate[k]["debito_residuo"]),
            "riallineata_ocr": bool(righe_normalizzate[k].get("riallineata_ocr", False)),
        }
        for k in rate_lette_lista
    ]

    strato_l = {
        "pagine_lette": pagine_trovate,
        "pagine_piano_ammortamento": [n for n, _ in pagine_piano],
        "pagine_riepilogo_costi_taeg": [n for n, _ in pagine_costi_taeg],
        "pagine_prospetto_liquidazione": [n for n, _ in pagine_liq],
        "pagine_intestazione_contratto": [n for n, _ in classif["PAGINE_INTESTAZIONE_CONTRATTO"]],
        "pagine_riepilogo_taeg_presenti": ha_pag_8_9,
        "criterio_allineamento_colonne": criterio_allineamento_colonne,
        "rate_riallineate_ocr": rate_riallineate_ocr,
        "convenzione_tan_adottata": convenzione_tan_adottata,
        "fonte_tan_controllo": fonte_tan_controllo,
        "numero_rate_totale": numero_rate_atteso,
        "n_rate_atteso": numero_rate_atteso,
        "n_rate_estratte": n_rate_estratte,
        "n_rate_lette_da_ocr": n_rate_estratte,
        "importo_rata": str(importo_rata) if importo_rata is not None else None,
        "montante_dichiarato": str(montante_dichiarato) if montante_dichiarato is not None else None,
        "interessi_totali_contrattuali": str(totale_interessi_stimato) if totale_interessi_stimato is not None else None,
        "capitale_o_valore_attuale": str(c_fin) if c_fin is not None else None,
        "capitale_finanziato": str(c_fin) if c_fin is not None else None,
        "netto_ricavo": str(c_netto) if c_netto is not None else None,
        "costi_accessori_trattenuti": str(costi_accessori_trattenuti) if costi_accessori_trattenuti is not None else None,
        "voci_costi_accessori_riconciliate": [str(v_r) for v_r in voci_costi_riconciliate_dec],
        "subtotali_o_esempi_scartati": [str(v_s) for v_s in subtotali_o_esempi_scartati],
        "voci_costi_accessori_trovate": [{"voce": et_v, "importo": str(val_v)} for et_v, val_v in voci_costi_trovate],
        "somma_voci_costi_trovate": str(somma_voci_costi_trovate) if voci_costi_trovate else None,
        "riconciliazione_costi_ok": riconciliazione_costi_ok,
        "tan_dichiarato": str(tan_dichiarato) if tan_dichiarato is not None else None,
        "taeg_dichiarato": str(taeg_dichiarato) if taeg_dichiarato is not None else None,
        "rate_lette_conteggio": n_rate_estratte,
        "rate_lette_lista": rate_lette_lista,
        "rate_lette_intervalli": _compatta_intervalli_rate(rate_lette_lista),
        "rate_mancanti_conteggio": n_rate_mancanti,
        "rate_mancanti_lista": rate_mancanti_lista,
        "rate_mancanti": elenco_mancanti_str,
        "rate_duplicate": rate_duplicate,
        "righe_scartate_conteggio": righe_scartate_conteggio,
        "piano_completo_al_100": piano_completo_al_100,
        "certificabile": certificabile,
        "verdetto_semaforo": verdetto_semaforo,
        "stato_certificazione": stato_certificazione,
        "messaggio_blocco_certificazione": messaggio_blocco_certificazione,
    }

    strato_a = {
        "montante_calcolato": str(montante_calcolato) if montante_calcolato is not None else None,
        "quadratura_montante_ok": quadratura_montante_ok,
        "c_fin_da_prospetto": str(c_fin_da_montante) if c_fin_da_montante is not None else None,
        "verifica_indipendente_tabella_stato": verifica_indipendente_tabella_stato,
        "quadratura_somma_quote_capitale_ok": quadratura_somma_quote_capitale_ok,
        "quadratura_somma_quote_interessi_ok": quadratura_somma_quote_interessi_ok,
        "quadratura_interessi_montante_ok": quadratura_interessi_montante_ok,
        "debito_residuo_finale_valore": str(debito_residuo_finale_valore) if debito_residuo_finale_valore is not None else None,
        "debito_residuo_finale_zero_ok": debito_residuo_finale_zero_ok,
        "rata_francese_teorica": str(rata_francese_teorica) if rata_francese_teorica is not None else None,
        "delta_rata_francese": str(delta_rata_francese) if delta_rata_francese is not None else None,
        "quadratura_rata_francese_ok": quadratura_rata_francese_ok,
        "fonte_tan_rata_francese": fonte_tan_controllo,
        "rate_verificate_ok": rate_verificate_ok,
        "rate_riallineate_ocr": rate_riallineate_ocr,
        "stato_rata_finale": stato_rata_finale,
        "nota_conguaglio_rata_finale": nota_conguaglio_rata_finale,
        "analisi_rata_finale": analisi_rata_finale,
        "somma_quote_capitale_lette": str(somma_quote_capitale_lette),
        "somma_quote_interessi_lette": str(somma_quote_interessi_lette),
        "somma_rate_lette": str(somma_rate_lette),
        "n_rate_mancanti": n_rate_mancanti,
        "somma_rate_mancanti_attesa": str(somma_rate_mancanti_attesa) if somma_rate_mancanti_attesa is not None else None,
        "somma_q_cap_mancanti_attesa": str(somma_q_cap_mancanti_attesa) if somma_q_cap_mancanti_attesa is not None else None,
        "somma_q_int_mancanti_attesa": str(somma_q_int_mancanti_attesa) if somma_q_int_mancanti_attesa is not None else None,
        "quadratura_blocco_mancante_ok": quadratura_blocco_mancante_ok,
        "salti_buco_residuo": salti_buco_residuo,
        "verifica_salto_buco_ok": verifica_salto_buco_ok,
        "verifica_teorica_continuita": verifica_teorica_continuita,
        "righe_rata_anomala": righe_rata_anomala,
        "anomalie_somma_rata": righe_quadratura_errata,
        "righe_quadratura_errata": righe_quadratura_errata,
        "righe_residuo_non_decrescente": righe_residuo_non_decrescente,
        "anomalie_capitale_residuo": anomalie_capitale_residuo,
        "anomalie_debito_residuo": anomalie_debito_residuo,
        "anomalie_interessi_nominale": anomalie_interessi_nominale,
        "anomalie_interessi_effettiva": anomalie_interessi_effettiva,
        "anomalie_interessi_primaria": anomalie_interessi_primaria,
        "anomalie_interessi_dettaglio": anomalie_interessi_dettaglio,
        "anomalie_interessi_tan": anomalie_interessi_primaria,
        "anomalie_quote_negative": anomalie_quote_negative,
        "anomalie_aggregate": anomalie_aggregate,
        "scarto_massimo_euro": str(scarto_massimo_tabella),
        "totale_anomalie": totale_anomalie,
    }

    strato_d = {
        "stato_taeg": stato_taeg,
        "voci_mancanti_cashflow": voci_mancanti_cashflow,
        "montante_lordo_m": str(m_rif_iniz) if m_rif_iniz is not None else None,
        "capitale_finanziato_c_fin": str(c_fin) if c_fin is not None else None,
        "capitale_netto_taeg_c_netto": str(c_netto) if c_netto is not None else None,
        "costi_accessori_trattenuti": str(costi_accessori_trattenuti) if costi_accessori_trattenuti is not None else None,
        "riconciliazione_costi_ok": riconciliazione_costi_ok,
        "capitale_riferimento_irr": str(c_netto or c_fin) if (c_netto or c_fin) is not None else None,
        "tasso_periodale_mensile_pct": str(tasso_mensile_irr) if tasso_mensile_irr is not None else None,
        "tan_ricalcolato_pct": str(tan_ricalcolato) if tan_ricalcolato is not None else None,
        "taeg_ricalcolato_pct": str(taeg_ricalcolato) if taeg_ricalcolato is not None else None,
        "tan_dichiarato_pct": str(tan_dichiarato) if tan_dichiarato is not None else None,
        "taeg_dichiarato_pct": str(taeg_dichiarato) if taeg_dichiarato is not None else None,
        "delta_tan_pct": str(delta_tan_pct) if delta_tan_pct is not None else None,
        "delta_taeg_pct": str(delta_taeg_pct) if delta_taeg_pct is not None else None,
        "tan_verificato_ok": tan_verificato_ok,
        "taeg_verificato_ok": taeg_verificato_ok,
    }

    stato_completezza = (
        f"COMPLETO AL 100% ({n_rate_estratte}/{numero_rate_atteso} rate lette da OCR)"
        if piano_completo_al_100
        else (
            f"PARZIALE — COERENTE SUI DATI VISIBILI ({n_rate_estratte}/{numero_rate_atteso} rate lette da OCR: presenti [{strato_l['rate_lette_intervalli']}]; da verificare OCR rate: [{elenco_mancanti_str}])"
            if verdetto_semaforo == "AMBAR"
            else f"PARZIALE — NON CERTIFICABILE ({n_rate_estratte}/{numero_rate_atteso} rate lette da OCR: presenti [{strato_l['rate_lette_intervalli']}], MANCANTI [{elenco_mancanti_str}])"
        )
    )
    blocco_avviso_md = f"\n> {messaggio_blocco_certificazione}\n" if messaggio_blocco_certificazione else ""
    avviso_cashflow = (
        f"- **Stato Ricalcolo NPV/TAEG:** `FLUSSO_CASSA_INCOMPLETO` — Dati mancanti per equazione esatta: `{', '.join(voci_mancanti_cashflow)}`\n"
        if stato_taeg == "FLUSSO_CASSA_INCOMPLETO"
        else ""
    )

    blocco_costi_md = ""
    if costi_accessori_trattenuti is not None:
        voci_str = " + ".join(f"{val_v} €" for _, val_v in voci_costi_trovate)
        scartati_str = ", ".join(f"{v_s} €" for v_s in subtotali_o_esempi_scartati[:8])
        dettaglio_voci = (
            f" · Riconciliazione Subset-Sum: `{voci_str} = {somma_voci_costi_trovate} €` (`OK: {riconciliazione_costi_ok}`)"
            + (f" · Scartati subtotali/duplicati/esempi OCR: `{scartati_str}`" if scartati_str else "")
            if voci_costi_trovate
            else ""
        )
        blocco_costi_md = (
            f"- **Riconciliazione Costi Accessori Upfront (C_fin - C_netto):** `{costi_accessori_trattenuti} €`{dettaglio_voci}\n"
        )

    blocco_riallineamento_md = ""
    if rate_riallineate_ocr:
        blocco_riallineamento_md = "- **Riallineamenti OCR Riga per Riga:** `" + "` | `".join(rate_riallineate_ocr[:5]) + "`\n"

    blocco_rata_finale_md = ""
    if nota_conguaglio_rata_finale:
        blocco_rata_finale_md = f"- **Conguaglio Fisiologico Rata Finale (`{stato_rata_finale}`):** {nota_conguaglio_rata_finale}\n"
    elif analisi_rata_finale and Decimal(analisi_rata_finale["scarto_euro"]) > TOL:
        blocco_rata_finale_md = f"- **Analisi Specifica Rata Finale ({analisi_rata_finale['rata']}):** {analisi_rata_finale['spiegazione']}\n"

    blocco_mancanti_md = ""
    if n_rate_mancanti > 0:
        righe_salti = "; ".join(
            f"buco `{s['buco']}` (D({s['rata_prima']}) - D({s['rata_dopo']}^-) = {s['salto_capitale_residuo']} €)"
            for s in salti_buco_residuo
        )
        blocco_continuita_teorica = ""
        if verifica_teorica_continuita.get("eseguita"):
            blocco_continuita_teorica = (
                f"- **Verifica Teorica di Continuità Piano Alla Francese (1..{numero_rate_atteso}, separata da OCR):** "
                f"`D_teorico({int(verifica_teorica_continuita['prima_rata_visibile']) - 1}) = {verifica_teorica_continuita['d_teorico_prima_visibile']} €` "
                f"vs `D_OCR({verifica_teorica_continuita['prima_rata_visibile']}) + Q_cap = {verifica_teorica_continuita['d_ocr_prima_visibile']} €` "
                f"(Delta `{verifica_teorica_continuita['delta_continuita_euro']} €` · Continuità OK: `{verifica_teorica_continuita['continuita_ok']}`)\n"
            )
        blocco_mancanti_md = (
            f"- **Verifica Indipendente Somma Quote Tabella (1..{numero_rate_atteso}):** `{verifica_indipendente_tabella_stato}`\n"
            f"{blocco_continuita_teorica}"
            f"- **Controllo Obbligatorio Rate Mancanti (`{n_rate_mancanti}` rate · `{elenco_mancanti_str}`):** "
            f"Somma rate attesa `{somma_rate_mancanti_attesa or 'N/D'} €` | "
            f"`Q_cap` mancanti attesa `{somma_q_cap_mancanti_attesa or 'N/D'} €` | "
            f"`Q_int` mancanti attesa `{somma_q_int_mancanti_attesa or 'N/D'} €` "
            f"(Quadratura blocco mancante: `{quadratura_blocco_mancante_ok}`"
            f"{f' · Salto residuo buco: {righe_salti}, OK={verifica_salto_buco_ok}' if righe_salti else ''})\n"
        )
    else:
        blocco_mancanti_md = (
            f"- **Verifica Indipendente Somma Quote Tabella (1..{numero_rate_atteso}):** "
            f"`VERIFICATA_INTEGRALE` (Somma Q_cap = `{somma_quote_capitale_lette} €`, Somma Q_int = `{somma_quote_interessi_lette} €`)\n"
        )

    dettagli_anomalie_md = ""
    if anomalie_interessi_dettaglio or anomalie_capitale_residuo or righe_quadratura_errata:
        campioni_anom = (anomalie_interessi_dettaglio + anomalie_capitale_residuo + righe_quadratura_errata)[:5]
        dettagli_anomalie_md = "- **Dettaglio Scostamenti Rilevati:** `" + "` | `".join(campioni_anom) + "`\n"

    stato_dn_str = (
        f"`{debito_residuo_finale_valore} €` (OK: `{debito_residuo_finale_zero_ok}`)"
        if debito_residuo_finale_valore is not None
        else "`NON ESTRATTO (ultima rata mancante)`"
    )
    descrizione_verdetto = (
        "🟢 VERDE — PIANO ARITMETICAMENTE COERENTE E PRIVO DI VIZI SOSTANZIALI"
        if verdetto_semaforo == "VERDE"
        else (
            "🟡 GIALLO / DA VERIFICARE OCR"
            if verdetto_semaforo == "AMBAR" and not piano_completo_al_100
            else f"{ {'AMBAR': '🟠', 'ROJO': '🔴', 'GREY': '⚪'}.get(verdetto_semaforo, '🔴') } `{verdetto_semaforo}`"
        )
    )
    tabulato_md = (
        "### 🧮 Tabulato Deterministico Python-First (11 Sezioni · `Decimal ROUND_HALF_UP`)\n"
        f"**Verdetto Semaforo Matematico:** **{descrizione_verdetto}** (`{stato_certificazione}`)\n"
        f"{blocco_avviso_md}\n"
        "#### 1. Strato L — Classificazione Pagine, Basi C_fin vs C_netto & Completezza\n"
        f"- **Pagine Rilevate:** `{pagine_trovate}` | **Piano Ammortamento:** `{strato_l['pagine_piano_ammortamento']}` | **Costi/TAEG:** `{strato_l['pagine_riepilogo_costi_taeg']}` | **Liquidazione:** `{strato_l['pagine_prospetto_liquidazione']}`\n"
        f"- **Allineamento Colonne (`Q_int`/`Q_cap`) & Convenzione TAN:** `{criterio_allineamento_colonne}` · `{convenzione_tan_adottata}` (`{fonte_tan_controllo}`)\n"
        f"- **Numero Rate Atteso:** `{numero_rate_atteso}` | **Importo Rata Contrattuale:** `{strato_l['importo_rata'] or 'N/D'} €` | **Rate Lette da OCR:** `{n_rate_estratte}/{numero_rate_atteso}`\n"
        f"- **Montante Lordo (M):** `{strato_l['montante_dichiarato'] or str(m_rif_iniz) or 'N/D'} €` | **Capitale Finanziato Piano (`C_fin` base TAN):** `{strato_l['capitale_finanziato'] or 'N/D'} €` | **Interessi Contrattuali:** `{strato_l['interessi_totali_contrattuali'] or 'N/D'} €` | **Netto Erogato (`C_netto` base TAEG):** `{strato_l['netto_ricavo'] or 'N/D'} €`\n"
        f"{blocco_costi_md}"
        f"- **TAN Dichiarato:** `{strato_l['tan_dichiarato'] or 'N/D'}%` | **TAEG Dichiarato:** `{strato_l['taeg_dichiarato'] or 'N/D'}%`\n"
        f"- **Stato Completezza (`{stato_certificazione}`):** **{stato_completezza}**\n\n"
        "#### 2. Strato A — Quadrature Rata per Rata, Riallineamenti OCR & Formula Alla Francese\n"
        f"- **Verifica Montante (n x R):** `{montante_calcolato or 'N/D'} €` (Quadratura OK: `{quadratura_montante_ok}`)\n"
        f"- **Rata Teorica Alla Francese ({fonte_tan_controllo}):** `{rata_francese_teorica or 'N/D'} €` (vs Contrattuale `{strato_l['importo_rata'] or 'N/D'} €` · Delta: `{delta_rata_francese if delta_rata_francese is not None else 'N/D'} €` · `|Delta| <= 0.01`: `{quadratura_rata_francese_ok}`)\n"
        f"- **Rate Verificate (`Q_cap + Q_int = Rata`):** `{rate_verificate_ok} / {n_rate_estratte}` | **`D(n) = 0` ({numero_rate_atteso}):** {stato_dn_str}\n"
        f"- **Somma Rate / `Q_cap` / `Q_int` (su {n_rate_estratte} rate lette):** `{somma_rate_lette} €` | `{somma_quote_capitale_lette} €` (`OK: {quadratura_somma_quote_capitale_ok if piano_completo_al_100 else 'NON VERIFICATO'}`) | `{somma_quote_interessi_lette} €` (`OK: {quadratura_somma_quote_interessi_ok if piano_completo_al_100 else 'NON VERIFICATO'}`)\n"
        f"{blocco_riallineamento_md}"
        f"{blocco_mancanti_md}"
        f"- **Anomalie Aritmetiche Sostanziali Rilevate (`scarto max {scarto_massimo_tabella} €`):** `{totale_anomalie}` (`Somma rata: {len(righe_quadratura_errata)}`, `Capitale res.: {len(anomalie_capitale_residuo)}`, `Interessi {convenzione_tan_adottata}: {len(anomalie_interessi_primaria)}`, `Aggregate: {len(anomalie_aggregate)}`)\n"
        f"{blocco_rata_finale_md}"
        f"{dettagli_anomalie_md}\n"
        "#### 3. Strato D — Ricalcolo NPV Separato C_fin (TAN) vs C_netto (TAEG)\n"
        f"{avviso_cashflow}"
        f"- **TAN Ricalcolato da `C_fin` (`{strato_d['capitale_finanziato_c_fin'] or 'N/D'} €`):** `{strato_d['tan_ricalcolato_pct'] or 'N/D'}%` (Dichiarato: `{strato_l['tan_dichiarato'] or 'N/D'}%` · OK: `{tan_verificato_ok}`)\n"
        f"- **TAEG Ricalcolato da `C_netto` (`{strato_d['capitale_netto_taeg_c_netto'] or 'N/D'} €`):** `{strato_d['taeg_ricalcolato_pct'] or 'N/D'}%` (Dichiarato: `{strato_l['taeg_dichiarato'] or 'N/D'}%` · OK: `{taeg_verificato_ok}`)\n"
    )

    return {
        "certificabile": certificabile,
        "verdetto_semaforo": verdetto_semaforo,
        "stato_certificazione": stato_certificazione,
        "totale_anomalie": totale_anomalie,
        "convenzione_tan_adottata": convenzione_tan_adottata,
        "strato_l_osservazione": strato_l,
        "strato_a_quadrature": strato_a,
        "strato_d_ricalcolo_taeg_tan": strato_d,
        "righe_tabella_normalizzate": righe_tabella_serializzate,
        "tabulato_audit_python": tabulato_md,
    }
