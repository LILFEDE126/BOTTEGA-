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
    """Motore Python-First (Livello 1): esegue il censimento pagine/rate (Strato L), la quadratura
    aritmetica aggregata e rata per rata in Decimal ROUND_HALF_UP (Strato A) e il ricalcolo
    attuariale IRR/TAEG/TAN con bisezione a 60 iterazioni (Strato D)."""
    testo = testo_documento or ""
    testo_basso = testo.lower()

    pagine_trovate = sorted(
        set(
            int(m)
            for m in re.findall(
                r"(?i)(?:###\s*\[?\s*page\s*|\bpag(?:ina|\.)?\s*)(\d{1,3})\b",
                testo,
            )
            if 1 <= int(m) <= 200
        )
    )
    if not pagine_trovate and testo.strip():
        pagine_trovate = [1]

    ha_pag_8_9 = bool(8 in pagine_trovate or 9 in pagine_trovate or "taeg" in testo_basso)

    def _cerca_parametro_dec(pattern_lista: List[str]) -> Optional[Decimal]:
        for pat in pattern_lista:
            m = re.search(pat, testo, flags=re.IGNORECASE)
            if m:
                val = _converti_stringa_in_decimal_audit(m.group(1))
                if val is not None and val > 0:
                    return val
        return None

    numero_rate_totale = 0
    for pat_n in (
        r"(?:numero\s+rate(?:\s+totale)?|n\.?\s*rate|durata(?:\s+finanziamento)?)\s*[:=]?\s*(\d{2,3})\b",
        r"\b(\d{2,3})\s+rate(?:\s+mensili|\s+da|\s+costanti)\b",
    ):
        m_nr = re.search(pat_n, testo, flags=re.IGNORECASE)
        if m_nr:
            cand_n = int(m_nr.group(1))
            if 6 <= cand_n <= 360:
                numero_rate_totale = cand_n
                break

    importo_rata = _cerca_parametro_dec([
        r"(?:importo\s+rata(?:\s+mensile)?|rata\s+mensile|rate\s+(?:mensili\s+)?da)\s*[:=]?\s*(?:euro|eur|€)?\s*(\d+(?:[.,]\d+)+)",
    ])
    montante_dichiarato = _cerca_parametro_dec([
        r"(?:montante(?:\s+lordo|\s+complessivo|\s+dichiarato)?|importo\s+totale\s+dovuto|totale\s+dovuto)\s*[:=]?\s*(?:euro|eur|€)?\s*(\d+(?:[.,]\d+)+)",
        r"\b\d{2,3}\s+rate\s+da\s*(?:euro|eur|€)?\s*\d+(?:[.,]\d+)+\s*(?:euro|eur|€)?\s*\(\s*(?:euro|eur|€)?\s*(\d+(?:[.,]\d+)+)",
    ])
    capitale_o_valore_attuale = _cerca_parametro_dec([
        r"(?:capitale\s+(?:finanziato|erogato|lordo|iniziale)|valore\s+attuale|importo\s+totale\s+del\s+credito|importo\s+finanziato)\s*[:=]?\s*(?:euro|eur|€)?\s*(\d+(?:[.,]\d+)+)",
    ])
    netto_ricavo = _cerca_parametro_dec([
        r"(?:netto\s+ricavo|importo\s+netto\s+erogato|erogato\s+netto)\s*[:=]?\s*(?:euro|eur|€)?\s*(\d+(?:[.,]\d+)+)",
    ])
    tan_dichiarato = _cerca_parametro_dec([
        r"\btan\b[^0-9\n]{0,30}(\d+(?:[.,]\d+)?)\s*%?",
    ])
    taeg_dichiarato = _cerca_parametro_dec([
        r"\btaeg\b[^0-9\n]{0,30}(\d+(?:[.,]\d+)?)\s*%?",
    ])

    righe_rate: Dict[int, Dict[str, Decimal]] = {}
    ordine_cap_prima_di_int = False
    for r_raw in testo.splitlines():
        r_low = r_raw.lower()
        if "quota capitale" in r_low and "quota interessi" in r_low:
            if r_low.find("quota capitale") < r_low.find("quota interessi"):
                ordine_cap_prima_di_int = True
            else:
                ordine_cap_prima_di_int = False
        if r_raw.strip().startswith("#"):
            continue
        r_senza_date = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", " ", r_raw)
        m_rata = re.match(r"^\s*\|?\s*(?:rata\s*n?\.?\s*)?(\d{1,3})\b(.*)$", r_senza_date, flags=re.IGNORECASE)
        if not m_rata:
            continue
        idx_r = int(m_rata.group(1))
        if not (1 <= idx_r <= 360):
            continue
        resto_riga = m_rata.group(2)
        token_dec = re.findall(r"\d+(?:[.,]\d{2})\b", resto_riga)
        if len(token_dec) < 2:
            continue
        valori_dec = [_converti_stringa_in_decimal_audit(tok) for tok in token_dec]
        valori_validi = [v for v in valori_dec if v is not None]
        if len(valori_validi) < 2:
            continue

        if len(valori_validi) >= 3:
            v0, v1, v2 = valori_validi[0], valori_validi[1], valori_validi[2]
            deb_res = valori_validi[3] if len(valori_validi) >= 4 else Decimal("0.00")
            if abs((v0 + v1) - v2) <= Decimal("0.50") or (importo_rata is not None and abs(v2 - importo_rata) <= Decimal("0.50")):
                rata_v = v2
                if ordine_cap_prima_di_int:
                    q_cap_v, q_int_v = v0, v1
                else:
                    q_int_v, q_cap_v = v0, v1
            elif abs((v1 + v2) - v0) <= Decimal("0.50") or (importo_rata is not None and abs(v0 - importo_rata) <= Decimal("0.50")):
                rata_v = v0
                q_cap_v, q_int_v = v1, v2
            else:
                q_int_v, q_cap_v, rata_v = v0, v1, v2
            righe_rate[idx_r] = {
                "quota_interessi": arrotonda_esatto_el_x8(q_int_v, 2),
                "quota_capitale": arrotonda_esatto_el_x8(q_cap_v, 2),
                "rata": arrotonda_esatto_el_x8(rata_v, 2),
                "debito_residuo": arrotonda_esatto_el_x8(deb_res, 2),
                "ha_debito_residuo": Decimal(1 if len(valori_validi) >= 4 else 0),
            }
        elif len(valori_validi) == 2 and importo_rata is not None:
            v0, v1 = valori_validi[0], valori_validi[1]
            if ordine_cap_prima_di_int:
                q_cap_v, q_int_v = v0, v1
            else:
                q_int_v, q_cap_v = v0, v1
            righe_rate[idx_r] = {
                "quota_interessi": arrotonda_esatto_el_x8(q_int_v, 2),
                "quota_capitale": arrotonda_esatto_el_x8(q_cap_v, 2),
                "rata": arrotonda_esatto_el_x8(importo_rata, 2),
                "debito_residuo": Decimal("0.00"),
                "ha_debito_residuo": Decimal(0),
            }

    rate_lette_lista = sorted(righe_rate.keys())
    if numero_rate_totale == 0 and rate_lette_lista:
        numero_rate_totale = max(rate_lette_lista)
    if importo_rata is None and rate_lette_lista:
        importo_rata = righe_rate[rate_lette_lista[0]]["rata"]

    rate_mancanti_lista = (
        [k for k in range(1, numero_rate_totale + 1) if k not in righe_rate]
        if numero_rate_totale > 0
        else []
    )
    piano_completo_al_100 = bool(
        numero_rate_totale > 0
        and len(rate_mancanti_lista) == 0
        and len(rate_lette_lista) == numero_rate_totale
    )

    strato_l = {
        "pagine_lette": pagine_trovate,
        "pagine_riepilogo_taeg_presenti": ha_pag_8_9,
        "numero_rate_totale": numero_rate_totale,
        "importo_rata": str(arrotonda_esatto_el_x8(importo_rata, 2)) if importo_rata is not None else None,
        "montante_dichiarato": str(arrotonda_esatto_el_x8(montante_dichiarato, 2)) if montante_dichiarato is not None else None,
        "capitale_o_valore_attuale": str(arrotonda_esatto_el_x8(capitale_o_valore_attuale, 2)) if capitale_o_valore_attuale is not None else None,
        "netto_ricavo": str(arrotonda_esatto_el_x8(netto_ricavo, 2)) if netto_ricavo is not None else None,
        "tan_dichiarato": str(arrotonda_esatto_el_x8(tan_dichiarato, 2)) if tan_dichiarato is not None else None,
        "taeg_dichiarato": str(arrotonda_esatto_el_x8(taeg_dichiarato, 2)) if taeg_dichiarato is not None else None,
        "rate_lette_conteggio": len(rate_lette_lista),
        "rate_lette_lista": rate_lette_lista,
        "rate_lette_intervalli": _compatta_intervalli_rate(rate_lette_lista),
        "rate_mancanti_conteggio": len(rate_mancanti_lista),
        "rate_mancanti_lista": rate_mancanti_lista,
        "rate_mancanti": _compatta_intervalli_rate(rate_mancanti_lista),
        "piano_completo_al_100": piano_completo_al_100,
    }

    montante_calcolato: Optional[Decimal] = None
    quadratura_montante_ok: Optional[bool] = None
    if numero_rate_totale > 0 and importo_rata is not None:
        montante_calcolato = arrotonda_esatto_el_x8(Decimal(numero_rate_totale) * importo_rata, 2)
        if montante_dichiarato is not None:
            quadratura_montante_ok = abs(montante_calcolato - montante_dichiarato) <= Decimal("0.05")
        else:
            quadratura_montante_ok = True

    anomalie_somma_rata: List[str] = []
    anomalie_debito_residuo: List[str] = []
    anomalie_interessi_tan: List[str] = []
    rate_verificate_ok = 0

    for k in rate_lette_lista:
        info_k = righe_rate[k]
        q_int = info_k["quota_interessi"]
        q_cap = info_k["quota_capitale"]
        r_val = info_k["rata"]
        somma_ic = arrotonda_esatto_el_x8(q_int + q_cap, 2)
        if abs(somma_ic - r_val) >= Decimal("0.01"):
            anomalie_somma_rata.append(
                f"Rata {k}: Q_cap ({q_cap}) + Q_int ({q_int}) = {somma_ic} != Rata ({r_val})"
            )
        else:
            rate_verificate_ok += 1

        if (k - 1) in righe_rate:
            info_prev = righe_rate[k - 1]
            if info_k["ha_debito_residuo"] > 0 and info_prev["ha_debito_residuo"] > 0:
                deb_atteso = arrotonda_esatto_el_x8(info_prev["debito_residuo"] - q_cap, 2)
                if abs(info_k["debito_residuo"] - deb_atteso) >= Decimal("0.02"):
                    anomalie_debito_residuo.append(
                        f"Rata {k}: Debito residuo {info_k['debito_residuo']} != {info_prev['debito_residuo']} - {q_cap} ({deb_atteso})"
                    )
                if tan_dichiarato is not None and info_prev["debito_residuo"] > 0:
                    int_teo = arrotonda_esatto_el_x8(
                        info_prev["debito_residuo"] * (tan_dichiarato / Decimal("1200")), 2
                    )
                    if abs(q_int - int_teo) >= Decimal("0.05"):
                        anomalie_interessi_tan.append(
                            f"Rata {k}: Q_int letta {q_int} vs teorica {int_teo} (su Debito {info_prev['debito_residuo']} al TAN {tan_dichiarato}%)"
                        )

    somma_quote_capitale_lette = arrotonda_esatto_el_x8(
        sum((righe_rate[k]["quota_capitale"] for k in rate_lette_lista), Decimal("0.00")), 2
    )
    somma_quote_interessi_lette = arrotonda_esatto_el_x8(
        sum((righe_rate[k]["quota_interessi"] for k in rate_lette_lista), Decimal("0.00")), 2
    )

    strato_a = {
        "montante_calcolato": str(montante_calcolato) if montante_calcolato is not None else None,
        "quadratura_montante_ok": quadratura_montante_ok,
        "rate_verificate_ok": rate_verificate_ok,
        "somma_quote_capitale_lette": str(somma_quote_capitale_lette),
        "somma_quote_interessi_lette": str(somma_quote_interessi_lette),
        "anomalie_somma_rata": anomalie_somma_rata,
        "anomalie_debito_residuo": anomalie_debito_residuo,
        "anomalie_interessi_tan": anomalie_interessi_tan,
    }

    cap_riferimento = netto_ricavo or capitale_o_valore_attuale
    if cap_riferimento is None and numero_rate_totale > 0 and importo_rata is not None:
        if 1 in righe_rate and righe_rate[1]["ha_debito_residuo"] > 0:
            cap_riferimento = arrotonda_esatto_el_x8(
                righe_rate[1]["debito_residuo"] + righe_rate[1]["quota_capitale"], 2
            )
        elif tan_dichiarato is not None and tan_dichiarato > 0:
            i_m_stima = float(tan_dichiarato) / 1200.0
            r_fl = float(importo_rata)
            pv_stima = sum(r_fl / ((1.0 + i_m_stima) ** k) for k in range(1, numero_rate_totale + 1))
            cap_riferimento = arrotonda_esatto_el_x8(Decimal(str(pv_stima)), 2)
        elif montante_calcolato is not None:
            cap_riferimento = arrotonda_esatto_el_x8(montante_calcolato * Decimal("0.68"), 2)

    tan_ricalcolato: Optional[Decimal] = None
    taeg_ricalcolato: Optional[Decimal] = None
    tasso_mensile_irr: Optional[Decimal] = None

    if (
        cap_riferimento is not None
        and cap_riferimento > 0
        and numero_rate_totale > 0
        and importo_rata is not None
        and importo_rata > 0
        and Decimal(numero_rate_totale) * importo_rata > cap_riferimento
    ):
        low_i = 0.000001
        high_i = 0.05
        target_pv = float(cap_riferimento)
        rata_f = float(importo_rata)
        for _ in range(60):
            mid_i = (low_i + high_i) / 2.0
            pv_mid = sum(rata_f / ((1.0 + mid_i) ** k) for k in range(1, numero_rate_totale + 1))
            if pv_mid > target_pv:
                low_i = mid_i
            else:
                high_i = mid_i
        i_m_finale = (low_i + high_i) / 2.0
        tasso_mensile_irr = arrotonda_esatto_el_x8(Decimal(str(i_m_finale * 100.0)), 4)
        tan_ricalcolato = arrotonda_esatto_el_x8(Decimal(str(i_m_finale * 12.0 * 100.0)), 2)
        taeg_ricalcolato = arrotonda_esatto_el_x8(Decimal(str(((1.0 + i_m_finale) ** 12 - 1.0) * 100.0)), 2)

    strato_d = {
        "capitale_riferimento_irr": str(cap_riferimento) if cap_riferimento is not None else None,
        "tasso_periodale_mensile_pct": str(tasso_mensile_irr) if tasso_mensile_irr is not None else None,
        "tan_ricalcolato_pct": str(tan_ricalcolato) if tan_ricalcolato is not None else None,
        "taeg_ricalcolato_pct": str(taeg_ricalcolato) if taeg_ricalcolato is not None else None,
        "tan_dichiarato_pct": str(tan_dichiarato) if tan_dichiarato is not None else None,
        "taeg_dichiarato_pct": str(taeg_dichiarato) if taeg_dichiarato is not None else None,
    }

    stato_completezza = (
        f"COMPLETO AL 100% ({len(rate_lette_lista)}/{numero_rate_totale} rate verificate)"
        if piano_completo_al_100
        else f"PARZIALE ({len(rate_lette_lista)}/{numero_rate_totale} rate lette: presenti [{strato_l['rate_lette_intervalli']}], MANCANTI [{strato_l['rate_mancanti']}])"
    )
    tabulato_md = (
        "### 🧮 Tabulato Deterministico Python-First (`Decimal ROUND_HALF_UP`)\n\n"
        "#### 1. Strato L — Censimento Pagine, Parametri e Completezza Piano\n"
        f"- **Pagine Rilevate:** `{pagine_trovate}` (Pagine finali riepilogo/TAEG presenti: `{ha_pag_8_9}`)\n"
        f"- **Numero Rate Totale Previsto:** `{numero_rate_totale}` | **Importo Rata:** `{strato_l['importo_rata'] or 'N/D'} €`\n"
        f"- **Montante Dichiarato:** `{strato_l['montante_dichiarato'] or 'N/D'} €` | **Capitale / Valore Attuale:** `{strato_l['capitale_o_valore_attuale'] or 'N/D'} €` | **Netto Ricavo:** `{strato_l['netto_ricavo'] or 'N/D'} €`\n"
        f"- **TAN Dichiarato:** `{strato_l['tan_dichiarato'] or 'N/D'}%` | **TAEG Dichiarato:** `{strato_l['taeg_dichiarato'] or 'N/D'}%`\n"
        f"- **Stato Completezza Tabella Ammortamento:** **{stato_completezza}**\n\n"
        "#### 2. Strato A — Quadrature Aritmetiche Aggregate e Rata per Rata\n"
        f"- **Verifica Montante (`N_rate * Rata`):** `{montante_calcolato or 'N/D'} €` (Quadratura OK: `{quadratura_montante_ok}`)\n"
        f"- **Rate Verificate con `Q_cap + Q_int == Rata`:** `{rate_verificate_ok} / {len(rate_lette_lista)}`\n"
        f"- **Somma Quote Capitale ( sulle {len(rate_lette_lista)} rate lette ):** `{somma_quote_capitale_lette} €` | **Somma Quote Interessi:** `{somma_quote_interessi_lette} €`\n"
        f"- **Anomalie Somma Rata (`Q_cap + Q_int != Rata`):** `{len(anomalie_somma_rata)}` {('-> ' + '; '.join(anomalie_somma_rata[:5])) if anomalie_somma_rata else '(Nessuna)'}\n"
        f"- **Anomalie Discesa Debito Residuo:** `{len(anomalie_debito_residuo)}` {('-> ' + '; '.join(anomalie_debito_residuo[:5])) if anomalie_debito_residuo else '(Nessuna)'}\n"
        f"- **Scostamenti Interessi vs TAN Teorico:** `{len(anomalie_interessi_tan)}` {('-> ' + '; '.join(anomalie_interessi_tan[:5])) if anomalie_interessi_tan else '(Nessuno)'}\n\n"
        "#### 3. Strato D — Ricalcolo Attuariale IRR / TAN / TAEG (Bisezione 60 Iterazioni)\n"
        f"- **Capitale di Riferimento Attualizzazione:** `{strato_d['capitale_riferimento_irr'] or 'N/D'} €`\n"
        f"- **Tasso Periodale Mensile ($i_m$):** `{strato_d['tasso_periodale_mensile_pct'] or 'N/D'}%`\n"
        f"- **TAN Ricalcolato ($i_m \\times 12$):** `{strato_d['tan_ricalcolato_pct'] or 'N/D'}%` (Dichiarato: `{strato_l['tan_dichiarato'] or 'N/D'}%`)\n"
        f"- **TAEG Ricalcolato ($(1+i_m)^{{12}}-1$):** `{strato_d['taeg_ricalcolato_pct'] or 'N/D'}%` (Dichiarato: `{strato_l['taeg_dichiarato'] or 'N/D'}%`)\n"
    )

    return {
        "strato_l_osservazione": strato_l,
        "strato_a_quadrature": strato_a,
        "strato_d_ricalcolo_taeg_tan": strato_d,
        "tabulato_audit_python": tabulato_md,
    }
