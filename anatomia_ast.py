#!/usr/bin/env python3
"""Layer 0 (THE): Pure static AST analysis on Python strings (zero I/O, zero internal dependencies)."""

import ast
from typing import Any, Dict, List


def _ha_uscita_propria_nel_while(nodo_while: ast.While) -> bool:
    """Checks whether a 'while True' loop has its own break/return/raise without being fooled
    by break statements inside nested for/while loops."""
    coda = list(nodo_while.body)
    while coda:
        corrente = coda.pop(0)
        if isinstance(corrente, (ast.Return, ast.Raise, ast.Break)):
            return True
        if isinstance(
            corrente,
            (ast.For, ast.AsyncFor, ast.While, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            continue
        coda.extend(ast.iter_child_nodes(corrente))
    return False


def _analizza_nodo_funzione(
    nodo: ast.FunctionDef | ast.AsyncFunctionDef,
    prefisso_classe: str = "",
) -> tuple[Dict[str, Any], List[str]]:
    """Extracts metrics and call graph edges from a top-level function or class method."""
    nome_qualificato = f"{prefisso_classe}.{nodo.name}" if prefisso_classe else nodo.name
    righe = (nodo.end_lineno or nodo.lineno) - nodo.lineno + 1
    chiamate_locali: List[str] = []
    archi: List[str] = []
    except_nudi_fn = 0
    except_generici_fn = 0

    for sub in ast.walk(nodo):
        if isinstance(sub, ast.ExceptHandler):
            if sub.type is None:
                except_nudi_fn += 1
            elif isinstance(sub.type, ast.Name) and sub.type.id in ("Exception", "BaseException"):
                except_generici_fn += 1
        elif isinstance(sub, ast.Call):
            target = None
            if isinstance(sub.func, ast.Name):
                target = sub.func.id
            elif isinstance(sub.func, ast.Attribute):
                target = sub.func.attr
            if target:
                chiamate_locali.append(target)
                archi.append(f'    "{nome_qualificato}" -> "{target}";')

    info_fn = {
        "nome": nome_qualificato,
        "nome_breve": nodo.name,
        "linea_inizio": nodo.lineno,
        "righe": righe,
        "argomenti": [a.arg for a in nodo.args.args],
        "chiamate": sorted(set(chiamate_locali)),
        "except_nudi": except_nudi_fn,
        "except_generici": except_generici_fn,
    }
    return info_fn, archi


def analizza_codice_ast(codice: str) -> Dict[str, Any]:
    """Analyzes a Python source string via AST including top-level functions and class methods."""
    albero = ast.parse(codice)
    funzioni: List[Dict[str, Any]] = []
    archi_chiamate: List[str] = []
    totale_except_nudi = 0
    totale_except_generici = 0
    cicli_senza_variante = 0
    usi_global_mutabili = 0
    import_rilevati: List[str] = []

    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.ExceptHandler):
            if nodo.type is None:
                totale_except_nudi += 1
            elif isinstance(nodo.type, ast.Name) and nodo.type.id in ("Exception", "BaseException"):
                totale_except_generici += 1
        elif isinstance(nodo, ast.Global):
            usi_global_mutabili += len(nodo.names)
        elif isinstance(nodo, ast.While):
            if isinstance(nodo.test, ast.Constant) and nodo.test.value is True:
                if not _ha_uscita_propria_nel_while(nodo):
                    cicli_senza_variante += 1
        elif isinstance(nodo, ast.Import):
            for alias in nodo.names:
                import_rilevati.append(alias.name.split(".")[0])
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            import_rilevati.append(nodo.module.split(".")[0])

    for nodo in albero.body:
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info_fn, archi = _analizza_nodo_funzione(nodo)
            funzioni.append(info_fn)
            archi_chiamate.extend(archi)
        elif isinstance(nodo, ast.ClassDef):
            for elemento in nodo.body:
                if isinstance(elemento, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    info_fn, archi = _analizza_nodo_funzione(elemento, prefisso_classe=nodo.name)
                    funzioni.append(info_fn)
                    archi_chiamate.extend(archi)

    dot_lines = ["digraph CallGraph {", "    rankdir=LR;"] + sorted(set(archi_chiamate)) + ["}"]
    return {
        "numero_funzioni": len(funzioni),
        "totale_except_nudi": totale_except_nudi,
        "totale_except_generici": totale_except_generici,
        "cicli_senza_variante": cicli_senza_variante,
        "usi_global_mutabili": usi_global_mutabili,
        "import_rilevati": sorted(set(import_rilevati)),
        "funzioni": funzioni,
        "dot_graph": "\n".join(dot_lines),
    }