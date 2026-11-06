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

_VERSIONE_MODULI_THE = "2026.11.06.v5"


def _allinea_moduli_in_memoria() -> None:
    """Forces Python on Streamlit Cloud to reload Layers 0..3 from disk when a new git commit is deployed,
    preventing stale sys.modules cache and ImportError while preserving the in-memory PDF archive."""
    necessita_reload = (
        st.session_state.get("_versione_moduli_the") != _VERSIONE_MODULI_THE
        or not hasattr(store_pgvector, "conta_frammenti_archivio_ram")
        or not hasattr(store_pgvector, "normalizza_spazi_testo_pdf")
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
        for voce in archivio_precedente:
            if "testo" in voce:
                voce["testo"] = store_pgvector.normalizza_spazi_testo_pdf(voce["testo"])
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
            chiave_doc = f"{dominio_doc}:{singolo_file.name}:{dim_file}"
            info_esistente = archivio_sess.get(singolo_file.name)
            in_ram = _conta_frammenti_ram_sicuro(singolo_file.name)

            if (
                clic_salva
                or info_esistente is None
                or info_esistente.get("chiave") != chiave_doc
                or in_ram == 0
            ):
                try:
                    blocchi_doc = store_pgvector.estrai_blocchi_documento(singolo_file.name, raw_bytes)
                    if not blocchi_doc:
                        st.warning(f"No readable text found in '{singolo_file.name}'.")
                    else:
                        try:
                            store_pgvector.inizializza_schema()
                        except psycopg2.Error:
                            pass
                        n_ins = store_pgvector.incasella_e_salva(dominio_doc, singolo_file.name, blocchi_doc)
                        archivio_sess[singolo_file.name] = {
                            "chiave": chiave_doc,
                            "dominio": dominio_doc,
                            "raw_bytes": raw_bytes,
                            "size_bytes": dim_file,
                            "n_frammenti": len(blocchi_doc),
                            "n_nuovi": n_ins,
                        }
                except Exception as err:
                    logging_bottega.log_exception(
                        "Errore indicizzazione documento caricato", "APP_DOC_001", err
                    )
                    st.error(f"Could not read document '{singolo_file.name}': {err}")

    archivio_attivo = st.session_state.get("documenti_archivio_sessione", {})
    if archivio_attivo:
        tot_docs = len(archivio_attivo)
        tot_frammenti = sum(v["n_frammenti"] for v in archivio_attivo.values())
        tot_mb = sum(v["size_bytes"] for v in archivio_attivo.values()) / (1024 * 1024)
        st.success(
            f"Active Archive: {tot_docs}/{max_docs} documents indexed "
            f"({tot_frammenti} total fragments, {tot_mb:.2f} MB / {max_mb} MB)."
        )
        with st.expander(f"Loaded Documents ({tot_docs}/{max_docs})"):
            for idx_d, (nome_d, meta_d) in enumerate(archivio_attivo.items(), start=1):
                st.caption(
                    f"{idx_d}. {nome_d} — {meta_d['n_frammenti']} fragments "
                    f"({meta_d['dominio']}, {meta_d['size_bytes'] / (1024 * 1024):.2f} MB)"
                )
            if st.button("Clear All Uploaded Documents"):
                st.session_state["documenti_archivio_sessione"] = {}
                if hasattr(store_pgvector, "_ARCHIVIO_MEMORIA_RAM"):
                    store_pgvector._ARCHIVIO_MEMORIA_RAM.clear()
                st.rerun()

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
                    for nome_sync, meta_sync in st.session_state.get("documenti_archivio_sessione", {}).items():
                        if _conta_frammenti_ram_sicuro(nome_sync) == 0:
                            blocchi_sync = store_pgvector.estrai_blocchi_documento(
                                nome_sync, meta_sync["raw_bytes"]
                            )
                            if blocchi_sync:
                                store_pgvector.incasella_e_salva(
                                    meta_sync["dominio"], nome_sync, blocchi_sync
                                )
                    tot_ram = _conta_frammenti_ram_sicuro()
                    st.write(f"1. Active Archive in memory: **{tot_ram} fragments** ready for verification.")
                    st.write("2. Hybrid RRF Search (EWD472), wp(S, R) precondition & Zero-Clutter filter...")
                    esito = risolutore_artigiano.risolvi_da_artigiano(
                        problema_utente,
                        dominio=dominio_scelto,
                        cercatore_esterno_fn=cercatore_fn,
                        ipotesi_gia_escluse=lista_escluse,
                        llm_fn=llm_selezionato_fn,
                    )
                    lingua_risp = esito.get("lingua", "it")
                    st.write(
                        f"3. Semaphore: **{esito['semaforo']}** (s_max={esito['s_max']}) | "
                        f"Tri-Color Node (EWD496A): **{esito['colore_nodo_ewd496a']}** "
                        f"(Percentages preserved: {esito['percentuali_conservate']})"
                    )
                    if lingua_risp == "en":
                        etichetta_stato = (
                            f"Analysis complete — Semaphore: {esito['semaforo']} (s_max={esito['s_max']}) | "
                            f"Numeric Barrier (EWD496A): Node {esito['colore_nodo_ewd496a']}"
                        )
                        titolo_risp = "Final Answer (Craftsman Method — Zero Clutter)"
                        titolo_expander = "Technical Details: Extracted PDF Fragments & JSON Schema (THE / EWD401 / EWD496A)"
                    elif lingua_risp == "es":
                        etichetta_stato = (
                            f"Análisis completado — Semáforo: {esito['semaforo']} (s_max={esito['s_max']}) | "
                            f"Barrera Numérica (EWD496A): Nodo {esito['colore_nodo_ewd496a']}"
                        )
                        titolo_risp = "Respuesta Final (Método Artesano — Cero Montón)"
                        titolo_expander = "Detalles Técnicos: Fragmentos PDF Extraídos y Esquema JSON (THE / EWD401 / EWD496A)"
                    else:
                        etichetta_stato = (
                            f"Analisi completata — Semaforo: {esito['semaforo']} (s_max={esito['s_max']}) | "
                            f"Barriera Numerica (EWD496A): Nodo {esito['colore_nodo_ewd496a']}"
                        )
                        titolo_risp = "Risposta Finale (Metodo Artigiano — Zero Mucchio)"
                        titolo_expander = "Dettagli Tecnici: Frammenti PDF Estratti & Schema JSON (THE / EWD401 / EWD496A)"

                    stato_diag.update(
                        label=etichetta_stato,
                        state="complete",
                        expanded=False,
                    )

                st.subheader(titolo_risp)
                testo_discorsivo = esito.get("risposta_discorsiva", "")
                if not testo_discorsivo and hasattr(risolutore_artigiano, "formatta_risposta_artigiano_leggibile"):
                    testo_discorsivo = risolutore_artigiano.formatta_risposta_artigiano_leggibile(
                        esito["risultato"], esito["modalita"], lingua=lingua_risp
                    )
                st.write_stream(_stream_testo_parole(testo_discorsivo))

                with st.expander(titolo_expander):
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
