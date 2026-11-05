#!/usr/bin/env python3
"""Layer 4 (THE): Multilingual Streamlit Dashboard (EN / ES / IT) with Free Cloud APIs,
local PostgreSQL document uploader and Free Web Bridge for ChatGPT / DeepSeek / Gemini."""

import tempfile
from pathlib import Path
import streamlit as st

from logging_bottega import log_exception
from anatomia_ast import analizza_codice_ast
from grounding_numerico import (
    classifica_nodo_tricolore,
    verifica_conservazione_percentuali_decimal,
)
from store_pgvector import (
    incasella_e_salva,
    inizializza_schema,
    recupera_con_semaforo,
)
from client_ollama import costruisci_llm_fn, traduci_query_per_ricerca
from cascata_strutturata import esegui_cascata
from risolutore_artigiano import (
    genera_prompt_ponte_web_gratuito,
    risolvi_da_artigiano,
)
from seed_bottega import cerca_nel_prontuario_esterno

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

st.set_page_config(page_title="Bottega Leonardesca & THE Engine", layout="wide")
st.title("Bottega Leonardesca — THE Architecture (EWD196), Hybrid RRF RAG & Diagnostic Solver")
st.caption("Multilingual Input Enabled: Write in English, Español, Italiano or any language — search is automatically translated.")

with st.sidebar:
    st.header("1. AI Engine (Local or Free Cloud)")
    provider_ui = st.selectbox(
        "Select AI Provider:",
        ["ollama", "gemini", "groq", "openrouter", "deepseek", "openai"],
        help="Gemini (Google AI Studio), Groq and OpenRouter offer a Free Tier without credit card.",
    )
    api_key_ui = ""
    model_ui = ""
    if provider_ui != "ollama":
        api_key_ui = st.text_input(
            f"API Key ({provider_ui.upper()}):",
            type="password",
            help="Leave blank if LLM_API_KEY is already set in .env or Streamlit Secrets.",
        )
        model_ui = st.text_input(
            "Model (optional, press Enter for free default):",
            placeholder="e.g. gemini-2.5-flash or openrouter/free",
        )
    else:
        st.caption("Local mode active on 127.0.0.1:11434 (Ollama).")

    st.divider()
    st.header("2. Local PostgreSQL Archive")
    dominio_doc = st.selectbox(
        "Target Domain:",
        ["leonardo", "dijkstra", "antirez"],
        key="dom_upload",
    )
    file_caricato = st.file_uploader(
        "Upload a document (.txt, .md, .csv, .py) into your local Postgres:",
        type=["txt", "md", "csv", "py"],
    )
    if file_caricato is not None:
        if st.button("Save to my Local PostgreSQL"):
            testo_doc = file_caricato.getvalue().decode("utf-8", errors="replace")
            paragrafi = [p.strip() for p in testo_doc.split("\n\n") if p.strip()]
            blocchi_doc = [
                (f"Paragraph {i}", p) for i, p in enumerate(paragrafi, start=1)
            ]
            try:
                inizializza_schema()
                n_ins = incasella_e_salva(dominio_doc, file_caricato.name, blocchi_doc)
                st.success(
                    f"Saved {n_ins} new fragments in PostgreSQL (domain '{dominio_doc}')."
                )
            except Exception:
                log_exception("Errore salvataggio documento in PostgreSQL", "APP_DB_001")
                st.error(
                    "Local PostgreSQL unreachable on 127.0.0.1:5432. "
                    "Start the project with Docker to save documents into your database."
                )

llm_selezionato_fn = costruisci_llm_fn(
    provider=provider_ui,
    api_key=api_key_ui if api_key_ui else None,
    model=model_ui if model_ui else None,
)


def _cercatore_cascata_ui(query_ricerca: str):
    return cerca_nel_prontuario_esterno(
        query_ricerca,
        provider=provider_ui,
        api_key=api_key_ui if api_key_ui else None,
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
                    dati_ast = analizza_codice_ast(codice_incollato)
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
                    analizza_codice_ast(codice_incollato)
                except SyntaxError as err:
                    st.error(f"Syntax error at line {err.lineno}: {err.msg}")
                    st.stop()

                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp_path = Path(tmpdir) / "codice_analizzato.py"
                    tmp_path.write_text(codice_incollato, encoding="utf-8")
                    try:
                        with st.spinner("Running AST, Hybrid RRF RAG and 3-Layer Cascade..."):
                            referto = esegui_cascata(str(tmp_path), llm_fn=llm_selezionato_fn)
                        st.markdown(referto)
                        st.download_button(
                            "Download Markdown Report",
                            referto,
                            file_name="referto_bottega.md",
                            mime="text/markdown",
                        )
                    except Exception:
                        log_exception("Errore esecuzione cascata Streamlit", "APP_CASCATA_001")
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
        dominio_scelto = st.selectbox("Guiding Domain:", ["leonardo", "dijkstra", "antirez"])
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
                with st.spinner("Translating search, checking RAG Semaphore, wp(S,R) & Tri-Color Write Barrier..."):
                    esito = risolvi_da_artigiano(
                        problema_utente,
                        dominio=dominio_scelto,
                        cercatore_esterno_fn=cercatore_fn,
                        ipotesi_gia_escluse=lista_escluse,
                        llm_fn=llm_selezionato_fn,
                    )
                st.info(
                    f"Semaphore: {esito['semaforo']} (s_max={esito['s_max']}) | "
                    f"Mode: {esito['modalita']} | "
                    f"External search triggered: {esito['ricerca_esterna_eseguita']} | "
                    f"Tri-Color Node (EWD496A): {esito['colore_nodo_ewd496a']}"
                )
                st.json(esito["risultato"])
            except Exception:
                log_exception("Errore risolutore artigiano Streamlit", "APP_ARTIGIANO_001")
                st.error(
                    "Unable to reach the selected AI provider. "
                    "Check the API key in the sidebar or use Tab 3 (Free Web Bridge)."
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
    query_web_tradotta = traduci_query_per_ricerca(problema_web)
    try:
        rag_web = recupera_con_semaforo(query_web_tradotta, dominio=dominio_doc, top_k=3)
        if rag_web.get("frammenti"):
            frammenti_contesto_web = [
                (f.get("sezione", "Local DB"), f.get("testo", ""))
                for f in rag_web["frammenti"]
            ]
    except Exception:
        pass
    if not frammenti_contesto_web:
        frammenti_contesto_web = _cercatore_cascata_ui(problema_web)

    lista_escluse_web = [x.strip() for x in escluse_web.split(",") if x.strip()]
    prompt_pronto = genera_prompt_ponte_web_gratuito(
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
            colore, orfane = classifica_nodo_tricolore(risposta_incollata, contesto_verifica)
            pct_ok = verifica_conservazione_percentuali_decimal(risposta_incollata, contesto_verifica)
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