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


def _normalizza_separatore_decimale(cifra: str) -> str:
    """Strips whitespace (including U+00A0) and normalizes decimal commas into dots."""
    return re.sub(r"[\s\xa0]", "", cifra).replace(",", ".")


def _converti_in_decimal_esatti(token_pulito: str) -> Set[Decimal]:
    """Converts a numeric token (EU thousands, EN thousands, or standard decimal) to exact Decimal values."""
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


def verifica_grounding_numerico(risposta: str, contesto: str) -> List[str]:
    """Returns the sorted list of figures cited in the response but absent from the context,
    comparing Decimal values for percentages, thousands, and technical decimals without confusing thousands."""
    raw_risp = PATRON_NUM.findall(risposta)
    raw_ctx = PATRON_NUM.findall(contesto)

    migliaia_ctx: Set[str] = set()
    altri_ctx: Set[str] = set()
    dec_ctx: Set[Decimal] = set()
    pct_ctx = estrai_percentuali_decimal(contesto)

    for m_int in PATRON_INTERI_PURI.findall(contesto):
        try:
            dec_ctx.add(Decimal(m_int))
        except InvalidOperation:
            pass

    for m in raw_ctx:
        pulito = re.sub(r"[\s\xa0]", "", m)
        norm = _normalizza_separatore_decimale(m)
        dec_ctx.update(_converti_in_decimal_esatti(pulito))
        if PATRON_MIGLIAIA.match(pulito):
            migliaia_ctx.add(norm)
        else:
            altri_ctx.add(norm)

    orfane: List[str] = []
    for m in raw_risp:
        pulito = re.sub(r"[\s\xa0]", "", m)
        c = _normalizza_separatore_decimale(m)
        e_migliaia = bool(PATRON_MIGLIAIA.match(pulito))

        if e_migliaia and c in migliaia_ctx:
            continue
        if not e_migliaia and c in altri_ctx:
            continue
        if c.endswith("%"):
            try:
                if Decimal(c[:-1]) in pct_ctx:
                    continue
            except InvalidOperation:
                pass
        else:
            candidati_dec = _converti_in_decimal_esatti(pulito)
            if candidati_dec and (candidati_dec & dec_ctx):
                continue
        orfane.append(c)
    return sorted(set(orfane))


def classifica_nodo_tricolore(risposta: str, contesto: str) -> Tuple[str, List[str]]:
    """EWD496A (Tri-Color Marking & Write Barrier): BIANCO (empty), GRIGIO (hallucinated), NERO (grounded)."""
    if not risposta or not risposta.strip():
        return ("BIANCO", [])
    cifre_orfane = verifica_grounding_numerico(risposta, contesto)
    if cifre_orfane:
        return ("GRIGIO", cifre_orfane)
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
    max_caratteri_pagina: int = 2400,
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
    passi_residui = 10000
    while residuo and passi_residui > 0:
        passi_residui -= 1
        if len(residuo) <= max_caratteri_pagina:
            pagine.append(residuo)
            break
        limite_taglio = max(100, max_caratteri_pagina - len(marcatore_continua))
        pagina_corrente = tronca_senza_spezzare_parola(residuo, limite_taglio)
        lunghezza_consumata = len(pagina_corrente)
        if lunghezza_consumata == 0 or lunghezza_consumata >= len(residuo):
            pagine.append(residuo)
            break
        pagine.append(pagina_corrente + marcatore_continua)
        residuo = residuo[lunghezza_consumata:].lstrip()
    return pagine
