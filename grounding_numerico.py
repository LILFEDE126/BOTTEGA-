#!/usr/bin/env python3
"""Layer 1 (THE): Exact Decimal arithmetic (EWD145), percentage conservation and Tri-Color
Write Barrier (EWD496A) on LLM-generated figures. Zero I/O dependencies."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import List, Set, Tuple

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
