#!/usr/bin/env python3
"""Layer 1 (THE): Acyclic THE hierarchy verification (EWD196), Radon metrics and file inspection."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from config import GERARCHIA_LIVELLI_THE
from anatomia_ast import analizza_codice_ast

try:
    from radon.complexity import cc_visit
except ImportError:
    cc_visit = None


def verifica_gerarchia_the(
    nome_modulo: str,
    codice: Optional[str] = None,
    import_rilevati: Optional[List[str]] = None,
) -> List[str]:
    """EWD196 / EWD310: Verifies that a module at layer L never imports modules at layer >= L."""
    if nome_modulo not in GERARCHIA_LIVELLI_THE:
        return []
    livello_corrente = GERARCHIA_LIVELLI_THE[nome_modulo]
    if import_rilevati is None:
        if codice is None:
            raise ValueError("Fornire 'codice' oppure 'import_rilevati'.")
        import_rilevati = analizza_codice_ast(codice)["import_rilevati"]

    violazioni: List[str] = []
    for mod_importato in import_rilevati:
        if mod_importato in GERARCHIA_LIVELLI_THE:
            livello_target = GERARCHIA_LIVELLI_THE[mod_importato]
            if livello_target >= livello_corrente:
                violazioni.append(
                    f"Violazione THE: '{nome_modulo}' (Livello {livello_corrente}) "
                    f"importa '{mod_importato}' (Livello {livello_target})"
                )
    return violazioni


def ispezione_completa(file_path: str) -> Dict[str, Any]:
    """Runs a single AST parse and combines THE hierarchy verification with Radon cyclomatic complexity."""
    percorso = Path(file_path)
    codice = percorso.read_text(encoding="utf-8")
    risultato = analizza_codice_ast(codice)
    risultato["violazioni_gerarchia_the"] = verifica_gerarchia_the(
        percorso.stem,
        import_rilevati=risultato["import_rilevati"],
    )

    mappa_cc: Dict[str, int] = {}
    if cc_visit is not None:
        for blocco in cc_visit(codice):
            chiave = (
                f"{blocco.classname}.{blocco.name}"
                if getattr(blocco, "classname", None)
                else blocco.name
            )
            mappa_cc[chiave] = blocco.complexity
            mappa_cc[blocco.name] = blocco.complexity

    for fn in risultato["funzioni"]:
        fn["complessita_ciclomatica"] = mappa_cc.get(
            fn["nome"],
            mappa_cc.get(fn.get("nome_breve", fn["nome"]), 1),
        )

    return risultato