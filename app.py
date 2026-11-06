#!/usr/bin/env python3
"""Layer 4 (THE): Multilingual Streamlit Dashboard (EN / ES / IT) with Free Cloud APIs,
automatic submodule hot-reload, automatic API key detection, live streaming and PDF archive."""

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

_VERSIONE_MODULI_THE = "2026.11.06.v3"


def _allinea_moduli_in_memoria() -> None:
    """Forces Python on Streamlit Cloud to reload Layers 0..3 from disk when a new git commit is deployed,
    preventing stale sys.modules cache and ImportError while preserving the in-memory PDF archive."""
    necessita_reload = (
        st.session_state.get("_versione_moduli_the") != _VERSIONE_MODULI_THE
        or not hasattr(store_pgvector, "conta_frammenti_archivio_ram")
        or not hasattr(risolutore_artigiano, "formatta_risposta_artigiano_leggibile")
        or not hasattr(config, "risolvi_chiave_api")
    )
    if not necessita_reload:
        return

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
        store_pgvector._ARCHIVIO_MEMORIA_RAM.extend(archivio_precedente)

    st.session_state["_versione_moduli_the"] = _VERSIONE_MODULI_THE


_allinea_moduli_in_memoria()

PROMPT_TASCHINO_UNIVERSALE = (
    'Always act with the "Craftsman Method (Leonardo + Dijkstra EWD401)":\n'
    "1. HONEST STOP ON MISSING DATA (ROJO Semaphore): If an objective datum is missing, DO NOT guess. "
    "Reply only with: confirmed facts, the SINGLE missing datum, and what to measure first.\n"
    "2. ZERO CLUTTER RULE (ZERO MUCCHIO): Never mix multiple hypotheses. Select ONE guiding principle, "
    "explicitly list discarded hypotheses, state the violated equilibrium, and formulate ONE root cause "
    "with its practical verification experiment.\n"
    "3. NUMERIC WRITE BARRIER: Never invent or round numbers, codes, or percentages not present in the source.\n"
    "4. LANGUAGE: Always reply in the exact same language used by the user (EN, ES, IT, etc.)."
)

DOMINI_DISPONIBILI = ["generale", "tecnico", "normativo"]
PROVIDERS_DISPONIBILI = ["gemini", "groq", "openrouter", "ollama", "deepseek", "openai"]


def _stream_testo_parole(testo: str):
    """Yields words preserving markdown newlines for real-time streaming in Streamlit."""
    for token in re.findall(r"\S+\s*", testo):
        yield token
        time.sleep(0.01)


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
st.title("Bottega — Engine & Diagnostic Solver")
st.caption("Multilingual Input Enabled: Write in English, Español, Italiano or any language — search is automatically translated.")

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
        help="Gemini (Google AI Studio), Groq and OpenRouter offer a Free Tier without credit card.",
    )
    fn_risolvi_chiave = getattr(config, "risolvi_chiave_api", None)
    chiave_auto = fn_risolvi_chiave() if callable(fn_risolvi_chiave) else getattr(config, "LLM_API_KEY", "")
    api_key_ui = ""
    model_ui = ""
    if provider_ui != "ollama":
        if chiave_auto:
            st.success(f"Automatic {provider_ui.upper()} API Key active (Ready to use).")
            with st.expander("Optional: Override API Key or Model"):
                api_key_ui = st.text_input(
                    f"Custom API Key ({provider_ui.upper()}):",
                    type="password",
                    help="Leave blank to use the built-in automatic key.",
                )
                model_ui = st.text_input(
                    "Model (optional, press Enter for default):",
                    placeholder="e.g. gemini-3.5-flash-lite or openrouter/free",
                )
        else:
            api_key_ui = st.text_input(
                f"API Key ({provider_ui.upper()}):",
                type="password",
                help="Enter your API key or set LLM_API_KEY in .env / Streamlit Secrets.",
            )
            model_ui = st.text_input(
                "Model (optional, press Enter for free default):",
                placeholder="e.g. gemini-3.5-flash-lite or openrouter/free",
            )
    else:
        st.caption("Local mode active on 127.0.0.1:11434 (Ollama).")

    st.divider()
    st.header("2. Document & PDF Archive")
    dominio_doc = st.selectbox(
        "Target Domain:",
        DOMINI_DISPONIBILI,
        key="dom_upload",
    )
    file_caricato = st.file_uploader(
        "Upload a document (.pdf, .txt, .md, .csv, .py) into the Archive:",
        type=["pdf", "txt", "md", "csv", "py"],
    )
    if file_caricato is not None:
        raw_bytes = file_caricato.getvalue()
        chiave_doc = f"{dominio_doc}:{file_caricato.name}:{len(raw_bytes)}"
        clic_salva = st.button("Save to Archive")
        in_ram = _conta_frammenti_ram_sicuro(file_caricato.name)
        if clic_salva or st.session_state.get("ultimo_doc_indicizzato") != chiave_doc or in_ram == 0:
            try:
                blocchi_doc = store_pgvector.estrai_blocchi_documento(file_caricato.name, raw_bytes)
                if not blocchi_doc:
                    st.warning("No readable text found in the uploaded file.")
                else:
                    try:
                        store_pgvector.inizializza_schema()
                    except psycopg2.Error:
                        pass
                    n_ins = store_pgvector.incasella_e_salva(dominio_doc, file_caricato.name, blocchi_doc)
                    st.session_state["ultimo_doc_indicizzato"] = chiave_doc
                    st.session_state["ultimo_doc_msg"] = (
                        f"Indexed {len(blocchi_doc)} fragments ({n_ins} new) from "
                        f"'{file_caricato.name}' in domain '{dominio_doc}'."
                    )
            except Exception as err:
                logging_bottega.log_exception("Errore indicizzazione documento caricato", "APP_DOC_001", err)
                st.error(f"Could not read document '{file_caricato.name}': {err}")

        if st.session_state.get("ultimo_doc_msg"):
            st.success(st.session_state["ultimo_doc_msg"])

chiave_effettiva_ui = api_key_ui.strip() if api_key_ui.strip() else (chiave_auto if provider_ui != "ollama" else None)

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
    "1. Python AST Inspection & 3-Layer Cascade",
    "2. Automated Diagnostic Solver (EN / ES / IT)",
    "3. Free Web Bridge (Copy-Paste for ChatGPT / DeepSeek / Gemini)",
])

with tab_codice:
    codice_incollato = st.text_area(
        "Paste Python code to inspect:",
        height=200,
        placeholder="def calculate_duty(value, rate):\n    return value * rate",
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
        if st.button("1B. Run Full 3-Layer Cascade (AST + RRF RAG + 3 Layers)", type="primary"):
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
                        with st.spinner("Running AST, Hybrid RRF RAG and 3-Layer Cascade..."):
                            referto = cascata_strutturata.esegui_cascata(str(tmp_path), llm_fn=llm_selezionato_fn)
                        st.write_stream(_stream_testo_parole(referto))
                        st.download_button(
                            "Download Markdown Report",
                            referto,
                            file_name="referto_bottega.md",
                            mime="text/markdown",
                        )
                    except Exception:
                        logging_bottega.log_exception("Errore esecuzione cascata Streamlit", "APP_CASCATA_001")
                        st.error(
                            "Inference service or API key unavailable. "
                            "Check the sidebar or use Tab 3 (Free Web Bridge)."
                        )

with tab_artigiano:
    problema_utente = st.text_area(
        "Describe an unexpected problem in English, Español, Italiano or any language:",
        height=120,
        placeholder="e.g. The heating system loses 0.4 bar every hour when cold with no visible radiator leaks... / ¿Qué arancel y antidumping aplica al código TARIC 7604210000 origen CN?",
    )
    col_a, col_b = st.columns(2)
    with col_a:
        indice_dom_default = DOMINI_DISPONIBILI.index(dominio_doc) if dominio_doc in DOMINI_DISPONIBILI else 0
        dominio_scelto = st.selectbox("Guiding Domain:", DOMINI_DISPONIBILI, index=indice_dom_default)
        attiva_ricerca = st.checkbox(
            "Enable cascading external search (Handbook -> AI Web Search -> DuckDuckGo/Wikipedia) on ROJO",
            value=True,
        )
    with col_b:
        ipotesi_escluse_input = st.text_area(
            "Hypotheses already falsified in the field (one per line, optional - Binary Search):",
            height=90,
            placeholder="e.g. Expansion vessel empty (isolated flow/return valves, boiler holds 1.5 bar)",
        )

    if st.button("Solve with Craftsman Method (Semaphore + wp(S, R) + Zero Clutter)", type="primary"):
        if not problema_utente.strip():
            st.warning("Please describe the problem first.")
        else:
            lista_escluse = [
                riga.strip() for riga in ipotesi_escluse_input.splitlines() if riga.strip()
            ]
            cercatore_fn = _cercatore_cascata_ui if attiva_ricerca else None
            try:
                with st.status("Streaming diagnostic analysis (PDF Archive, RAG Semaphore & Write Barrier)...", expanded=True) as stato_diag:
                    if file_caricato is not None and _conta_frammenti_ram_sicuro(file_caricato.name) == 0:
                        blocchi_sync = store_pgvector.estrai_blocchi_documento(file_caricato.name, file_caricato.getvalue())
                        if blocchi_sync:
                            store_pgvector.incasella_e_salva(dominio_doc, file_caricato.name, blocchi_sync)
                    tot_ram = _conta_frammenti_ram_sicuro()
                    st.write(f"1. Archivio attivo in memoria: **{tot_ram} frammenti** pronti per la verifica.")
                    st.write("2. Ricerca ibrida RRF (EWD472), calcolo precondizione wp(S, R) e filtro Zero Mucchio...")
                    esito = risolutore_artigiano.risolvi_da_artigiano(
                        problema_utente,
                        dominio=dominio_scelto,
                        cercatore_esterno_fn=cercatore_fn,
                        ipotesi_gia_escluse=lista_escluse,
                        llm_fn=llm_selezionato_fn,
                    )
                    st.write(
                        f"3. Semaforo: **{esito['semaforo']}** (s_max={esito['s_max']}) | "
                        f"Nodo Tri-Colore (EWD496A): **{esito['colore_nodo_ewd496a']}** "
                        f"(Percentuali conservate: {esito['percentuali_conservate']})"
                    )
                    stato_diag.update(
                        label=(
                            f"Analisi completata — Semaforo: {esito['semaforo']} (s_max={esito['s_max']}) | "
                            f"Barriera Numerica (EWD496A): Nodo {esito['colore_nodo_ewd496a']}"
                        ),
                        state="complete",
                        expanded=False,
                    )

                st.subheader("Risposta Finale (Metodo Artigiano — Zero Mucchio)")
                testo_discorsivo = esito.get("risposta_discorsiva", "")
                if not testo_discorsivo and hasattr(risolutore_artigiano, "formatta_risposta_artigiano_leggibile"):
                    testo_discorsivo = risolutore_artigiano.formatta_risposta_artigiano_leggibile(
                        esito["risultato"], esito["modalita"]
                    )
                st.write_stream(_stream_testo_parole(testo_discorsivo))

                with st.expander("Dettagli Tecnici: Frammenti PDF Estratti & Schema JSON (THE / EWD401 / EWD496A)"):
                    frammenti_letti = esito.get("frammenti_usati", [])
                    if frammenti_letti:
                        st.markdown("**Frammenti certificati estratti dal PDF / Archivio:**")
                        for idx_f, txt_f in enumerate(frammenti_letti, start=1):
                            st.info(f"**Frammento {idx_f}:**\n{txt_f}")
                    st.markdown("**Oggetto Strutturato JSON (Pydantic Validated):**")
                    st.json(esito["risultato"])
            except Exception as err:
                logging_bottega.log_exception("Errore risolutore artigiano Streamlit", "APP_ARTIGIANO_001", err)
                st.error(
                    f"Unable to reach the selected AI provider ({err}). "
                    "Check the sidebar or use Tab 3 (Free Web Bridge)."
                )

with tab_ponte_web:
    st.subheader("Use Free ChatGPT, DeepSeek or Gemini via Browser with Bottega's Protection")
    with st.expander("Show 'Universal Pocket Prompt' for Custom Instructions on Smartphone/Web"):
        st.code(PROMPT_TASCHINO_UNIVERSALE, language="text")

    problema_web = st.text_area(
        "Step 1 — Write your technical or accounting problem (in EN, ES, IT, etc.):",
        value="Importing aluminum profiles TARIC code 7604210000 origin CN for 14.400 EUR: which ordinary duty and antidumping apply?",
        height=90,
    )
    escluse_web = st.text_input(
        "Hypotheses already excluded in the field (optional, comma-separated):",
        placeholder="e.g. intra-EU duty exemption",
    )

    frammenti_contesto_web = []
    query_web_tradotta = client_ollama.traduci_query_per_ricerca(problema_web)
    try:
        rag_web = store_pgvector.recupera_con_semaforo(query_web_tradotta, dominio=dominio_doc, top_k=3)
        if rag_web.get("frammenti"):
            frammenti_contesto_web = [
                (f.get("sezione", "Archive"), f.get("testo", ""))
                for f in rag_web["frammenti"]
            ]
    except Exception:
        pass
    if not frammenti_contesto_web:
        frammenti_contesto_web = _cercatore_cascata_ui(problema_web)

    lista_escluse_web = [x.strip() for x in escluse_web.split(",") if x.strip()]
    prompt_pronto = risolutore_artigiano.genera_prompt_ponte_web_gratuito(
        problema_web,
        frammenti_contesto_web,
        ipotesi_gia_escluse=lista_escluse_web,
    )
    st.text_area(
        "Copy this Structured Prompt and paste it into Free ChatGPT, DeepSeek or Gemini:",
        value=prompt_pronto,
        height=210,
    )

    risposta_incollata = st.text_area(
        "Step 2 — Paste the response received from ChatGPT / DeepSeek / Gemini to verify its numbers:",
        height=130,
        placeholder="Paste the text generated by the web chat here...",
    )
    if st.button("Verify Response with Tri-Color Write Barrier (EWD496A) & Decimal (EWD145)"):
        if not risposta_incollata.strip():
            st.warning("Please paste the web chat response first.")
        else:
            contesto_verifica = f"{problema_web}\n" + "\n".join(
                f"{sez}: {txt}" for sez, txt in frammenti_contesto_web
            )
            colore, orfane = grounding_numerico.classifica_nodo_tricolore(risposta_incollata, contesto_verifica)
            pct_ok = grounding_numerico.verifica_conservazione_percentuali_decimal(risposta_incollata, contesto_verifica)
            if colore == "NERO" and pct_ok:
                st.success(
                    "Certified BLACK Node (EWD496A): all numbers, amounts, and percentages "
                    "match the official sources."
                )
            else:
                st.error(
                    f"GREY Node Blocked by Write Barrier! Hallucinated or altered numbers: {orfane} | "
                    f"Official percentages preserved: {pct_ok}"
                )
