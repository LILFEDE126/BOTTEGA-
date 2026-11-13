# AGENTS.md — Bottega Leonardesca Agent Execution Protocol & Architecture Schema

This specification governs all AI coding agents (Antigravity, Pi, Claude Code, Codex, Cursor) operating on this repository. Every agent modifying or extending this codebase must adhere strictly to the invariants, acyclic layering, memory hierarchies, and verification gates documented below.

---

## 1. Architectural Foundations: The 5 Acyclic Rings (EWD196 Hierarchy)

The system is organized into strictly acyclic hierarchical rings following the foundational principles of E. W. D. (EWD196).
A module residing at Layer $L$ may **only** import modules from Layer $< L$. Reverse or peer imports across prohibited boundaries are strictly forbidden and enforced by AST inspection (`ispezione_moduli.py` and unit test `test_gerarchia_aciclica_the_ewd196_sui_file_reali`).

```
Layer 4: UI & Presentation
         └── app.py

Layer 3: Reasoning, Synthesis & Closed-Loop Resolution
         ├── risolutore_artigiano.py
         ├── cascata_strutturata.py
         └── seed_bottega.py

Layer 2: Persistence, Vector Store & Foundation Providers
         ├── store_pgvector.py
         └── client_ollama.py

Layer 1: Deterministic Geometry, Guardrails & AST Inspection
         ├── geometria_semaforo.py
         ├── grounding_numerico.py
         ├── presidio_concorrenza.py
         └── ispezione_moduli.py

Layer 0: Core Foundation, Configuration & Structured Logging
         ├── config.py
         ├── logging_bottega.py
         └── anatomia_ast.py
```

### Layer Rules
- **Layer 0 (`config`, `logging_bottega`, `anatomia_ast`):** Pure foundational constants, AST analysis utilities, and structured loggers. No external imports beyond Python standard library.
- **Layer 1 (`geometria_semaforo`, `grounding_numerico`, `presidio_concorrenza`, `ispezione_moduli`):** Deterministic mathematical functions (cosine similarity, reciprocal rank fusion, Decimal rounding, AST module hierarchy checks, concurrency locks). May only import from Layer 0.
- **Layer 2 (`store_pgvector`, `client_ollama`):** Vector storage adapters, in-memory RRF indexing, and LLM provider interfaces. May only import from Layers 0 and 1.
- **Layer 3 (`seed_bottega`, `cascata_strutturata`, `risolutore_artigiano`):** Three-tier cognitive solver (Strato L · Principle of Necessity, Strato A · Pragmatic Guardrails, Strato D · Weakest Preconditions $wp(S, R)$), Gen 3 LLM Wiki second brain graph engine, and Napkin-style visual DOT flowcharts. May only import from Layers 0, 1, and 2.
- **Layer 4 (`app`):** Accessible Streamlit web interface and Graphviz SVG rendering. May import from any lower layer (0..3).

---

## 2. Inviolable Code Invariants

All automated code modifications must preserve the following non-negotiable invariants:

1. **Zero `#` Comments in Production Code:**
   The 13 production source modules (`GERARCHIA_LIVELLI_THE`) must contain **zero** `#` comments (with the sole exception of `#!/usr/bin/env python3` on line 1). All explanations, contracts, and invariants must be written exclusively as PEP 257 docstrings. This is validated by token-level AST analysis (`tokenize.generate_tokens`).

2. **Zero `assert` Statements in Production Code:**
   Production modules must never use `assert` for validation or error handling. Use explicit exception raising (`ValueError`, `RuntimeError`, `psycopg2.Error`, etc.). `assert` is permitted strictly within `tests/test_bottega.py`.

3. **Zero Bare `except:` Clauses:**
   Every `try...except` block must catch explicit, named exception types (e.g., `except (RuntimeError, OSError) as err:`). Bare `except:` is rejected during linting.

4. **Zero Nested `st.expander` Components in `app.py`:**
   Streamlit prohibits nested expanders. All expander elements in `app.py` must reside at the top column or tab level.

5. **Exact Decimal Arithmetic:**
   All monetary amounts, VAT rates, subsidies, co-financing percentages, and financial thresholds must use `decimal.Decimal` with explicit `ROUND_HALF_UP` rounding. Floating-point arithmetic for financial sums or thresholds is strictly forbidden.

6. **Relational Write Barrier & Figure Grounding (Strato D):**
   No figure, percentage, or currency sum may be returned to the user unless it is directly grounded in retrieved document fragments or strictly derived via documented arithmetic operations ($A \times B$, $A + B\%$). The engine flags ungrounded hallucinations as Gray Nodes.

7. **Proper Name Anonymization:**
   To protect private identities and maintain rigorous confidentiality standards, all personal and geographic proper names across source code, docstrings, tests, and extracted documents must use initial-only abbreviations (`L.`, `A.`, `D.`, `K.`, `E. W. D.`, `R.`, `M.`, `V.`).

---

## 3. Memory Architecture: Gen 1, Gen 2 & Gen 3 (K. LLM Wiki Pattern)

The engine implements a hybrid 3-generation memory architecture:

- **Generation 1 (Dense Vector & Reciprocal Rank Fusion Retrieval):**
  - High-density chunking with anchored headers `[DOCUMENT | SECTION]`.
  - Reciprocal Rank Fusion (RRF) combining dense semantic cosine similarity with exact BM25 keyword matching.
  - Three-color guarded semaphore: `VERDE` ($s_{\max} \ge 0.65$), `AMBAR` ($0.45 \le s_{\max} < 0.65$), `ROJO` ($s_{\max} < 0.45$).

- **Generation 2 (Agentic Search Fallback on ROJO):**
  - When memory density is insufficient (`ROJO`), the engine executes an honest stop rather than hallucinating.
  - Cascading external search (Handbooks $\rightarrow$ Web Search $\rightarrow$ Encyclopedia) isolates exact missing parameters.

- **Generation 3 (Persistent Second Brain Knowledge Vault — K. Pattern):**
  - Located in `wiki_vault/` adhering to the open Obsidian-compatible file schema:
    - `raw/`: Unaltered ingested source documents and raw PDF texts.
    - `wiki/sources/`: Extracted markdown sources with metadata YAML frontmatter.
    - `wiki/concepts/`: Atomic synthesized conceptual notes with bidirectional `[[wikilinks]]`.
    - `wiki/entities/`: Domain entities, machinery specifications, tax categories.
    - `wiki/synthesis/`: Verified answers, diagnostic conclusions, and cross-source summaries.
    - `wiki/presentations/`: Auto-generated Marp slide presentations.
    - `index.md`: Central navigational index and live register of the entire vault.
    - `log.md`: Append-only audit log tracking all `INGEST`, `QUERY`, `LINT`, and `MARP` operations.

### Vault Operations Protocol
- `INGEST`: Ingests raw documents, normalizes ligatures/spaces, extracts code blocks, anonymizes personal names, and populates `sources/`.
- `QUERY`: Resolves queries with 1-hop graph traversals across `concepts/` and saves verified conclusions to `synthesis/`.
- `LINT`: Checks bidirectional link consistency, repairs orphan notes, and reconciles `index.md`.
- `MARP`: Generates presentation decks with YAML frontmatter `marp: true`.

---

## 4. Headless CLI Execution Mode (Pi / Codex Standard)

Any external coding agent, headless process, or automated test runner may invoke the engine via terminal without starting the Streamlit web server:

```bash
# Human-readable discursive response output
python risolutore_artigiano.py "What are the clean code rules?"

# Machine-readable structured JSON output
python risolutore_artigiano.py "How to configure VAT rate?" --json
```

The CLI entry point is defined in `risolutore_artigiano.py` and outputs either formatted text or full structured JSON diagnostics including semaphore, grounded citations, memory status, and Strato L · A · D audit details.

---

## 5. Visual Action Flowcharts (Napkin Style)

Under every verified answer, the engine renders a 4-step horizontal Graphviz flowchart (`costruisci_diagramma_flusso_risposta_dot`):
1. `1. Question / Case` (Soft Blue `#D0E8FF` / Border `#3B82F6`)
2. `2. Key Rule / Source` (Soft Green `#D4EDDA` / Border `#10B981`, or Soft Red `#FADBD8` / Border `#EF4444` if `ROJO`)
3. `3. What To Do (Action)` (Soft Amber `#FFE8B6` / Border `#F59E0B`)
4. `4. Final Verification` (Soft Purple `#E2D9F3` / Border `#8B5CF6`)

Text inside node labels is sanitized by stripping unescaped double quotes and backslashes, ensuring resilient SVG rendering via `st.graphviz_chart` with zero external NPM or SaaS dependencies.

---

## 6. Verification Gate: Mandatory Pre-Commit Protocol

Before committing any change to Git, the agent **must** run and pass both verification test batteries:

```bash
# 1. Pure Unit Test Battery (45 pure offline tests, zero network, zero DB)
python -m pytest -v

# 2. Domain B2B Benchmark (25 real high-density test cases)
python benchmarks/valuta_benchmark_verticale.py
```

### Acceptance Thresholds
- **Unit Tests:** 45/45 Passed (100%), 0 Failures, 0 AST comment violations.
- **B2B Benchmark:** 25/25 Passed (100%), Average latency $< 150\text{ ms}$, 0 relational barrier violations.
- **Vault Hygiene:** `wiki_vault/wiki/synthesis/` must remain clean after test runs.
