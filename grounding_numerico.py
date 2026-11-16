#!/usr/bin/env python3
"""Layer 1 (THE): Exact Decimal arithmetic (EWD145), percentage conservation and Tri-Color
Write Barrier (EWD496A) on LLM-generated figures. Zero I/O dependencies."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
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


def esegui_audit_matematico_tabella_pdf(testo_documento: str) -> Dict[str, object]:
    """Pipeline deterministica Python-First in 10 punti (Livello 1, Decimal ROUND_HALF_UP):
    1) Classificazione pagine; 2-4) Schema normalizzato e guardia certificabilita';
    5-6) Quadrature rata per rata, doppia convenzione TAN e formula alla francese;
    7) Ricalcolo NPV separato C_fin (TAN) vs C_netto (TAEG) con guardia di credibilita';
    8) Scarto righe di riepilogo e sanity check; 9-10) Output deterministico per LLM."""
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
        or ("taeg" in testo_costi_low and ("netto ricavo" in testo_costi_low or "capitale finanziato" in testo_costi_low or "tan" in testo_costi_low))
    )

    def _cerca_parametro_dec(
        sorgente_testo: str,
        pattern_lista: List[str],
        min_val: Decimal = Decimal("0.01"),
        max_val: Decimal = Decimal("1000000.00"),
    ) -> Optional[Decimal]:
        for pat in pattern_lista:
            for m in re.finditer(pat, sorgente_testo, flags=re.IGNORECASE):
                val = _converti_stringa_in_decimal_audit(m.group(1))
                if val is not None and min_val <= val <= max_val:
                    return arrotonda_esatto_el_x8(val, 2)
        return None

    numero_rate_atteso = 0
    for pat_n in (
        r"(?:numero\s+rate(?:\s+totale)?|n\.?\s*rate|durata(?:\s+finanziamento)?)\s*[:=]?\s*(\d{1,3})\b",
        r"\b(\d{1,3})\s+rate(?:\s+mensili|\s+da|\s+costanti)\b",
    ):
        m_nr = re.search(pat_n, testo_costi_liq if testo_costi_liq else testo, flags=re.IGNORECASE)
        if not m_nr:
            m_nr = re.search(pat_n, testo, flags=re.IGNORECASE)
        if m_nr:
            cand_n = int(m_nr.group(1))
            if 6 <= cand_n <= 360:
                numero_rate_atteso = cand_n
                break

    importo_rata = _cerca_parametro_dec(testo_costi_liq, [
        r"(?:importo\s+(?:della\s+)?rata(?:\s+mensile)?|rata\s+mensile|rate\s+(?:mensili\s+)?da)\s*[:=]?\s*(?:euro|eur|€)?\s*(\d+(?:[.,]\d+)+)",
    ]) or _cerca_parametro_dec(testo, [
        r"(?:importo\s+(?:della\s+)?rata(?:\s+mensile)?|rata\s+mensile|rate\s+(?:mensili\s+)?da)\s*[:=]?\s*(?:euro|eur|€)?\s*(\d+(?:[.,]\d+)+)",
    ])

    montante_dichiarato = _cerca_parametro_dec(testo_costi_liq, [
        r"(?:montante(?:\s+lordo|\s+complessivo|\s+dichiarato)?|importo\s+totale\s+dovuto|totale\s+dovuto)\s*[:=]?\s*(?:euro|eur|€)?\s*(\d+(?:[.,]\d+)+)",
        r"\b\d{1,3}\s+rate\s+da\s*(?:euro|eur|€)?\s*\d+(?:[.,]\d+)+\s*(?:euro|eur|€)?\s*\(\s*(?:euro|eur|€)?\s*(\d+(?:[.,]\d+)+)",
    ])

    capitale_finanziato = _cerca_parametro_dec(testo_costi_liq, [
        r"(?:capitale\s+(?:finanziato|erogato|lordo|iniziale)|valore\s+attuale(?:\s+delle\s+rate)?|importo\s+totale\s+del\s+credito|importo\s+finanziato)\s*[:=]?\s*(?:euro|eur|€)?\s*(\d+(?:[.,]\d+)+)",
    ])

    netto_ricavo = _cerca_parametro_dec(testo_costi_liq, [
        r"(?:netto\s+ricavo|importo\s+netto\s+erogato|somma\s+netta\s+erogata|erogato\s+netto)\s*[:=]?\s*(?:euro|eur|€)?\s*(\d+(?:[.,]\d+)+)",
    ])

    totale_interessi_dich = _cerca_parametro_dec(testo_costi_liq, [
        r"(?:totale\s+interessi|interessi\s+complessivi|quota\s+interessi\s+totale)\s*[:=]?\s*(?:euro|eur|€)?\s*(\d+(?:[.,]\d+)+)",
    ])

    costi_upfront_taeg = Decimal("0.00")
    for pat_costo in (
        r"(?:spese\s+(?:di\s+)?istruttoria|commissioni\s+(?:bancarie|di\s+intermediazione|di\s+distribuzione)|oneri\s+fiscali|imposta\s+sostitutiva)\s*[:=]?\s*(?:euro|eur|€)?\s*(\d+(?:[.,]\d{2}))\b",
    ):
        for m_c in re.finditer(pat_costo, testo_costi_liq, flags=re.IGNORECASE):
            v_c = _converti_stringa_in_decimal_audit(m_c.group(1))
            if v_c is not None and Decimal("0.00") < v_c < Decimal("20000.00"):
                costi_upfront_taeg += arrotonda_esatto_el_x8(v_c, 2)

    tan_dichiarato = _cerca_parametro_dec(
        testo_costi_liq,
        [r"\btan\b[^0-9\n]{0,30}(\d+(?:[.,]\d+)?)\s*%?"],
        min_val=Decimal("0.01"),
        max_val=Decimal("40.00"),
    )
    taeg_dichiarato = _cerca_parametro_dec(
        testo_costi_liq,
        [r"\btaeg\b[^0-9\n]{0,30}(\d+(?:[.,]\d+)?)\s*%?"],
        min_val=Decimal("0.01"),
        max_val=Decimal("45.00"),
    )

    righe_normalizzate: Dict[int, Dict[str, object]] = {}
    rate_duplicate: List[int] = []
    righe_scartate_conteggio = 0
    patron_scarto_riepilogo = re.compile(
        r"\b(?:totale|riepilogo|saldo|finale|pagina|allegato|tan|taeg)\b",
        flags=re.IGNORECASE,
    )

    for _, corpo_piano in pagine_piano:
        ordine_cap_prima_di_int = False
        ha_col_debito_e_capitale = False
        for r_raw in corpo_piano.splitlines():
            r_low = r_raw.lower()
            if "quota capitale" in r_low and "quota interessi" in r_low:
                ordine_cap_prima_di_int = r_low.find("quota capitale") < r_low.find("quota interessi")
            if "capitale residuo" in r_low and "debito residuo" in r_low:
                ha_col_debito_e_capitale = True
            if r_raw.strip().startswith("#"):
                continue
            if patron_scarto_riepilogo.search(r_raw):
                righe_scartate_conteggio += 1
                continue

            m_data = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", r_raw)
            scadenza_str = m_data.group(1) if m_data else ""
            r_senza_date = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", " ", r_raw)

            m_rata = re.match(r"^\s*\|?\s*(?:rata\s*n?\.?\s*)?(\d{1,3})\b(.*)$", r_senza_date, flags=re.IGNORECASE)
            if not m_rata:
                continue
            idx_r = int(m_rata.group(1))
            limite_sup_rata = numero_rate_atteso if numero_rate_atteso > 0 else 360
            if not (1 <= idx_r <= limite_sup_rata):
                righe_scartate_conteggio += 1
                continue

            resto_riga = m_rata.group(2)
            token_dec = re.findall(r"\d+(?:[.,]\d{3})*(?:[.,]\d{2})\b", resto_riga)
            if len(token_dec) < 2:
                continue
            valori_dec = [_converti_stringa_in_decimal_audit(tok) for tok in token_dec]
            valori_validi = [v for v in valori_dec if v is not None]
            if len(valori_validi) < 2 or any(v > Decimal("1000000.00") or v < Decimal("0.00") for v in valori_validi):
                righe_scartate_conteggio += 1
                continue

            q_cap_v = Decimal("0.00")
            q_int_v = Decimal("0.00")
            rata_v = Decimal("0.00")
            cap_res_v = Decimal("0.00")
            deb_res_v = Decimal("0.00")
            ha_cap_res = False
            ha_deb_res = False

            if len(valori_validi) >= 3:
                v0, v1, v2 = valori_validi[0], valori_validi[1], valori_validi[2]
                if abs((v0 + v1) - v2) <= Decimal("0.50") or (importo_rata is not None and abs(v2 - importo_rata) <= Decimal("0.50")):
                    rata_v = v2
                    if ordine_cap_prima_di_int:
                        q_cap_v, q_int_v = v0, v1
                    else:
                        q_int_v, q_cap_v = v0, v1
                elif abs((v1 + v2) - v0) <= Decimal("0.50") or (importo_rata is not None and abs(v0 - importo_rata) <= Decimal("0.50")):
                    rata_v = v0
                    if ordine_cap_prima_di_int:
                        q_cap_v, q_int_v = v1, v2
                    else:
                        q_int_v, q_cap_v = v1, v2
                elif len(valori_validi) == 3 and importo_rata is not None:
                    rata_v = importo_rata
                    if ordine_cap_prima_di_int:
                        q_cap_v, q_int_v = v0, v1
                    else:
                        q_int_v, q_cap_v = v0, v1
                    cap_res_v = v2
                    ha_cap_res = True
                else:
                    q_int_v, q_cap_v, rata_v = v0, v1, v2

                if len(valori_validi) >= 5 and ha_col_debito_e_capitale:
                    cap_res_v = valori_validi[3]
                    deb_res_v = valori_validi[4]
                    ha_cap_res = True
                    ha_deb_res = True
                elif len(valori_validi) >= 4 and not ha_cap_res:
                    cap_res_v = valori_validi[3]
                    ha_cap_res = True
                    if len(valori_validi) >= 5:
                        deb_res_v = valori_validi[4]
                        ha_deb_res = True
            else:
                if importo_rata is None:
                    continue
                v0, v1 = valori_validi[0], valori_validi[1]
                if ordine_cap_prima_di_int:
                    q_cap_v, q_int_v = v0, v1
                else:
                    q_int_v, q_cap_v = v0, v1
                rata_v = importo_rata

            if rata_v <= Decimal("0.00"):
                righe_scartate_conteggio += 1
                continue

            if idx_r in righe_normalizzate:
                rate_duplicate.append(idx_r)
            else:
                righe_normalizzate[idx_r] = {
                    "rata": idx_r,
                    "scadenza": scadenza_str,
                    "importo_rata": arrotonda_esatto_el_x8(rata_v, 2),
                    "quota_capitale": arrotonda_esatto_el_x8(q_cap_v, 2),
                    "quota_interessi": arrotonda_esatto_el_x8(q_int_v, 2),
                    "capitale_residuo": arrotonda_esatto_el_x8(cap_res_v, 2),
                    "debito_residuo": arrotonda_esatto_el_x8(deb_res_v, 2),
                    "ha_capitale_residuo": ha_cap_res,
                    "ha_debito_residuo": ha_deb_res,
                }

    rate_lette_lista = sorted(righe_normalizzate.keys())
    n_rate_estratte = len(rate_lette_lista)
    if numero_rate_atteso == 0 and rate_lette_lista:
        numero_rate_atteso = max(rate_lette_lista)
    if importo_rata is None and rate_lette_lista:
        importo_rata = Decimal(str(righe_normalizzate[rate_lette_lista[0]]["importo_rata"]))

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

    certificabile = bool(piano_completo_al_100 and len(rate_duplicate) == 0)
    stato_certificazione = (
        "CERTIFICABILE_PIANO_COMPLETO"
        if certificabile
        else "NON_CERTIFICABILE_TABELLA_INCOMPLETA"
    )
    messaggio_blocco_certificazione = (
        ""
        if certificabile
        else (
            f"⚠️ BLOCCO DI CERTIFICAZIONE: Rilevate {n_rate_estratte} rate valide su {numero_rate_atteso} attese "
            f"(mancanti: {elenco_mancanti_str}). Non è possibile né certificare la correttezza dell'intero "
            f"piano né attestare l'assenza di vizi finché tutte le {numero_rate_atteso} rate non sono estratte."
        )
    )

    montante_calcolato: Optional[Decimal] = None
    quadratura_montante_ok: Optional[bool] = None
    if numero_rate_atteso > 0 and importo_rata is not None:
        montante_calcolato = arrotonda_esatto_el_x8(Decimal(numero_rate_atteso) * importo_rata, 2)
        if montante_dichiarato is not None:
            quadratura_montante_ok = abs(montante_calcolato - montante_dichiarato) <= Decimal("0.05")
        else:
            quadratura_montante_ok = True

    righe_rata_anomala: List[str] = []
    righe_quadratura_errata: List[str] = []
    righe_residuo_non_decrescente: List[str] = []
    anomalie_capitale_residuo: List[str] = []
    anomalie_debito_residuo: List[str] = []
    anomalie_interessi_nominale: List[str] = []
    anomalie_interessi_effettiva: List[str] = []
    rate_verificate_ok = 0

    i_m_nominale = (tan_dichiarato / Decimal("1200")) if tan_dichiarato is not None else None
    i_m_effettiva = (
        Decimal(str((1.0 + float(tan_dichiarato) / 100.0) ** (1.0 / 12.0) - 1.0))
        if tan_dichiarato is not None
        else None
    )

    for k in rate_lette_lista:
        info_k = righe_normalizzate[k]
        q_int = Decimal(str(info_k["quota_interessi"]))
        q_cap = Decimal(str(info_k["quota_capitale"]))
        r_val = Decimal(str(info_k["importo_rata"]))
        cap_res = Decimal(str(info_k["capitale_residuo"]))
        deb_res = Decimal(str(info_k["debito_residuo"]))

        if importo_rata is not None and k < numero_rate_atteso and abs(r_val - importo_rata) > Decimal("0.50"):
            righe_rata_anomala.append(f"Rata {k}: {r_val} € != {importo_rata} €")

        somma_ic = arrotonda_esatto_el_x8(q_int + q_cap, 2)
        if abs(somma_ic - r_val) > Decimal("0.01"):
            righe_quadratura_errata.append(
                f"Rata {k}: Q_cap ({q_cap}) + Q_int ({q_int}) = {somma_ic} != Rata ({r_val})"
            )
        else:
            rate_verificate_ok += 1

        if (k - 1) in righe_normalizzate:
            info_prev = righe_normalizzate[k - 1]
            prev_cap_res = Decimal(str(info_prev["capitale_residuo"]))
            prev_deb_res = Decimal(str(info_prev["debito_residuo"]))
            if info_k["ha_capitale_residuo"] and info_prev["ha_capitale_residuo"]:
                if cap_res > prev_cap_res:
                    righe_residuo_non_decrescente.append(f"Rata {k}: Capitale residuo {cap_res} > {prev_cap_res}")
                cap_atteso = arrotonda_esatto_el_x8(prev_cap_res - q_cap, 2)
                if abs(cap_res - cap_atteso) > Decimal("0.02"):
                    anomalie_capitale_residuo.append(
                        f"Rata {k}: C_res {cap_res} != {prev_cap_res} - {q_cap} ({cap_atteso})"
                    )
                if i_m_nominale is not None and prev_cap_res > Decimal("0.00"):
                    int_nom_atteso = arrotonda_esatto_el_x8(prev_cap_res * i_m_nominale, 2)
                    if abs(q_int - int_nom_atteso) > Decimal("0.02"):
                        anomalie_interessi_nominale.append(
                            f"Rata {k}: Q_int {q_int} vs nominale {int_nom_atteso}"
                        )
                if i_m_effettiva is not None and prev_cap_res > Decimal("0.00"):
                    int_eff_atteso = arrotonda_esatto_el_x8(prev_cap_res * i_m_effettiva, 2)
                    if abs(q_int - int_eff_atteso) > Decimal("0.02"):
                        anomalie_interessi_effettiva.append(
                            f"Rata {k}: Q_int {q_int} vs effettiva {int_eff_atteso}"
                        )

            if info_k["ha_debito_residuo"] and info_prev["ha_debito_residuo"]:
                deb_atteso = arrotonda_esatto_el_x8(prev_deb_res - r_val, 2)
                if abs(deb_res - deb_atteso) > Decimal("0.02"):
                    anomalie_debito_residuo.append(
                        f"Rata {k}: D_res {deb_res} != {prev_deb_res} - {r_val} ({deb_atteso})"
                    )

    m_rif = montante_dichiarato or montante_calcolato
    c_fin = capitale_finanziato
    if c_fin is None and totale_interessi_dich is not None and m_rif is not None:
        cand_c_fin = arrotonda_esatto_el_x8(m_rif - totale_interessi_dich, 2)
        if cand_c_fin > Decimal("0.00"):
            c_fin = cand_c_fin
    if c_fin is None and 1 in righe_normalizzate and righe_normalizzate[1]["ha_capitale_residuo"]:
        c_fin = arrotonda_esatto_el_x8(
            Decimal(str(righe_normalizzate[1]["capitale_residuo"]))
            + Decimal(str(righe_normalizzate[1]["quota_capitale"])),
            2,
        )

    c_netto = netto_ricavo
    if c_netto is None and c_fin is not None and costi_upfront_taeg > Decimal("0.00"):
        cand_netto = arrotonda_esatto_el_x8(c_fin - costi_upfront_taeg, 2)
        if cand_netto > Decimal("0.00"):
            c_netto = cand_netto

    rata_francese_teorica: Optional[Decimal] = None
    delta_rata_francese: Optional[Decimal] = None
    if c_fin is not None and c_fin > Decimal("0.00") and numero_rate_atteso > 0 and tan_dichiarato is not None and tan_dichiarato > Decimal("0.00"):
        i_m_f = float(tan_dichiarato) / 1200.0
        r_fr_float = float(c_fin) * (i_m_f / (1.0 - (1.0 + i_m_f) ** (-numero_rate_atteso)))
        rata_francese_teorica = arrotonda_esatto_el_x8(Decimal(str(r_fr_float)), 2)
        if importo_rata is not None:
            delta_rata_francese = arrotonda_esatto_el_x8(abs(importo_rata - rata_francese_teorica), 2)

    c_fin_coerente = bool(
        c_fin is not None
        and m_rif is not None
        and (Decimal("0.35") * m_rif) <= c_fin < (Decimal("0.98") * m_rif)
    )
    c_netto_coerente = bool(
        c_netto is not None
        and m_rif is not None
        and (Decimal("0.25") * m_rif) <= c_netto <= (c_fin if c_fin is not None else m_rif)
    )

    def _risolvi_irr_bisezione(cap_iniz: Optional[Decimal], cap_valido: bool) -> Optional[float]:
        if (
            not cap_valido
            or cap_iniz is None
            or cap_iniz <= Decimal("0.00")
            or numero_rate_atteso <= 0
            or importo_rata is None
            or importo_rata <= Decimal("0.00")
            or Decimal(numero_rate_atteso) * importo_rata <= cap_iniz
        ):
            return None
        low_i = 0.00001
        high_i = 0.05
        target_pv = float(cap_iniz)
        rata_f = float(importo_rata)
        for _ in range(60):
            mid_i = (low_i + high_i) / 2.0
            pv_mid = sum(rata_f / ((1.0 + mid_i) ** k) for k in range(1, numero_rate_atteso + 1))
            if pv_mid > target_pv:
                low_i = mid_i
            else:
                high_i = mid_i
        return (low_i + high_i) / 2.0

    i_m_fin = _risolvi_irr_bisezione(c_fin, c_fin_coerente)
    tan_ricalcolato: Optional[Decimal] = None
    if i_m_fin is not None:
        cand_tan = arrotonda_esatto_el_x8(Decimal(str(i_m_fin * 12.0 * 100.0)), 2)
        if Decimal("0.50") <= cand_tan <= Decimal("35.00"):
            tan_ricalcolato = cand_tan

    i_m_netto = _risolvi_irr_bisezione(c_netto, c_netto_coerente)
    taeg_ricalcolato: Optional[Decimal] = None
    tasso_mensile_irr: Optional[Decimal] = None
    if i_m_netto is not None:
        cand_taeg = arrotonda_esatto_el_x8(Decimal(str(((1.0 + i_m_netto) ** 12 - 1.0) * 100.0)), 2)
        if Decimal("0.50") <= cand_taeg <= Decimal("35.00"):
            taeg_ricalcolato = cand_taeg
            tasso_mensile_irr = arrotonda_esatto_el_x8(Decimal(str(i_m_netto * 100.0)), 4)

    voci_mancanti_cashflow: List[str] = []
    if not c_fin_coerente:
        voci_mancanti_cashflow.append("Capitale Finanziato coerente (0.35*M <= C_fin < 0.98*M)")
    if not c_netto_coerente:
        voci_mancanti_cashflow.append("Netto Ricavo / Capitale Netto TAEG coerente (Pag. 8/9)")
    stato_taeg = (
        "TAEG_TAN_CALCOLATI_SU_FLUSSO_COERENTE"
        if (tan_ricalcolato is not None and taeg_ricalcolato is not None)
        else "FLUSSO_CASSA_INCOMPLETO"
    )

    somma_quote_capitale_lette = arrotonda_esatto_el_x8(
        sum((Decimal(str(righe_normalizzate[k]["quota_capitale"])) for k in rate_lette_lista), Decimal("0.00")), 2
    )
    somma_quote_interessi_lette = arrotonda_esatto_el_x8(
        sum((Decimal(str(righe_normalizzate[k]["quota_interessi"])) for k in rate_lette_lista), Decimal("0.00")), 2
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
        "numero_rate_totale": numero_rate_atteso,
        "n_rate_atteso": numero_rate_atteso,
        "n_rate_estratte": n_rate_estratte,
        "importo_rata": str(importo_rata) if importo_rata is not None else None,
        "montante_dichiarato": str(montante_dichiarato) if montante_dichiarato is not None else None,
        "capitale_o_valore_attuale": str(c_fin) if c_fin is not None else None,
        "capitale_finanziato": str(c_fin) if c_fin is not None else None,
        "netto_ricavo": str(c_netto) if c_netto is not None else None,
        "tan_dichiarato": str(tan_dichiarato) if tan_dichiarato is not None else None,
        "taeg_dichiarato": str(taeg_dichiarato) if taeg_dichiarato is not None else None,
        "rate_lette_conteggio": n_rate_estratte,
        "rate_lette_lista": rate_lette_lista,
        "rate_lette_intervalli": _compatta_intervalli_rate(rate_lette_lista),
        "rate_mancanti_conteggio": len(rate_mancanti_lista),
        "rate_mancanti_lista": rate_mancanti_lista,
        "rate_mancanti": elenco_mancanti_str,
        "rate_duplicate": rate_duplicate,
        "righe_scartate_conteggio": righe_scartate_conteggio,
        "piano_completo_al_100": piano_completo_al_100,
        "certificabile": certificabile,
        "stato_certificazione": stato_certificazione,
        "messaggio_blocco_certificazione": messaggio_blocco_certificazione,
    }

    strato_a = {
        "montante_calcolato": str(montante_calcolato) if montante_calcolato is not None else None,
        "quadratura_montante_ok": quadratura_montante_ok,
        "rata_francese_teorica": str(rata_francese_teorica) if rata_francese_teorica is not None else None,
        "delta_rata_francese": str(delta_rata_francese) if delta_rata_francese is not None else None,
        "rate_verificate_ok": rate_verificate_ok,
        "somma_quote_capitale_lette": str(somma_quote_capitale_lette),
        "somma_quote_interessi_lette": str(somma_quote_interessi_lette),
        "righe_rata_anomala": righe_rata_anomala,
        "anomalie_somma_rata": righe_quadratura_errata,
        "righe_quadratura_errata": righe_quadratura_errata,
        "righe_residuo_non_decrescente": righe_residuo_non_decrescente,
        "anomalie_capitale_residuo": anomalie_capitale_residuo,
        "anomalie_debito_residuo": anomalie_debito_residuo,
        "anomalie_interessi_nominale": anomalie_interessi_nominale,
        "anomalie_interessi_effettiva": anomalie_interessi_effettiva,
        "anomalie_interessi_tan": anomalie_interessi_nominale,
    }

    strato_d = {
        "stato_taeg": stato_taeg,
        "voci_mancanti_cashflow": voci_mancanti_cashflow,
        "montante_lordo_m": str(m_rif) if m_rif is not None else None,
        "capitale_finanziato_c_fin": str(c_fin) if c_fin is not None else None,
        "capitale_netto_taeg_c_netto": str(c_netto) if c_netto is not None else None,
        "capitale_riferimento_irr": str(c_netto or c_fin) if (c_netto or c_fin) is not None else None,
        "tasso_periodale_mensile_pct": str(tasso_mensile_irr) if tasso_mensile_irr is not None else None,
        "tan_ricalcolato_pct": str(tan_ricalcolato) if tan_ricalcolato is not None else None,
        "taeg_ricalcolato_pct": str(taeg_ricalcolato) if taeg_ricalcolato is not None else None,
        "tan_dichiarato_pct": str(tan_dichiarato) if tan_dichiarato is not None else None,
        "taeg_dichiarato_pct": str(taeg_dichiarato) if taeg_dichiarato is not None else None,
    }

    stato_completezza = (
        f"COMPLETO AL 100% ({n_rate_estratte}/{numero_rate_atteso} rate verificate)"
        if piano_completo_al_100
        else f"PARZIALE — NON CERTIFICABILE ({n_rate_estratte}/{numero_rate_atteso} rate estratte: presenti [{strato_l['rate_lette_intervalli']}], MANCANTI [{elenco_mancanti_str}])"
    )
    blocco_avviso_md = f"\n> {messaggio_blocco_certificazione}\n" if messaggio_blocco_certificazione else ""
    avviso_cashflow = (
        f"- **Stato Ricalcolo NPV/TAEG:** `FLUSSO_CASSA_INCOMPLETO` — Dati mancanti per equazione esatta: `{', '.join(voci_mancanti_cashflow)}`\n"
        if stato_taeg == "FLUSSO_CASSA_INCOMPLETO"
        else ""
    )

    tabulato_md = (
        "### 🧮 Tabulato Deterministico Python-First (Pipeline in 10 Punti · `Decimal ROUND_HALF_UP`)\n"
        f"{blocco_avviso_md}\n"
        "#### 1. Strato L — Classificazione Pagine & Guardia di Certificabilità\n"
        f"- **Pagine Rilevate:** `{pagine_trovate}` | **Piano Ammortamento:** `{strato_l['pagine_piano_ammortamento']}` | **Costi/TAEG:** `{strato_l['pagine_riepilogo_costi_taeg']}` | **Liquidazione:** `{strato_l['pagine_prospetto_liquidazione']}`\n"
        f"- **Numero Rate Atteso:** `{numero_rate_atteso}` | **Importo Rata Contrattuale:** `{strato_l['importo_rata'] or 'N/D'} €`\n"
        f"- **Montante Lordo ($M$):** `{strato_l['montante_dichiarato'] or str(m_rif) or 'N/D'} €` | **Capitale Finanziato ($C_{{fin}}$):** `{strato_l['capitale_finanziato'] or 'N/D'} €` | **Netto Ricavo ($C_{{netto}}$):** `{strato_l['netto_ricavo'] or 'N/D'} €`\n"
        f"- **TAN Dichiarato:** `{strato_l['tan_dichiarato'] or 'N/D'}%` | **TAEG Dichiarato:** `{strato_l['taeg_dichiarato'] or 'N/D'}%`\n"
        f"- **Stato Completezza & Certificabilità (`{stato_certificazione}`):** **{stato_completezza}**\n\n"
        "#### 2. Strato A — Quadrature Rata per Rata & Formula Piano Alla Francese\n"
        f"- **Verifica Montante ($n \\times R$):** `{montante_calcolato or 'N/D'} €` (Quadratura OK: `{quadratura_montante_ok}`)\n"
        f"- **Rata Teorica Alla Francese ($C_{{fin}} \\cdot i_m / (1 - (1+i_m)^{{-n}})$):** `{rata_francese_teorica or 'N/D'} €` (Delta vs contrattuale: `{delta_rata_francese if delta_rata_francese is not None else 'N/D'} €`)\n"
        f"- **Rate Verificate con $Q_{{cap}} + Q_{{int}} = \\text{{Rata}}$:** `{rate_verificate_ok} / {n_rate_estratte}`\n"
        f"- **Somma Quote Capitale / Interessi (su {n_rate_estratte} rate lette):** `{somma_quote_capitale_lette} €` / `{somma_quote_interessi_lette} €`\n"
        f"- **Anomalie (Quadrature / Rata Anomala / Capitale Residuo / TAN nom. vs eff.):** `{len(righe_quadratura_errata)}` / `{len(righe_rata_anomala)}` / `{len(anomalie_capitale_residuo)}` / `{len(anomalie_interessi_nominale)}` nom. vs `{len(anomalie_interessi_effettiva)}` eff.\n\n"
        "#### 3. Strato D — Ricalcolo NPV Separato $C_{{fin}}$ (TAN) vs $C_{{netto}}$ (TAEG)\n"
        f"{avviso_cashflow}"
        f"- **TAN Ricalcolato da $C_{{fin}}$ (`{strato_d['capitale_finanziato_c_fin'] or 'N/D'} €`):** `{strato_d['tan_ricalcolato_pct'] or 'N/D'}%` (Dichiarato: `{strato_l['tan_dichiarato'] or 'N/D'}%`)\n"
        f"- **TAEG Ricalcolato da $C_{{netto}}$ (`{strato_d['capitale_netto_taeg_c_netto'] or 'N/D'} €`):** `{strato_d['taeg_ricalcolato_pct'] or 'N/D'}%` (Dichiarato: `{strato_l['taeg_dichiarato'] or 'N/D'}%`)\n"
    )

    return {
        "certificabile": certificabile,
        "stato_certificazione": stato_certificazione,
        "strato_l_osservazione": strato_l,
        "strato_a_quadrature": strato_a,
        "strato_d_ricalcolo_taeg_tan": strato_d,
        "righe_tabella_normalizzate": righe_tabella_serializzate,
        "tabulato_audit_python": tabulato_md,
    }
