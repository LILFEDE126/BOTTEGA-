#!/usr/bin/env python3
"""Layer 4 (THE): Multilingual Streamlit Dashboard (EN / ES / IT) with Free Cloud APIs,
automatic submodule hot-reload, automatic API key detection, live streaming and PDF archive."""

import hashlib
import importlib
import re
import tempfile
import time
from pathlib import Path
import psycopg2
import streamlit as st

import config
import logging_bottega
import anatomia_ast
import geometria_semaforo
import grounding_numerico
import ispezione_moduli
import presidio_concorrenza
import store_pgvector
import client_ollama
import seed_bottega
import cascata_strutturata
import risolutore_artigiano

_VERSIONE_MODULI_THE = "2026.11.09.v8"


def _allinea_moduli_in_memoria() -> None:
    """Forces Python on Streamlit Cloud to reload Layers 0..3 from disk when a new git commit is deployed,
    preventing stale sys.modules cache and ImportError while preserving the in-memory PDF archive."""
    necessita_reload = (
        st.session_state.get("_versione_moduli_the") != _VERSIONE_MODULI_THE
        or not hasattr(store_pgvector, "conta_frammenti_archivio_ram")
        or not hasattr(store_pgvector, "normalizza_spazi_testo_pdf")
        or not hasattr(risolutore_artigiano, "formatta_risposta_artigiano_leggibile")
        or not hasattr(config, "ha_chiave_dedicata_provider")
    )
    if necessita_reload:
        archivio_precedente = list(getattr(store_pgvector, "_ARCHIVIO_MEMORIA_RAM", []))
        moduli_ordinati = (
            config,
            logging_bottega,
            anatomia_ast,
            geometria_semaforo,
            grounding_numerico,
            ispezione_moduli,
            presidio_concorrenza,
            store_pgvector,
            client_ollama,
            seed_bottega,
            cascata_strutturata,
            risolutore_artigiano,
        )
        for modulo in moduli_ordinati:
            importlib.reload(modulo)

        if archivio_precedente and not getattr(store_pgvector, "_ARCHIVIO_MEMORIA_RAM", None):
            for voce in archivio_precedente:
                if "testo" in voce:
                    voce["testo"] = store_pgvector.normalizza_spazi_testo_pdf(voce["testo"])
            store_pgvector._ARCHIVIO_MEMORIA_RAM.extend(archivio_precedente)

        st.session_state["_versione_moduli_the"] = _VERSIONE_MODULI_THE

    archivio_sess_corrente = st.session_state.get("documenti_archivio_sessione", {})
    if archivio_sess_corrente:
        titoli_in_ram = {
            v.get("titolo") for v in getattr(store_pgvector, "_ARCHIVIO_MEMORIA_RAM", [])
        }
        for nome_doc_s, meta_doc_s in archivio_sess_corrente.items():
            blocchi_s = meta_doc_s.get("blocchi") or []
            if blocchi_s and nome_doc_s not in titoli_in_ram:
                store_pgvector.incasella_e_salva(
                    meta_doc_s.get("dominio", "generale"), nome_doc_s, blocchi_s
                )


_allinea_moduli_in_memoria()

PROMPT_TASCHINO_UNIVERSALE = (
    'Always act with the "Craftsman Method (Strato L + Strato A + Strato D)":\n'
    "1. HONEST STOP ON MISSING DATA (ROJO Semaphore): If an objective datum is missing, DO NOT guess. "
    "Reply only with: confirmed facts, the SINGLE missing datum, and what to measure first.\n"
    "2. ZERO CLUTTER RULE (ZERO MUCCHIO): Never mix multiple hypotheses. Select ONE guiding principle, "
    "explicitly list discarded hypotheses, state the violated equilibrium, and formulate ONE root cause "
    "with its practical verification experiment.\n"
    "3. NUMERIC WRITE BARRIER (STRATO D): Never invent or round numbers, codes, or percentages not present in the source.\n"
    "4. LANGUAGE: Always reply in the exact same language used by the user (EN, ES, IT, etc.)."
)

DOMINI_DISPONIBILI = ("generale", "tecnico", "normativo")
PROVIDERS_DISPONIBILI = ("gemini", "groq", "openrouter", "ollama", "deepseek", "openai")

_STILE_EDITORIALE_SOBRIO = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Spectral:ital,wght@0,400;0,600;1,400&display=swap');

div[data-testid="stMetricValue"], code, pre {
    font-family: 'IBM Plex Mono', monospace !important;
    font-variant-numeric: tabular-nums;
}
blockquote {
    border-left: 3px solid #2F6B5A !important;
    padding-left: 1rem !important;
}
.bottega-footer-disclaimer {
    text-align: center;
    font-size: 0.86rem;
    opacity: 0.82;
    margin-top: 2rem;
    margin-bottom: 0.4rem;
    font-variant-numeric: tabular-nums;
}
</style>
"""


INTERVALLO_STREAMING_UI_SECONDI: float = 0.01
ALTEZZA_TEXTAREA_UI: int = 120


def _stream_testo_parole(testo: str):
    """Yields words preserving markdown newlines for real-time streaming in Streamlit."""
    for token in re.findall(r"\S+\s*", testo):
        yield token
        time.sleep(INTERVALLO_STREAMING_UI_SECONDI)


def _conta_frammenti_ram_sicuro(titolo=None) -> int:
    """Safely counts fragments in the RAM archive even if an older module instance is present."""
    fn_conta = getattr(store_pgvector, "conta_frammenti_archivio_ram", None)
    if callable(fn_conta):
        return fn_conta(titolo)
    archivio = getattr(store_pgvector, "_ARCHIVIO_MEMORIA_RAM", [])
    if titolo is None:
        return len(archivio)
    return sum(1 for item in archivio if item.get("titolo") == titolo)


st.set_page_config(page_title="Bottega — Engine & Diagnostic Solver", layout="wide")
st.markdown(_STILE_EDITORIALE_SOBRIO, unsafe_allow_html=True)
st.title("Bottega — Engine & Diagnostic Solver")
st.caption(
    "Multilingual Input Enabled: Write in English, Español, Italiano or any language — "
    "cross-lingual retrieval and 3-Layer Verification (Strato L · Strato A · Strato D) are automatic."
)

with st.sidebar:
    st.header("1. AI Engine (Local or Free Cloud)")
    provider_cfg = getattr(config, "LLM_PROVIDER", "gemini")
    idx_provider_default = (
        PROVIDERS_DISPONIBILI.index(provider_cfg)
        if provider_cfg in PROVIDERS_DISPONIBILI
        else 0
    )
    provider_ui = st.selectbox(
        "Select AI Provider:",
        PROVIDERS_DISPONIBILI,
        index=idx_provider_default,
        help="Gemini (Google AI Studio) is pre-configured out-of-the-box. Other providers can use a custom key or auto-route through Gemini Cloud.",
    )
    fn_risolvi_chiave = getattr(config, "risolvi_chiave_api", None)
    chiave_dedicata = (
        fn_risolvi_chiave(provider=provider_ui)
        if callable(fn_risolvi_chiave)
        else getattr(config, "LLM_API_KEY", "")
    )
    api_key_ui = ""
    model_ui = ""
    if provider_ui != "ollama":
        if chiave_dedicata:
            st.success(f"Automatic {provider_ui.upper()} API Key active (Ready to use).")
            with st.expander("Optional: Override API Key or Model"):
                api_key_ui = st.text_input(
                    f"Custom API Key ({provider_ui.upper()}):",
                    type="password",
                    help="Leave blank to use the active key.",
                )
                model_ui = st.text_input(
                    "Model (optional, press Enter for default):",
                    placeholder="e.g. gemini-3.5-flash-lite or openrouter/free",
                )
        else:
            st.info(
                f"No dedicated {provider_ui.upper()} key set — automatically routing via built-in Gemini Cloud "
                f"(or enter your {provider_ui.upper()} API key below)."
            )
            api_key_ui = st.text_input(
                f"Optional {provider_ui.upper()} API Key:",
                type="password",
                help=f"Enter your {provider_ui.upper()} key, or leave blank to use the built-in Gemini Cloud engine.",
            )
            model_ui = st.text_input(
                "Model (optional, press Enter for default):",
                placeholder=f"Default for {provider_ui}",
            )
    else:
        st.info(
            "Local Ollama mode (127.0.0.1:11434) — automatically falls back to built-in Gemini Cloud when running on Streamlit Cloud."
        )

    st.divider()
    st.header("2. Document & PDF Archive")
    dominio_doc = st.selectbox(
        "Target Domain:",
        DOMINI_DISPONIBILI,
        key="dom_upload",
        help="Assigns a domain label (generale = Strato L, tecnico = Strato A, normativo = Strato D) to uploaded fragments.",
    )
    max_docs = getattr(config, "MAX_DOCUMENTI_PER_RICHIESTA", 30)
    max_mb = getattr(config, "MAX_MB_PER_RICHIESTA", 200)
    max_bytes = getattr(config, "MAX_BYTES_PER_RICHIESTA", 200 * 1024 * 1024)

    if "documenti_archivio_sessione" not in st.session_state:
        st.session_state["documenti_archivio_sessione"] = {}

    files_caricati = st.file_uploader(
        f"Upload up to {max_docs} documents (.pdf, .txt, .md, .csv, .py — max {max_mb} MB total):",
        type=["pdf", "txt", "md", "csv", "py"],
        accept_multiple_files=True,
    )
    clic_salva = st.button("Save to Archive")

    if files_caricati:
        archivio_sess = st.session_state["documenti_archivio_sessione"]
        files_da_elaborare = list(files_caricati)
        if len(files_da_elaborare) > max_docs:
            st.warning(
                f"Maximum limit of {max_docs} documents per request reached: "
                f"indexing the first {max_docs} files."
            )
            files_da_elaborare = files_da_elaborare[:max_docs]

        bytes_totali_correnti = sum(
            info["size_bytes"]
            for nome_f, info in archivio_sess.items()
            if nome_f not in {f.name for f in files_da_elaborare}
        )

        ram_globale = _conta_frammenti_ram_sicuro()
        nuovi_elaborati_ora = 0

        for singolo_file in files_da_elaborare:
            raw_bytes = singolo_file.getvalue()
            dim_file = len(raw_bytes)
            if singolo_file.name not in archivio_sess and len(archivio_sess) >= max_docs:
                st.warning(
                    f"Archive already holds {max_docs}/{max_docs} documents. "
                    f"Skipped '{singolo_file.name}'."
                )
                continue
            if bytes_totali_correnti + dim_file > max_bytes:
                st.warning(
                    f"Total size limit of {max_mb} MB per request exceeded: "
                    f"skipped '{singolo_file.name}'."
                )
                continue

            bytes_totali_correnti += dim_file
            sha_file = hashlib.sha256(raw_bytes).hexdigest()
            chiave_doc = f"{dominio_doc}:{sha_file}"
            info_esistente = archivio_sess.get(singolo_file.name)

            if (
                info_esistente is None
                or info_esistente.get("chiave") != chiave_doc
                or ram_globale == 0
            ):
                try:
                    blocchi_doc = store_pgvector.estrai_blocchi_documento(singolo_file.name, raw_bytes)
                    n_ins = 0
                    if not blocchi_doc:
                        st.warning(f"No readable text found in '{singolo_file.name}'.")
                    else:
                        try:
                            store_pgvector.inizializza_schema()
                        except psycopg2.Error as err_init:
                            logging_bottega.log.info(
                                "Inizializzazione PostgreSQL non riuscita (%s): memorizzazione nell'archivio RAM",
                                err_init,
                                extra={"code": "APP_INIT_001"},
                            )
                        n_ins = store_pgvector.incasella_e_salva(dominio_doc, singolo_file.name, blocchi_doc)
                        ram_globale = _conta_frammenti_ram_sicuro()
                    archivio_sess[singolo_file.name] = {
                        "chiave": chiave_doc,
                        "dominio": dominio_doc,
                        "blocchi": blocchi_doc,
                        "size_bytes": dim_file,
                        "n_frammenti": len(blocchi_doc),
                        "n_nuovi": n_ins,
                    }
                    nuovi_elaborati_ora += 1
                except (RuntimeError, ValueError, OSError, psycopg2.Error, KeyError, TypeError) as err:
                    logging_bottega.log_exception(
                        "Errore indicizzazione documento caricato", "APP_DOC_001", err
                    )
                    st.error(f"Could not read document '{singolo_file.name}': {err}")

        if clic_salva and nuovi_elaborati_ora == 0 and archivio_sess:
            st.toast("All uploaded documents are already indexed and active in the Archive!")

    archivio_attivo = st.session_state.get("documenti_archivio_sessione", {})
    if archivio_attivo:
        tot_docs = len(archivio_attivo)
        tot_frammenti_ram = _conta_frammenti_ram_sicuro()
        tot_frammenti = tot_frammenti_ram if tot_frammenti_ram > 0 else sum(
            v["n_frammenti"] for v in archivio_attivo.values()
        )
        tot_mb = sum(v["size_bytes"] for v in archivio_attivo.values()) / (1024 * 1024)
        st.success(
            f"Active Archive: {tot_docs}/{max_docs} documents indexed "
            f"({tot_frammenti} unique fragments in memory, {tot_mb:.2f} MB / {max_mb} MB)."
        )
        with st.expander(f"Loaded Documents ({tot_docs}/{max_docs})"):
            for idx_d, (nome_d, meta_d) in enumerate(archivio_attivo.items(), start=1):
                n_new = meta_d.get("n_nuovi", meta_d["n_frammenti"])
                nota_dup = " [duplicate deduplicated]" if (n_new == 0 and meta_d["n_frammenti"] > 0) else ""
                st.caption(
                    f"{idx_d}. {nome_d} — {n_new} new / {meta_d['n_frammenti']} fragments{nota_dup} "
                    f"({meta_d['dominio']}, {meta_d['size_bytes'] / (1024 * 1024):.2f} MB)"
                )
            if st.button("Clear All Uploaded Documents"):
                st.session_state["documenti_archivio_sessione"] = {}
                if hasattr(store_pgvector, "_ARCHIVIO_MEMORIA_RAM"):
                    store_pgvector._ARCHIVIO_MEMORIA_RAM.clear()
                st.rerun()

chiave_effettiva_ui = (
    api_key_ui.strip()
    if api_key_ui.strip()
    else (chiave_dedicata if provider_ui != "ollama" else None)
)

llm_selezionato_fn = client_ollama.costruisci_llm_fn(
    provider=provider_ui,
    api_key=chiave_effettiva_ui,
    model=model_ui.strip() if model_ui.strip() else None,
)


def _cercatore_cascata_ui(query_ricerca: str):
    return seed_bottega.cerca_nel_prontuario_esterno(
        query_ricerca,
        provider=provider_ui,
        api_key=chiave_effettiva_ui,
    )


tab_codice, tab_artigiano, tab_ponte_web = st.tabs([
    "1. Python AST Inspection & 3-Layer Cascade (Strato L · A · D)",
    "2. Automated Diagnostic Solver (EN / ES / IT)",
    "3. Free Web Bridge (Copy-Paste & Write-Barrier Audit)",
])

with tab_codice:
    codice_incollato = st.text_area(
        "Paste Python code to inspect:",
        height=200,
        placeholder="def calculate_margin(price, cost):\n    return price - cost",
    )
    col1, col2 = st.columns(2)

    with col1:
        if st.button("1A. Deterministic AST Anatomy Only (Instant, Zero LLM)"):
            if not codice_incollato.strip():
                st.warning("Please enter Python code first.")
            else:
                try:
                    dati_ast = anatomia_ast.analizza_codice_ast(codice_incollato)
                    st.success(
                        f"Functions/Methods: {dati_ast['numero_funzioni']} | "
                        f"Bare excepts: {dati_ast['totale_except_nudi']} | "
                        f"Unbounded loops: {dati_ast['cicli_senza_variante']} | "
                        f"Mutable globals: {dati_ast['usi_global_mutabili']}"
                    )
                    st.graphviz_chart(dati_ast["dot_graph"])
                    st.json(dati_ast["funzioni"])
                except SyntaxError as err:
                    st.error(f"Syntax error at line {err.lineno}: {err.msg}")

    with col2:
        if st.button("1B. Run Full 3-Layer Cascade (AST + RRF RAG + Strato L / A / D)", type="primary"):
            if not codice_incollato.strip():
                st.warning("Please enter Python code first.")
            else:
                try:
                    anatomia_ast.analizza_codice_ast(codice_incollato)
                except SyntaxError as err:
                    st.error(f"Syntax error at line {err.lineno}: {err.msg}")
                    st.stop()

                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp_path = Path(tmpdir) / "codice_analizzato.py"
                    tmp_path.write_text(codice_incollato, encoding="utf-8")
                    try:
                        with st.spinner("Running AST, Hybrid RRF RAG and 3-Layer Cascade (Strato L -> Strato A -> Strato D)..."):
                            referto = cascata_strutturata.esegui_cascata(str(tmp_path), llm_fn=llm_selezionato_fn)
                        st.write_stream(_stream_testo_parole(referto))
                        st.download_button(
                            "Download Markdown Report",
                            referto,
                            file_name="referto_bottega.md",
                            mime="text/markdown",
                        )
                    except (RuntimeError, ValueError, OSError, psycopg2.Error, KeyError, TypeError) as err:
                        logging_bottega.log_exception("Errore in esegui_cascata UI", "APP_CAS_001", err)
                        st.error(f"Error during cascade execution ({provider_ui}): {err}")

with tab_artigiano:
    PRESET_ESEMPI_TAB2 = {
        "Custom / Manual Input": {
            "problema": "",
            "escluse": "",
            "cerca": True,
            "info": "Type or paste your own question freely.",
        },
        "1. [PDF IT] Interessi attivi bancari e ritenuta 27% (1.000 euro, 270 euro, 730 euro)": {
            "problema": (
                "Se la banca accredita in conto corrente interessi attivi per un importo di 1.000 euro "
                "applicando una ritenuta fiscale del 27%, qual e' l'importo della ritenuta per l'Erario "
                "e qual e' l'importo netto accreditato in Banca c/c?"
            ),
            "escluse": "",
            "cerca": False,
            "info": "Present in loaded accounting PDFs (docsity...2025.pdf Pag. 28, 14dcea31...pdf Pag. 117). Expected: VERDE, Node: NERO.",
        },
        "2. [PDF ES] Reembolso prestamo Gamma Spa y 4 fases del prestito obbligazionario (20.000 euro, 2.300 euro, 22.300 euro)": {
            "problema": (
                "Con referencia a un prestamo hipotecario (mutuo passivo) ya existente, si la sociedad Gamma Spa "
                "reembolsa una cuota de capital de 20.000 euros y una cuota de intereses de 2.300 euros, "
                "cual es el importe total pagado por banco y cuales son las 4 fases en las que se articula un prestito obbligazionario?"
            ),
            "escluse": "",
            "cerca": False,
            "info": "Present in loaded accounting PDFs (docsity...2025.pdf Pag. 31). Answer 100% in Spanish. Expected: VERDE, Node: NERO.",
        },
        "3. [PDF EN] Advance to supplier & advance invoice (3.000 euro + VAT, 2.000 euro + VAT, 3.660 euro, 440 euro, 2.440 euro)": {
            "problema": (
                "When a company pays an advance to a supplier of 3.000 euros plus 22% VAT before receiving the invoice, "
                "what is the total bank payment of 3.660 euros recorded, and when the advance invoice of 2.000 euros plus 22% VAT arrives, "
                "what are the amounts of VAT credit of 440 euros and total debt of 2.440 euros?"
            ),
            "escluse": "",
            "cerca": False,
            "info": "Present in loaded accounting PDFs (docsity...2025.pdf Pag. 18). Answer 100% in English. Expected: VERDE, Node: NERO.",
        },
        "4. [PDF IT - Binary Search] 3 casi diminuzione capitale per uscita soci (con ipotesi escluse)": {
            "problema": (
                "Quali sono i 3 casi specifici in cui si verifica una diminuzione del capitale sociale "
                "per uscita dei soci secondo i documenti in archivio?"
            ),
            "escluse": (
                "Diminuzione del capitale sociale per esuberanza\n"
                "Copertura virtuale di una perdita di esercizio di 40.000 euro"
            ),
            "cerca": False,
            "info": "Present in loaded accounting PDFs (docsity...2025.pdf Pag. 35). Binary search isolates the 3 partner withdrawal cases in Point 1-5 and puts excluded hypotheses into Point 6.",
        },
        "5. [Web IT] Emendamenti OIC 16 e OIC 31 (2024) Fondi smantellamento e ripristino": {
            "problema": (
                "Cosa prevede l'emendamento al principio contabile OIC 31 entrato in vigore dal 2024 "
                "in merito alla contabilizzazione degli obblighi di smantellamento, rimozione del cespite e ripristino del sito?"
            ),
            "escluse": "",
            "cerca": True,
            "info": "External standard not in baseline PDFs. Uncheck external search to see ROJO Honest Stop; keep checked to trigger VERDE (s_max=0.95) + Node NERO.",
        },
        "6. [Web ES] Ley 18/2022 Crea y Crece facturacion B2B (8M euro, 60 dias)": {
            "problema": (
                "Que establece la Ley 18/2022 (Ley Crea y Crece) en Espana sobre la facturacion electronica "
                "obligatoria B2B entre empresas y autonomos y el plazo maximo de pago de 60 dias contra la morosidad?"
            ),
            "escluse": "",
            "cerca": True,
            "info": "External Spanish law. Uncheck external search to see ROJO Honest Stop; keep checked to trigger VERDE (s_max=0.95) + Node NERO.",
        },
        "7. [Web EN] OECD Pillar Two / EU Directive 2022/2523 (15% rate, 750M euro threshold)": {
            "problema": (
                "Under the new global minimum tax rules (OECD Pillar Two / EU Directive 2022/2523), "
                "what is the minimum effective corporate tax rate of 15% and what is the consolidated revenue threshold "
                "of 750 million euros for multinational groups?"
            ),
            "escluse": "",
            "cerca": True,
            "info": "External international tax rule. Uncheck external search to see ROJO Honest Stop; keep checked to trigger VERDE (s_max=0.95) + Node NERO.",
        },
    }

    if "diag_problema_area" not in st.session_state:
        st.session_state["diag_problema_area"] = ""
    if "diag_escluse_area" not in st.session_state:
        st.session_state["diag_escluse_area"] = ""
    if "diag_cerca_box" not in st.session_state:
        st.session_state["diag_cerca_box"] = True

    def _aggiorna_preset_tab2():
        scelto = st.session_state.get("menu_preset_scelto", "Custom / Manual Input")
        dati_preset = PRESET_ESEMPI_TAB2.get(scelto, PRESET_ESEMPI_TAB2["Custom / Manual Input"])
        st.session_state["diag_problema_area"] = dati_preset["problema"]
        st.session_state["diag_escluse_area"] = dati_preset["escluse"]
        st.session_state["diag_cerca_box"] = dati_preset["cerca"]

    st.selectbox(
        "Quick Test Presets (Italiano · Español · English — Verified on Baseline PDFs & Live Web):",
        options=list(PRESET_ESEMPI_TAB2.keys()),
        key="menu_preset_scelto",
        on_change=_aggiorna_preset_tab2,
        help="Select any certified example to automatically populate the question, falsified hypotheses, and external search toggle.",
    )
    scelto_ora = st.session_state.get("menu_preset_scelto", "Custom / Manual Input")
    preset_corrente = PRESET_ESEMPI_TAB2.get(scelto_ora, PRESET_ESEMPI_TAB2["Custom / Manual Input"])
    if preset_corrente.get("info"):
        st.caption(f"ℹ️ {preset_corrente['info']}")

    problema_testo = st.text_area(
        "Describe an unexpected problem in English, Español, Italiano or any language:",
        key="diag_problema_area",
        height=ALTEZZA_TEXTAREA_UI,
        placeholder=(
            "Write in English, Español or Italiano: e.g. According to OIC 19, when must payables be discounted? "
            "/ ¿Cuándo deben actualizarse las deudas según OIC 19? / Quando si attualizzano i debiti secondo OIC 19?"
        ),
    )
    col_dom, col_escl = st.columns([1, 2])
    with col_dom:
        dominio_scelto = st.selectbox(
            "Guiding Domain:",
            DOMINI_DISPONIBILI,
            index=0,
            help="Prioritizes fragments saved in this domain (generale = Strato L, tecnico = Strato A, normativo = Strato D) while still searching all loaded documents.",
        )
        cerca_fuori = st.checkbox(
            "Enable cascading external search (Handbook -> AI Web Search -> DuckDuckGo/Wikipedia) on ROJO Semaphore",
            key="diag_cerca_box",
        )
    with col_escl:
        ipotesi_escluse_testo = st.text_area(
            "Hypotheses already falsified in the field (one per line, optional - Binary Search):",
            key="diag_escluse_area",
            height=90,
            placeholder="e.g. Expansion vessel empty (isolated flow/return valves, boiler holds 1.5 bar)\nor: Short-term payable under 12 months already ruled out",
            help="Any hypothesis entered here is strictly forbidden as the root cause and will be isolated in Point 6 as [Falsified in the field].",
        )

    if st.button("Solve with Craftsman Method (Semaphore + wp(S, R) + Zero Clutter)", type="primary"):
        if not problema_testo.strip():
            st.warning("Please enter a problem description first.")
        else:
            lista_escluse = [
                riga.strip() for riga in ipotesi_escluse_testo.splitlines() if riga.strip()
            ]
            cercatore_fn = _cercatore_cascata_ui if cerca_fuori else None
            try:
                with st.spinner("Evaluating Guarded Semaphore, RRF Retrieval and Write Barrier (Strato L · A · D)..."):
                    esito = risolutore_artigiano.risolvi_da_artigiano(
                        problema_testo,
                        dominio=dominio_scelto,
                        cercatore_esterno_fn=cercatore_fn,
                        ipotesi_gia_escluse=lista_escluse,
                        llm_fn=llm_selezionato_fn,
                    )
                m1, m2, m3 = st.columns(3)
                m1.metric("RAG Semaphore", f"{esito['semaforo']} (s_max={esito['s_max']})")
                m2.metric("Mode", esito["modalita"])
                m3.metric("Write Barrier (Strato D)", f"Node {esito['colore_nodo_ewd496a']}")

                testo_leggibile = esito.get("risposta_discorsiva") or risolutore_artigiano.formatta_risposta_artigiano_leggibile(
                    esito["risultato"],
                    esito["modalita"],
                    lingua=esito.get("lingua", "it"),
                )
                st.subheader("Diagnostic Response & Operational Plan")
                st.write_stream(_stream_testo_parole(testo_leggibile))

                if testo_leggibile.strip().endswith("continua"):
                    st.info("ℹ️ Il testo prosegue. Inserisci 'continua' nel box o premi il pulsante sotto.")
                    if st.button("➡️ Continua lettura (Turno successivo)", type="secondary", key="btn_continua_tab2"):
                        st.session_state["diag_problema_area"] = "continua"
                        st.rerun()

                if esito.get("frammenti_usati"):
                    with st.expander("View Grounded Fragments Extracted from Document / Archive"):
                        for idx_f, testo_f in enumerate(esito["frammenti_usati"], start=1):
                            st.markdown(f"**Fragment {idx_f}:**\n> {testo_f}")

                with st.expander("Technical Details & JSON Audit (Strato L · Strato A · Strato D)"):
                    st.json(esito["risultato"])
                    if esito["cifre_non_ancorate"]:
                        st.warning(f"Ungrounded figures flagged by Write Barrier: {esito['cifre_non_ancorate']}")
            except (RuntimeError, ValueError, OSError, psycopg2.Error, KeyError, TypeError) as err:
                logging_bottega.log_exception("Errore in risolvi_da_artigiano UI", "APP_ART_001", err)
                st.error(f"Error during diagnostic execution ({provider_ui}): {err}")

with tab_ponte_web:
    st.subheader("Zero-API Mode: Generate a Grounded Prompt & Audit External AI Responses")
    st.markdown(
        "Use this section to combine **Bottega's local RAG retrieval and Strato D Decimal Write-Barrier** "
        "with any external web AI chat (ChatGPT, DeepSeek, Claude, Gemini) at **zero API cost**. "
        "**Nothing from an external AI is ever trusted blindly**: in Step 2, Bottega audits every single "
        "number and percentage before certifying it."
    )
    with st.expander("Universal Pocket Prompt (Copy & paste into any web AI Custom Instructions)"):
        st.code(PROMPT_TASCHINO_UNIVERSALE, language="markdown")

    problema_web = st.text_area(
        "Problem to solve via Free Web Bridge (in English, Español, Italiano, etc.):",
        key="prob_web",
        height=100,
        value=(
            "For the incorporation of Gamma Spa, a partner contributes 35.000 euro for a business with "
            "receivables of 20.000 euro, machinery of 60.000 euro, and payables of 50.000 euro: "
            "what is the net equity and what is the goodwill (avviamento)?"
        ),
    )
    escluse_web = st.text_input(
        "Hypotheses already falsified in the field (comma-separated, optional):",
        placeholder="e.g. Liabilities underestimated, Cash contribution without goodwill",
    )

    if st.button("Step 1 — Generate Grounded Prompt (Strato L + Strato A + Strato D)"):
        lista_escl_w = [x.strip() for x in escluse_web.split(",") if x.strip()]
        query_tradotta_w = client_ollama.traduci_query_per_ricerca(problema_web)
        blocchi_trovati = []
        try:
            rag_w = store_pgvector.recupera_con_semaforo(query_tradotta_w, dominio="generale", top_k=4)
            for idx_rw, fr_w in enumerate(rag_w.get("frammenti", []), start=1):
                blocchi_trovati.append((f"Archive Fragment {idx_rw}", fr_w["testo"]))
        except (RuntimeError, ValueError, OSError, psycopg2.Error, KeyError, TypeError) as err:
            logging_bottega.log.warning("Ponte web: errore recupero frammenti RAG: %s", err, extra={"code": "APP_WEB_001"})
        for sez_est, txt_est in seed_bottega.cerca_nel_prontuario_locale(problema_web):
            if not any(txt_est in b[1] for b in blocchi_trovati):
                blocchi_trovati.append((sez_est, txt_est))

        prompt_pronto = risolutore_artigiano.genera_prompt_ponte_web_gratuito(
            problema_web,
            blocchi_trovati,
            ipotesi_gia_escluse=lista_escl_w,
        )
        st.session_state["ultimo_contesto_web"] = "\n".join(
            [problema_web] + [f"{t}: {c}" for t, c in blocchi_trovati]
        )
        st.session_state["ultimo_problema_web"] = problema_web
        st.info("Copy the prompt below and paste it into ChatGPT, DeepSeek, Claude or Gemini:")
        st.code(prompt_pronto, language="markdown")

    st.divider()
    risposta_incollata = st.text_area(
        "Step 2 — Paste the web AI response here to subject it to Strato D Critical Audit (Tri-Color Write Barrier):",
        height=140,
        placeholder="Paste the response obtained from the external web AI here...",
    )
    if st.button("Step 2 — Audit Response with Tri-Color Write Barrier (Strato D)"):
        if not risposta_incollata.strip():
            st.warning("Paste the web AI response first.")
        else:
            ctx_verifica = st.session_state.get("ultimo_contesto_web", problema_web)
            colore_w, orfane_w = grounding_numerico.classifica_nodo_tricolore(
                risposta_incollata, ctx_verifica
            )
            pct_w = grounding_numerico.verifica_conservazione_percentuali_decimal(
                risposta_incollata, ctx_verifica
            )
            st.session_state["ultimo_audit_web"] = {
                "colore": colore_w,
                "pct_ok": pct_w,
                "orfane": orfane_w,
                "testo": risposta_incollata.strip(),
                "problema": st.session_state.get("ultimo_problema_web", problema_web),
            }

    audit_corrente = st.session_state.get("ultimo_audit_web")
    if audit_corrente and risposta_incollata.strip() == audit_corrente.get("testo"):
        if audit_corrente["colore"] == "NERO" and audit_corrente["pct_ok"]:
            st.success(
                "Certified BLACK Node (Strato D Verified): 100% of figures and percentages are strictly "
                "grounded in the source context (Decimal ROUND_HALF_UP)."
            )
            if st.button("Optional: Save Certified BLACK Node Response to Volatile Session Memory"):
                n_salvati_web = store_pgvector.incasella_e_salva(
                    "generale",
                    f"Verified Web Bridge Audit: {audit_corrente['problema'][:50]}",
                    [("Certified BLACK Node", audit_corrente["testo"])],
                )
                st.toast(f"Saved {n_salvati_web} certified fragment(s) to volatile session memory!")
        else:
            st.error(
                f"GREY Node Blocked by Strato D Write Barrier! Ungrounded/invented numbers detected: "
                f"{audit_corrente['orfane']} | Percentages preserved: {audit_corrente['pct_ok']}. "
                "This response is rejected and CANNOT be saved into session memory."
            )

st.divider()
st.markdown(
    '<p class="bottega-footer-disclaimer">'
    "Bottega uses AI and can make mistakes, including about people or numbers — "
    "always verify outputs against the certified source fragments."
    "</p>",
    unsafe_allow_html=True,
)
with st.expander("Your Privacy, Data Handling & Verification Architecture (Strato L · Strato A · Strato D)"):
    st.markdown(
        """
**1. Volatile In-Memory Data Handling & Privacy (Zero Permanent Cloud Storage)**
- **RAM-Only Session Archive:** When you upload documents (`.pdf`, `.txt`, `.md`, `.csv`, `.py` — up to **30 files and 200 MB per session**), Bottega extracts and indexes text fragments exclusively in volatile memory (`_ARCHIVIO_MEMORIA_RAM` and your active browser session).
- **No External Model Training:** Your uploaded files are never permanently stored on third-party servers and are never used to train external AI models.
- **Instant Purge:** Clicking **"Clear All Uploaded Documents"** in the sidebar (or closing your session) immediately wipes all indexed fragments from volatile memory.

**2. Three-Layer Verification Architecture (`Strato L` · `Strato A` · `Strato D`)**
- **`Strato L` (Observation & Simplicity — Domain `generale`):** Inspects objective facts and AST structure first, applying the *Zero Clutter (`Zero Mucchio`)* principle to select a single guiding source and isolate discarded fragments in Point 6.
- **`Strato A` (Pragmatic Guardrails — Domain `tecnico`):** Enforces explicit network timeouts, schema self-stabilization, concurrency protection, and binary field-falsification filters.
- **`Strato D` (Formal Rigor & Write Barrier — Domain `normativo`):** Enforces the Law of the Excluded Miracle (`wp(S, false) = false`) and the **Tri-Color Write Barrier** in exact `Decimal` (`ROUND_HALF_UP`) arithmetic.

**3. Shared Volatile Memory & Critical Judgment (Zero Blind Trust)**
- Fragments stored in volatile memory are accessible across all three tools (**Tab 1**, **Tab 2**, and **Tab 3**), allowing you to cross-examine an entire document dossier.
- **Nothing in memory is ever accepted uncritically:** Every query re-evaluates fragments through Hybrid RRF ranking, the Guarded Semaphore (`VERDE` / `AMBAR` / `ROJO`), the anti-clutter discard filter, and the `Strato D` Decimal Write Barrier. Any output containing even a single unverified number is immediately flagged as a **`GREY Node`** and blocked from certification.
"""
    )
