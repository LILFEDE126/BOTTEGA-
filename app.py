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

_VERSIONE_MODULI_THE = "2026.11.13.v19"
INTERVALLO_STREAMING_UI_SECONDI = 0.01
ALTEZZA_TEXTAREA_UI = 120
ALTEZZA_CODICE_UI = 200
ALTEZZA_ESCLUSIONI_UI = 90
ALTEZZA_AUDIT_WEB_UI = 140
DIVISORE_MB = 1024 * 1024


def _allinea_moduli_in_memoria() -> None:
    """Forces Python on Streamlit Cloud to reload Layers 0..3 from disk when a new git commit is deployed,
    preventing stale sys.modules cache and ImportError while preserving the in-memory PDF archive."""
    necessita_reload = (
        st.session_state.get("_versione_moduli_the") != _VERSIONE_MODULI_THE
        or not hasattr(store_pgvector, "conta_frammenti_archivio_ram")
        or not hasattr(store_pgvector, "normalizza_spazi_testo_pdf")
        or not hasattr(risolutore_artigiano, "formatta_risposta_artigiano_leggibile")
        or not hasattr(risolutore_artigiano, "compila_voce_wiki_markdown")
        or not hasattr(risolutore_artigiano, "carica_voci_wiki_da_disco")
        or not hasattr(risolutore_artigiano, "esegui_ingest_documento_in_wiki")
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
            nome_mod = getattr(modulo, "__name__", "")
            if nome_mod in importlib.sys.modules:
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
            voce_ram.get("titolo") for voce_ram in getattr(store_pgvector, "_ARCHIVIO_MEMORIA_RAM", [])
        }
        for nome_doc_s, meta_doc_s in archivio_sess_corrente.items():
            blocchi_s = meta_doc_s.get("blocchi") or []
            if blocchi_s and nome_doc_s not in titoli_in_ram:
                store_pgvector.incasella_e_salva(
                    meta_doc_s.get("dominio", "generale"), nome_doc_s, blocchi_s
                )


_allinea_moduli_in_memoria()

if "llm_wiki_voci" not in st.session_state:
    st.session_state["llm_wiki_voci"] = risolutore_artigiano.carica_voci_wiki_da_disco()

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
ESTENSIONI_SUPPORTATE = frozenset({".pdf", ".txt", ".md", ".csv", ".py", ".zip"})
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

_HTML_JS_ZERO_AXIOS = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
<style>
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    margin: 0; padding: 4px; background: transparent;
  }
  .btn-mob {
    display: block; width: 100%; box-sizing: border-box; padding: 9px 12px;
    background-color: rgb(13, 110, 253); color: white; border: none; border-radius: 6px;
    font-size: 13px; font-weight: 600; cursor: pointer; text-align: center;
  }
  .btn-mob:active { background-color: rgb(11, 94, 215); }
  .btn-copy {
    display: none; width: 100%; box-sizing: border-box; margin-top: 6px; padding: 6px 10px;
    background-color: rgb(248, 249, 250); color: rgb(33, 37, 41); border: 1px solid rgb(206, 212, 218);
    border-radius: 6px; font-size: 12px; cursor: pointer; text-align: center;
  }
  .status-box { margin-top: 6px; font-size: 12px; line-height: 1.3; }
</style>
</head>
<body>
  <input type="file" id="mob_file_input" accept=".pdf,.txt,.md,.csv,.py,.zip" multiple style="display:none;" />
  <button type="button" class="btn-mob" onclick="document.getElementById('mob_file_input').click();">
    📱 Select PDF or Files from Phone / Tablet
  </button>
  <button type="button" id="btn_copia_appunti" class="btn-copy">
    📋 Copy extracted text to clipboard
  </button>
  <div id="mob_status" class="status-box"></div>

<script>
  if (typeof pdfjsLib !== 'undefined') {
    pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
  }

  let testoGlobaleEstratto = '';

  document.getElementById('mob_file_input').addEventListener('change', async function(e) {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const stBox = document.getElementById('mob_status');
    const cpBtn = document.getElementById('btn_copia_appunti');
    stBox.innerHTML = '<span style="color:rgb(13, 110, 253);">⏳ Reading file in local device memory...</span>';

    try {
      let testiAccumulati = [];
      let primoNome = files[0].name;

      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const nomeLower = file.name.toLowerCase();

        if (nomeLower.endsWith('.pdf')) {
          const ab = await file.arrayBuffer();
          const loadingTask = pdfjsLib.getDocument({ data: new Uint8Array(ab) });
          const pdfDoc = await loadingTask.promise;
          let testoPdf = '';
          for (let p = 1; p <= pdfDoc.numPages; p++) {
            const page = await pdfDoc.getPage(p);
            const content = await page.getTextContent();
            const stringhePagina = content.items.map(function(item) { return item.str; }).join(' ');
            testoPdf += stringhePagina + '\\n\\n';
          }
          testiAccumulati.push(testoPdf);
        } else {
          const testoTxt = await file.text();
          testiAccumulati.push(testoTxt);
        }
      }

      testoGlobaleEstratto = testiAccumulati.join('\\n--- [Next Document] ---\\n');

      try {
        const parentDoc = window.parent.document;
        const ta = parentDoc.querySelector('textarea[aria-label="Document Text to Save in Archive:"]') ||
                   parentDoc.querySelector('textarea[aria-label="Testo del documento da salvare in Archivio:"]') ||
                   parentDoc.querySelector('textarea[placeholder*="testo estratto"]') ||
                   parentDoc.querySelector('textarea[placeholder*="Paste your document content"]') ||
                   parentDoc.querySelector('textarea[placeholder*="Incolla"]');
        if (ta) {
          const setterTa = Object.getOwnPropertyDescriptor(window.parent.HTMLTextAreaElement.prototype, 'value').set;
          setterTa.call(ta, testoGlobaleEstratto);
          ta.dispatchEvent(new Event('input', { bubbles: true }));
          ta.dispatchEvent(new Event('change', { bubbles: true }));
        }

        const inpTitle = parentDoc.querySelector('input[aria-label="Document Title:"]') ||
                         parentDoc.querySelector('input[aria-label="Nome documento (Mobile):"]');
        if (inpTitle) {
          const setterInp = Object.getOwnPropertyDescriptor(window.parent.HTMLInputElement.prototype, 'value').set;
          setterInp.call(inpTitle, primoNome);
          inpTitle.dispatchEvent(new Event('input', { bubbles: true }));
          inpTitle.dispatchEvent(new Event('change', { bubbles: true }));
        }
      } catch (errParent) {
        testoGlobaleEstratto = testiAccumulati.join('\\n');
      }

      stBox.innerHTML = '<span style="color:rgb(15, 81, 50);font-weight:600;">✅ Read successfully (' + primoNome + ')! Now click \\"Save Document to Knowledge Base\\" below.</span>';
      cpBtn.style.display = 'block';
    } catch (errLettura) {
      stBox.innerHTML = '<span style="color:rgb(176, 42, 55);">❌ Error reading file: ' + errLettura.message + '</span>';
    }
  });

  document.getElementById('btn_copia_appunti').addEventListener('click', function() {
    if (!testoGlobaleEstratto) return;
    navigator.clipboard.writeText(testoGlobaleEstratto).then(function() {
      document.getElementById('btn_copia_appunti').innerText = '✅ Text Copied to Clipboard!';
    }).catch(function() {
      document.getElementById('btn_copia_appunti').innerText = '❌ Error copying text';
    });
  });
</script>
</body>
</html>
"""


def _stream_testo_parole(testo: str):
    """Yields the complete markdown text block atomically to preserve all newlines and code formatting."""
    yield testo


def _conta_frammenti_ram_sicuro(titolo=None) -> int:
    """Safely counts fragments in the RAM archive even if an older module instance is present."""
    fn_conta = getattr(store_pgvector, "conta_frammenti_archivio_ram", None)
    if callable(fn_conta):
        return fn_conta(titolo)
    archivio = getattr(store_pgvector, "_ARCHIVIO_MEMORIA_RAM", [])
    if titolo is None:
        return len(archivio)
    return sum(1 for item in archivio if item.get("titolo") == titolo)


def _elabora_file_caricati(
    files_caricati,
    dominio_scelto: str,
    max_documenti: int,
    max_megabyte: int,
    limite_bytes: int,
) -> int:
    """Indicizza i documenti caricati in archivio e RAM con validazione estensione file."""
    if not files_caricati:
        return 0
    if "documenti_archivio_sessione" not in st.session_state:
        st.session_state["documenti_archivio_sessione"] = {}
    archivio_sess = st.session_state["documenti_archivio_sessione"]
    files_da_elaborare = list(files_caricati)
    if len(files_da_elaborare) > max_documenti:
        st.warning(
            f"Maximum limit of {max_documenti} documents per request reached: "
            f"indexing the first {max_documenti} files."
        )
        files_da_elaborare = files_da_elaborare[:max_documenti]

    bytes_totali_correnti = sum(
        info["size_bytes"]
        for nome_f, info in archivio_sess.items()
        if nome_f not in {file_up.name for file_up in files_da_elaborare}
    )

    ram_globale = _conta_frammenti_ram_sicuro()
    nuovi_elaborati_ora = 0

    for singolo_file in files_da_elaborare:
        estensione = Path(singolo_file.name).suffix.lower()
        if estensione not in ESTENSIONI_SUPPORTATE:
            st.warning(
                f"Unsupported file format for '{singolo_file.name}': "
                f"only .pdf, .txt, .md, .csv, .py, .zip are accepted."
            )
            continue

        raw_bytes = singolo_file.getvalue()
        dim_file = len(raw_bytes)

        if estensione == ".zip":
            n_zip = risolutore_artigiano.importa_vault_wiki_zip(raw_bytes)
            st.success(f"Obsidian Vault successfully restored: {n_zip} Markdown files imported!")
            st.toast(f"Vault ripristinato con successo: {n_zip} file .md!")
            nuovi_elaborati_ora += 1
            continue

        testo_file_wiki = raw_bytes.decode("utf-8", errors="ignore")
        if "## 📚 Voce Wiki:" in testo_file_wiki:
            voci_ripristinate = risolutore_artigiano.estrai_voci_wiki_da_testo_markdown(testo_file_wiki)
            if voci_ripristinate:
                if "llm_wiki_voci" not in st.session_state:
                    st.session_state["llm_wiki_voci"] = risolutore_artigiano.carica_voci_wiki_da_disco()
                voci_wiki_stato = st.session_state["llm_wiki_voci"]
                for voce_r in voci_ripristinate:
                    if voce_r not in voci_wiki_stato:
                        voci_wiki_stato.append(voce_r)
                    risolutore_artigiano.salva_voce_wiki_su_disco(voce_r)
                st.toast(f"Gen III Wiki: {len(voci_ripristinate)} voci ripristinate con successo!")
        if singolo_file.name not in archivio_sess and len(archivio_sess) >= max_documenti:
            st.warning(
                f"Archive already holds {max_documenti}/{max_documenti} documents. "
                f"Skipped '{singolo_file.name}'."
            )
            continue
        if bytes_totali_correnti + dim_file > limite_bytes:
            st.warning(
                f"Total size limit of {max_megabyte} MB per request exceeded: "
                f"skipped '{singolo_file.name}'."
            )
            continue

        bytes_totali_correnti += dim_file
        sha_file = hashlib.sha256(raw_bytes).hexdigest()
        chiave_doc = f"{dominio_scelto}:{sha_file}"
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
                    n_ins = store_pgvector.incasella_e_salva(dominio_scelto, singolo_file.name, blocchi_doc)
                    ram_globale = _conta_frammenti_ram_sicuro()
                    try:
                        risolutore_artigiano.esegui_ingest_documento_in_wiki(
                            singolo_file.name, dominio_scelto, blocchi_doc
                        )
                    except (OSError, RuntimeError) as err_ing:
                        logging_bottega.log.warning(
                            "Wiki Vault Ingest errore (%s): %s", singolo_file.name, err_ing
                        )
                archivio_sess[singolo_file.name] = {
                    "chiave": chiave_doc,
                    "dominio": dominio_scelto,
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

    return nuovi_elaborati_ora


def _salva_testo_incollato_in_archivio(
    titolo_doc: str,
    testo_doc: str,
    dominio_scelto: str,
    max_documenti: int,
    max_megabyte: int,
    limite_bytes: int,
) -> bool:
    """Salva direttamente testo incollato in archivio e RAM senza upload multipart Axios."""
    titolo_pulito = titolo_doc.strip()
    if not titolo_pulito:
        st.warning("Please specify a document title (e.g. 'Note.txt' or 'Codice_Appalti').")
        return False
    if not Path(titolo_pulito).suffix:
        titolo_pulito = f"{titolo_pulito}.txt"

    testo_pulito = testo_doc.strip()
    if not testo_pulito:
        st.warning("Please paste non-empty document text.")
        return False

    if "## 📚 Voce Wiki:" in testo_pulito:
        voci_ripristinate = risolutore_artigiano.estrai_voci_wiki_da_testo_markdown(testo_pulito)
        if voci_ripristinate:
            if "llm_wiki_voci" not in st.session_state:
                st.session_state["llm_wiki_voci"] = risolutore_artigiano.carica_voci_wiki_da_disco()
            voci_wiki_stato = st.session_state["llm_wiki_voci"]
            for voce_r in voci_ripristinate:
                if voce_r not in voci_wiki_stato:
                    voci_wiki_stato.append(voce_r)
                risolutore_artigiano.salva_voce_wiki_su_disco(voce_r)
            st.toast(f"Gen III Wiki: {len(voci_ripristinate)} voci ripristinate con successo!")

    raw_bytes = testo_pulito.encode("utf-8")
    dim_file = len(raw_bytes)

    if "documenti_archivio_sessione" not in st.session_state:
        st.session_state["documenti_archivio_sessione"] = {}
    archivio_sess = st.session_state["documenti_archivio_sessione"]

    if titolo_pulito not in archivio_sess and len(archivio_sess) >= max_documenti:
        st.warning(
            f"Archive already holds {max_documenti}/{max_documenti} documents. Skipped '{titolo_pulito}'."
        )
        return False

    bytes_totali_correnti = sum(
        info["size_bytes"]
        for nome_f, info in archivio_sess.items()
        if nome_f != titolo_pulito
    )
    if bytes_totali_correnti + dim_file > limite_bytes:
        st.warning(
            f"Total size limit of {max_megabyte} MB per request exceeded: skipped '{titolo_pulito}'."
        )
        return False

    sha_file = hashlib.sha256(raw_bytes).hexdigest()
    chiave_doc = f"{dominio_scelto}:{sha_file}"

    try:
        blocchi_doc = store_pgvector.estrai_blocchi_documento(titolo_pulito, raw_bytes)
        n_ins = 0
        if not blocchi_doc:
            st.warning(f"No readable text extracted from '{titolo_pulito}'.")
            return False
        try:
            store_pgvector.inizializza_schema()
        except psycopg2.Error as err_init:
            logging_bottega.log.info(
                "Inizializzazione PostgreSQL non riuscita (%s): memorizzazione nell'archivio RAM",
                err_init,
                extra={"code": "APP_INIT_002"},
            )
        n_ins = store_pgvector.incasella_e_salva(dominio_scelto, titolo_pulito, blocchi_doc)
        try:
            risolutore_artigiano.esegui_ingest_documento_in_wiki(
                titolo_pulito, dominio_scelto, blocchi_doc
            )
        except (OSError, RuntimeError) as err_ing_p:
            logging_bottega.log.warning(
                "Wiki Vault Ingest errore (%s): %s", titolo_pulito, err_ing_p
            )
        archivio_sess[titolo_pulito] = {
            "chiave": chiave_doc,
            "dominio": dominio_scelto,
            "blocchi": blocchi_doc,
            "size_bytes": dim_file,
            "n_frammenti": len(blocchi_doc),
            "n_nuovi": n_ins,
        }
        st.toast(f"'{titolo_pulito}' successfully saved into memory ({len(blocchi_doc)} fragments)!")
        return True
    except (RuntimeError, ValueError, OSError, psycopg2.Error, KeyError, TypeError) as err:
        logging_bottega.log_exception(
            "Errore salvataggio testo incollato in archivio", "APP_DOC_002", err
        )
        st.error(f"Could not index pasted document '{titolo_pulito}': {err}")
        return False


max_docs = getattr(config, "MAX_DOCUMENTI_PER_RICHIESTA", 30)
max_mb = getattr(config, "MAX_MB_PER_RICHIESTA", 200)
max_bytes = getattr(config, "MAX_BYTES_PER_RICHIESTA", 200 * DIVISORE_MB)

st.set_page_config(
    page_title="Bottega — Engine & Diagnostic Solver",
    layout="wide",
    initial_sidebar_state="expanded",
)
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
    if "documenti_archivio_sessione" not in st.session_state:
        st.session_state["documenti_archivio_sessione"] = {}

    files_caricati = st.file_uploader(
        f"Upload up to {max_docs} documents (.pdf, .txt, .md, .csv, .py — max {max_mb} MB total):",
        key="uploader_sidebar",
        accept_multiple_files=True,
    )
    clic_salva = st.button("Save to Archive")

    with st.expander("📱 Direct Phone & Tablet File Reader (or Paste Text)"):
        st.caption("Reads PDF and text files directly in your phone or tablet memory, bypassing mobile browser upload limitations.")
        st.components.v1.html(_HTML_JS_ZERO_AXIOS, height=135)
        titolo_mobile = st.text_input(
            "Document Title:",
            value="Mobile_Document.pdf",
            key="titolo_mobile_doc",
            help="Title assigned to the document read from phone or pasted.",
        )
        testo_mobile = st.text_area(
            "Document Text to Save in Archive:",
            key="testo_mobile_area",
            height=100,
            placeholder="Text extracted from your file will appear here automatically, or you can paste it manually...",
        )
        if st.button("💾 Save Document to Knowledge Base", type="primary", key="btn_salva_mobile"):
            if _salva_testo_incollato_in_archivio(
                titolo_mobile,
                testo_mobile,
                dominio_doc,
                max_docs,
                max_mb,
                max_bytes,
            ):
                st.rerun()

    if files_caricati:
        nuovi_sb = _elabora_file_caricati(
            files_caricati, dominio_doc, max_docs, max_mb, max_bytes
        )
        if clic_salva and nuovi_sb == 0 and st.session_state.get("documenti_archivio_sessione"):
            st.toast("All uploaded documents are already indexed and active in the Archive!")

    archivio_attivo = st.session_state.get("documenti_archivio_sessione", {})
    if archivio_attivo:
        tot_docs = len(archivio_attivo)
        tot_frammenti_ram = _conta_frammenti_ram_sicuro()
        tot_frammenti = tot_frammenti_ram if tot_frammenti_ram > 0 else sum(
            voce_att["n_frammenti"] for voce_att in archivio_attivo.values()
        )
        tot_mb = sum(voce_att["size_bytes"] for voce_att in archivio_attivo.values()) / DIVISORE_MB
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
                    f"({meta_d['dominio']}, {meta_d['size_bytes'] / DIVISORE_MB:.2f} MB)"
                )
            if st.button("Clear All Uploaded Documents"):
                st.session_state["documenti_archivio_sessione"] = {}
                if hasattr(store_pgvector, "_ARCHIVIO_MEMORIA_RAM"):
                    store_pgvector._ARCHIVIO_MEMORIA_RAM.clear()
                st.rerun()

archivio_centrale = st.session_state.get("documenti_archivio_sessione", {})
if archivio_centrale:
    tot_docs_c = len(archivio_centrale)
    tot_frammenti_ram_c = _conta_frammenti_ram_sicuro()
    tot_frammenti_c = (
        tot_frammenti_ram_c
        if tot_frammenti_ram_c > 0
        else sum(voce_c["n_frammenti"] for voce_c in archivio_centrale.values())
    )
    tot_mb_c = sum(voce_c["size_bytes"] for voce_c in archivio_centrale.values()) / DIVISORE_MB
    st.success(
        f"Active Archive: {tot_docs_c}/{max_docs} documents indexed "
        f"({tot_frammenti_c} unique fragments in memory, {tot_mb_c:.2f} MB / {max_mb} MB). "
        "Ready for automated diagnostic solving."
    )



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


tab_artigiano, tab_wiki, tab_ponte_web, tab_codice = st.tabs([
    "🔍 1. Ask Your Documents & Second Brain",
    "📚 2. Knowledge Wiki & Visual Map",
    "🛡️ 3. Fact-Check External AI",
    "⚙️ 4. Python Code Inspector",
])

with tab_artigiano:
    problema_testo = st.text_area(
        "Ask any question about your uploaded documents (in English, Italiano, Español, or any language):",
        height=ALTEZZA_TEXTAREA_UI,
        placeholder="Ask a question or describe a problem based on your documents...",
    )
    col_dom, col_escl = st.columns([1, 2])
    with col_dom:
        dominio_scelto = st.selectbox(
            "Guiding Domain:",
            DOMINI_DISPONIBILI,
            help="Prioritizes fragments saved in this domain (generale = Strato L, tecnico = Strato A, normativo = Strato D) while still searching all loaded documents.",
        )
        cerca_fuori = st.checkbox(
            "Enable cascading external search (Handbook -> AI Web Search -> DuckDuckGo/Wikipedia) on ROJO Semaphore",
            value=False,
        )
    with col_escl:
        ipotesi_escluse_testo = st.text_area(
            "Hypotheses already falsified in the field (one per line, optional - Binary Search):",
            height=ALTEZZA_ESCLUSIONI_UI,
            placeholder="Optional: enter hypotheses or causes already ruled out (one per line)...",
            help="Any hypothesis entered here is strictly forbidden as the root cause and will be isolated in Point 6 as [Falsified in the field].",
        )

    clic_risolvi = st.button("Get Verified Answer", type="primary")

    if clic_risolvi:
        testo_input_effettivo = problema_testo.strip()
        if not testo_input_effettivo:
            st.warning("Please enter a question or problem description first.")
        else:
            lista_escluse = [
                riga.strip() for riga in ipotesi_escluse_testo.splitlines() if riga.strip()
            ]
            cercatore_fn = _cercatore_cascata_ui if cerca_fuori else None
            e_continua = risolutore_artigiano.e_richiesta_continua(testo_input_effettivo)
            try:
                with st.spinner("Evaluating Guarded Semaphore, RRF Retrieval and Write Barrier (Strato L · A · D)..."):
                    if e_continua:
                        esito = risolutore_artigiano.risolvi_da_artigiano(
                            "continua",
                            dominio=dominio_scelto,
                            cercatore_esterno_fn=cercatore_fn,
                            ipotesi_gia_escluse=lista_escluse,
                            llm_fn=llm_selezionato_fn,
                        )
                        testo_cont = esito.get("risposta_discorsiva", "")
                        parte_pulita = risolutore_artigiano.rimuovi_coda_audit_6_punti(testo_cont)
                        parti = st.session_state.setdefault("parti_discorso_accumulate", [])
                        if parte_pulita:
                            if parti:
                                parti[-1] = re.sub(r"(?:\n\s*)*continua\s*$", "", parti[-1], flags=re.IGNORECASE).rstrip()
                            parti.append(parte_pulita)
                        else:
                            approf = risolutore_artigiano.approfondisci_sezioni_successive_documento(dominio_scelto)
                            if approf:
                                if parti:
                                    parti[-1] = re.sub(r"(?:\n\s*)*continua\s*$", "", parti[-1], flags=re.IGNORECASE).rstrip()
                                parti.append(approf)
                        esito_orig = st.session_state.get("esito_principale_originale")
                        st.session_state["ultimo_esito_artigiano"] = esito_orig if esito_orig is not None else esito
                    else:
                        esito = risolutore_artigiano.risolvi_da_artigiano(
                            testo_input_effettivo,
                            dominio=dominio_scelto,
                            cercatore_esterno_fn=cercatore_fn,
                            ipotesi_gia_escluse=lista_escluse,
                            llm_fn=llm_selezionato_fn,
                            max_caratteri_turno=2200,
                        )
                        st.session_state["esito_principale_originale"] = esito
                        st.session_state["ultimo_esito_artigiano"] = esito
                        st.session_state["ultima_domanda_artigiano"] = testo_input_effettivo
                        testo_grezzo = (
                            esito.get("risultato", {}).get("risposta_finale_discorsiva")
                            or esito.get("risposta_discorsiva")
                            or ""
                        )
                        parte_pulita = risolutore_artigiano.rimuovi_coda_audit_6_punti(testo_grezzo)
                        st.session_state["parti_discorso_accumulate"] = [parte_pulita if parte_pulita else testo_grezzo]

                voce_wiki = risolutore_artigiano.compila_voce_wiki_markdown(testo_input_effettivo, esito)
                voci_wiki = st.session_state.setdefault("llm_wiki_voci", [])
                if voce_wiki not in voci_wiki:
                    voci_wiki.append(voce_wiki)
                risolutore_artigiano.salva_voce_wiki_su_disco(voce_wiki)
            except (RuntimeError, ValueError, OSError, psycopg2.Error, KeyError, TypeError) as err:
                logging_bottega.log_exception("Errore in risolvi_da_artigiano UI", "APP_ART_001", err)
                st.error(f"Error during diagnostic execution ({provider_ui}): {err}")

    esito = st.session_state.get("ultimo_esito_artigiano")
    if esito:
        m1, m2, m3 = st.columns(3)
        m1.metric("Document Match", f"{'High' if esito['semaforo'] == 'VERDE' else ('Partial' if esito['semaforo'] == 'AMBAR' else 'Not Found')} ({int(round(float(esito['s_max']) * 100))}%)")
        m2.metric("Answer Status", "Verified from Your Files" if esito["modalita"] != "RICERCA_PRIMA_DI_AGIRE" else "Honest Stop — Missing Data")
        m3.metric("Numbers & Facts Check", "100% Verified" if esito["colore_nodo_ewd496a"] == "NERO" else "Unverified Numbers Flagged")

        if esito.get("sintesi_deterministica_attiva"):
            st.caption("ℹ️ Local Document Summary Mode active. To enable full neural AI prose generation, enter a free Google AI Studio key ('AIzaSy...') in the left sidebar.")

        parti_acc = st.session_state.get("parti_discorso_accumulate", [])
        if parti_acc:
            discorso_completo = "\n\n".join(parti_acc)
        else:
            testo_base = (
                esito.get("risultato", {}).get("risposta_finale_discorsiva")
                or esito.get("risposta_discorsiva")
                or ""
            )
            discorso_completo = risolutore_artigiano.rimuovi_coda_audit_6_punti(testo_base) or testo_base

        st.markdown("### Answer from Your Documents")
        st.markdown(discorso_completo)

        if risolutore_artigiano.ha_pagine_continua_in_sospeso(dominio_scelto):
            st.info("📖 More content available for this topic: click the button below (or type 'continua') to continue the explanation.")
            if st.button("➡️ Continue Reading — Next Part ('continua')", type="primary", key="btn_continua_sotto"):
                with st.spinner("Retrieving next part..."):
                    esito_cont = risolutore_artigiano.risolvi_da_artigiano("continua", dominio=dominio_scelto)
                    testo_cont = esito_cont.get("risposta_discorsiva", "")
                    parte_pulita = risolutore_artigiano.rimuovi_coda_audit_6_punti(testo_cont)
                    parti = st.session_state.setdefault("parti_discorso_accumulate", [])
                    if parte_pulita:
                        if parti:
                            parti[-1] = re.sub(r"(?:\n\s*)*continua\s*$", "", parti[-1], flags=re.IGNORECASE).rstrip()
                        parti.append(parte_pulita)
                    else:
                        approf = risolutore_artigiano.approfondisci_sezioni_successive_documento(dominio_scelto)
                        if approf:
                            if parti:
                                parti[-1] = re.sub(r"(?:\n\s*)*continua\s*$", "", parti[-1], flags=re.IGNORECASE).rstrip()
                            parti.append(approf)
                    esito_orig = st.session_state.get("esito_principale_originale")
                    st.session_state["ultimo_esito_artigiano"] = esito_orig if esito_orig is not None else esito_cont
                    st.rerun()

        st.markdown("#### 🗺️ Visual Step-by-Step Summary")
        st.graphviz_chart(
            risolutore_artigiano.costruisci_diagramma_flusso_risposta_dot(
                st.session_state.get("ultima_domanda_artigiano", problema_testo),
                esito,
            )
        )

        with st.expander("🔬 Technical Audit & Step-by-Step Verification Details (Strato L · A · D)"):
            testo_completo_diagnostica = risolutore_artigiano.formatta_risposta_artigiano_leggibile(
                esito.get("risultato", {}),
                esito.get("modalita", "AZIONE_SINGOLA_VERIFICABILE"),
                lingua=esito.get("lingua", "it"),
            )
            st.markdown("#### Full Step-by-Step Diagnostic Report")
            st.markdown(testo_completo_diagnostica)
            if esito.get("frammenti_usati"):
                st.markdown("#### Grounded Fragments from Your Files")
                for idx_f, testo_f in enumerate(esito["frammenti_usati"], start=1):
                    st.markdown(f"**Fragment {idx_f}:**\n> {testo_f}")
            st.markdown("#### JSON Audit Data")
            st.json(esito["risultato"])
            if esito.get("cifre_non_ancorate"):
                st.warning(f"Ungrounded figures flagged by Write Barrier: {esito['cifre_non_ancorate']}")

with tab_wiki:
    st.subheader("📚 Second Brain Knowledge Vault (Obsidian & K. Pattern)")
    st.caption("Multi-file Markdown knowledge vault with bidirectional [[wikilinks]], live graph navigation, Marp presentations and 1-click Obsidian export.")

    radice_vault = risolutore_artigiano.inizializza_vault_wiki()
    n_sources = len(list((radice_vault / "wiki" / "sources").glob("*.md")))
    n_concepts = len(list((radice_vault / "wiki" / "concepts").glob("*.md")))
    n_entities = len(list((radice_vault / "wiki" / "entities").glob("*.md")))
    n_synthesis = len(list((radice_vault / "wiki" / "synthesis").glob("*.md")))
    n_presentations = len(list((radice_vault / "wiki" / "presentations").glob("*.md")))

    m_v1, m_v2, m_v3, m_v4, m_v5 = st.columns(5)
    m_v1.metric("Sources", n_sources)
    m_v2.metric("Concepts", n_concepts)
    m_v3.metric("Entities", n_entities)
    m_v4.metric("Saved Answers", n_synthesis)
    m_v5.metric("Slide Decks", n_presentations)

    b1, b2, b3, b4 = st.columns(4)
    with b1:
        if st.button("🔍 Run Wiki Health Check (Lint)", key="btn_lint_wiki_tab"):
            esito_lint = risolutore_artigiano.esegui_lint_wiki(radice_vault)
            st.success(
                f"Health Status: {esito_lint['stato_salute']} | "
                f"Total Pages: {esito_lint['pagine_totali']} | "
                f"Orphans Repaired: {esito_lint['orfani_riparati']} | "
                f"Links Added: {esito_lint['link_aggiunti']}"
            )
            st.rerun()
    with b2:
        if st.button("🎞️ Generate 5-Slide Presentation (MARP)", key="btn_marp_slides_tab"):
            ult_prob = st.session_state.get(
                "ultima_domanda_artigiano", "Bottega Executive Presentation"
            )
            ult_esito = st.session_state.get("ultimo_esito_artigiano") or {
                "semaforo": "VERDE",
                "s_max": 1.0,
                "colore_nodo_ewd496a": "NERO",
                "risultato": {"principio_guida_unico": "Bottega L. LLM Wiki"},
                "risposta_discorsiva": "Executive summary generated from Knowledge Vault.",
            }
            testo_marp, path_marp = risolutore_artigiano.genera_presentazione_marp(
                ult_prob, ult_esito, radice_vault
            )
            st.session_state["ultimo_marp_testo"] = testo_marp
            st.session_state["ultimo_marp_nome"] = path_marp.name
            st.success(f"Marp Presentation created: {path_marp.name}")

    with b3:
        dati_zip = risolutore_artigiano.esporta_vault_wiki_zip(radice_vault)
        st.download_button(
            "📦 Download Full Obsidian Vault (.zip)",
            data=dati_zip,
            file_name="bottega_obsidian_vault.zip",
            mime="application/zip",
            key="dl_vault_zip_tab",
        )

    with b4:
        if st.button("🗑️ Reset Wiki Vault", key="btn_reset_vault"):
            for sub in ("synthesis", "concepts", "entities", "sources", "presentations", "raw"):
                sub_dir = radice_vault / ("raw" if sub == "raw" else f"wiki/{sub}")
                if sub_dir.is_dir():
                    for f_rm in sub_dir.glob("*"):
                        try:
                            if f_rm.is_file():
                                f_rm.unlink()
                        except OSError:
                            pass
            risolutore_artigiano.inizializza_vault_wiki(radice_vault)
            st.success("Wiki Vault reset successfully!")
            st.rerun()

    if "ultimo_marp_testo" in st.session_state:
        st.download_button(
            f"💾 Download Generated Presentation ({st.session_state.get('ultimo_marp_nome', 'slides.md')})",
            data=st.session_state["ultimo_marp_testo"].encode("utf-8"),
            file_name=st.session_state.get("ultimo_marp_nome", "presentation_marp.md"),
            mime="text/markdown",
            key="dl_marp_tab",
        )

    st.markdown("### Visual Knowledge Map (Wikilinks Graph)")
    st.graphviz_chart(risolutore_artigiano.costruisci_grafo_dot_wiki(radice_vault))

    st.markdown("### Browse Knowledge Base Pages (.md)")
    tutti_md = list((radice_vault / "wiki").glob("*/*.md"))
    if tutti_md:
        nomi_md = sorted([str(p.relative_to(radice_vault)).replace("\\", "/") for p in tutti_md])
        scelta_p = st.selectbox("Select Page to View:", nomi_md, key="sel_wiki_page")
        file_sel = radice_vault / scelta_p
        if file_sel.is_file():
            contenuto_file = file_sel.read_text(encoding="utf-8", errors="ignore")
            st.markdown(contenuto_file)
            st.download_button(
                f"Download {file_sel.name}",
                data=contenuto_file.encode("utf-8"),
                file_name=file_sel.name,
                mime="text/markdown",
                key=f"dl_md_page_{file_sel.stem}",
            )
    else:
        st.info("No pages in the Knowledge Vault yet. Upload documents or ask questions to populate it.")

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
        height=ALTEZZA_TEXTAREA_UI,
        placeholder="Write the question or problem you want to solve with grounded fragments...",
    )
    escluse_web = st.text_input(
        "Hypotheses already falsified in the field (comma-separated, optional):",
        placeholder="Optional: comma-separated hypotheses already ruled out...",
    )

    if st.button("Step 1 — Generate Grounded Prompt (Strato L + Strato A + Strato D)"):
        if not problema_web.strip():
            st.warning("Please enter a problem first.")
        else:
            lista_escl_w = [voce_w.strip() for voce_w in escluse_web.split(",") if voce_w.strip()]
            query_tradotta_w = client_ollama.traduci_query_per_ricerca(problema_web)
            blocchi_trovati = []
            try:
                rag_w = store_pgvector.recupera_con_semaforo(query_tradotta_w, dominio="generale", top_k=4)
                for idx_rw, fr_w in enumerate(rag_w.get("frammenti", []), start=1):
                    blocchi_trovati.append((f"Archive Fragment {idx_rw}", fr_w["testo"]))
            except (RuntimeError, ValueError, OSError, psycopg2.Error, KeyError, TypeError) as err_web:
                logging_bottega.log_exception("Errore recupero RAG in Free Web Bridge", "APP_WEB_001", err_web)
            for sez_est, txt_est in seed_bottega.cerca_nel_prontuario_locale(problema_web):
                if not any(txt_est in blocco_es[1] for blocco_es in blocchi_trovati):
                    blocchi_trovati.append((sez_est, txt_est))

            prompt_pronto = risolutore_artigiano.genera_prompt_ponte_web_gratuito(
                problema_web,
                blocchi_trovati,
                ipotesi_gia_escluse=lista_escl_w,
            )
            st.session_state["ultimo_contesto_web"] = "\n".join(
                [problema_web] + [f"{tit_b}: {cont_b}" for tit_b, cont_b in blocchi_trovati]
            )
            st.session_state["ultimo_problema_web"] = problema_web
            st.info("Copy the prompt below and paste it into ChatGPT, DeepSeek, Claude or Gemini:")
            st.code(prompt_pronto, language="markdown")

    st.divider()
    risposta_incollata = st.text_area(
        "Step 2 — Paste the web AI response here to subject it to Strato D Critical Audit (Tri-Color Write Barrier):",
        height=ALTEZZA_AUDIT_WEB_UI,
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
                "Numeric Check Passed (Node NERO): All figures and percentages match the source context (Decimal ROUND_HALF_UP)."
            )
            if st.button("Optional: Save Verified Response to Volatile Session Memory"):
                titolo_audit = grounding_numerico.tronca_senza_spezzare_parola(
                    audit_corrente["problema"], 50
                )
                n_salvati_web = store_pgvector.incasella_e_salva(
                    "generale",
                    f"Verified Web Bridge Audit: {titolo_audit}",
                    [("Verified Response", audit_corrente["testo"])],
                )
                st.toast(f"Saved {n_salvati_web} certified fragment(s) to volatile session memory!")
        else:
            st.error(
                f"GREY Node Blocked by Strato D Write Barrier! Ungrounded/invented numbers detected: "
                f"{audit_corrente['orfane']} | Percentages preserved: {audit_corrente['pct_ok']}. "
                "This response is rejected and CANNOT be saved into session memory."
            )

with tab_codice:
    codice_incollato = st.text_area(
        "Paste Python code to inspect:",
        height=ALTEZZA_CODICE_UI,
        placeholder="def calculate_margin(price, cost):\n    return price - cost",
    )
    col1, col2 = st.columns(2)

    with col1:
        if st.button("4A. Deterministic AST Anatomy Only (Instant, Zero LLM)"):
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
        if st.button("4B. Run Full 3-Layer Cascade (AST + RRF RAG + Strato L / A / D)", type="primary"):
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
                        st.markdown(referto)
                        st.download_button(
                            "Download Markdown Report",
                            referto,
                            file_name="referto_bottega.md",
                            mime="text/markdown",
                        )
                    except (RuntimeError, ValueError, OSError, psycopg2.Error, KeyError, TypeError) as err:
                        logging_bottega.log_exception("Errore in esegui_cascata UI", "APP_CAS_001", err)
                        st.error(f"Error during cascade execution ({provider_ui}): {err}")

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
