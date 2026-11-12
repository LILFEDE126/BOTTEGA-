#!/usr/bin/env python3
"""Layer 5 (THE): Complete suite of 43 pure unit tests (zero network, zero DB, zero LLM).
Includes AST check for zero '#' comments in source modules and multilingual EN/ES -> IT search tests."""

import ast
from decimal import Decimal
import io
import math
from pathlib import Path
import tokenize
from types import MappingProxyType
from pydantic import BaseModel
import pytest
import requests

import config
from config import GERARCHIA_LIVELLI_THE, EMBED_DIM
from anatomia_ast import analizza_codice_ast
from ispezione_moduli import verifica_gerarchia_the
from geometria_semaforo import (
    costruisci_testo_ancorato,
    fondi_rrf,
    normalizza_l2,
    similitudine_coseno,
    valuta_semaforo,
)
from grounding_numerico import (
    arrotonda_esatto_el_x8,
    classifica_nodo_tricolore,
    ripara_parola_troncata,
    suddividi_in_pagine_con_continua,
    tronca_senza_spezzare_parola,
    verifica_conservazione_percentuali_decimal,
    verifica_grounding_numerico,
)
from presidio_concorrenza import PresidioConcorrenzaTHE, verifica_stato_sicuro_banchiere
import client_ollama
import store_pgvector
import seed_bottega
import risolutore_artigiano


class _SchemaTest(BaseModel):
    esito: str
    valore: int


def _trova_radice_progetto() -> Path:
    corrente = Path(__file__).resolve().parent
    if (corrente / "config.py").is_file():
        return corrente
    if (corrente.parent / "config.py").is_file():
        return corrente.parent
    raise FileNotFoundError("Impossibile trovare config.py nella directory corrente o superiore.")


def test_anatomia_ast_rileva_metodi_classe_except_e_cicli_annidati():
    codice = "\n".join([
        "contatore = 0",
        "class Gestore:",
        "    def elabora(self, items):",
        "        global contatore",
        "        while True:",
        "            for x in items:",
        "                break",
        "            contatore += 1",
        "        try:",
        "            return calcola(items)",
        "        except:",
        "            return None",
    ])
    res = analizza_codice_ast(codice)
    assert res["numero_funzioni"] == 1
    assert res["funzioni"][0]["nome"] == "Gestore.elabora"
    assert res["totale_except_nudi"] == 1
    assert res["cicli_senza_variante"] == 1
    assert res["usi_global_mutabili"] == 1
    assert '"Gestore.elabora" -> "calcola";' in res["dot_graph"]


def test_gerarchia_aciclica_the_ewd196_sui_file_reali():
    radice = _trova_radice_progetto()
    for nome_modulo in GERARCHIA_LIVELLI_THE:
        percorso = radice / f"{nome_modulo}.py"
        assert percorso.is_file(), f"Modulo architetturale mancante: {percorso.name}"
        codice = percorso.read_text(encoding="utf-8")
        assert verifica_gerarchia_the(nome_modulo, codice=codice) == []

    violazioni = verifica_gerarchia_the("config", codice="import app\n")
    assert len(violazioni) == 1
    assert "Violazione THE" in violazioni[0]


def test_zero_commenti_cancelletto_nei_moduli_sorgente():
    radice = _trova_radice_progetto()
    for nome_modulo in GERARCHIA_LIVELLI_THE:
        percorso = radice / f"{nome_modulo}.py"
        testo = percorso.read_text(encoding="utf-8")
        tokens = tokenize.generate_tokens(io.StringIO(testo).readline)
        commenti_trovati = [
            (tok.start[0], tok.string)
            for tok in tokens
            if tok.type == tokenize.COMMENT and not tok.string.startswith("#!")
        ]
        assert commenti_trovati == [], (
            f"Trovati commenti '#' in {percorso.name}: {commenti_trovati}"
        )


def test_traduzione_query_multilingua_en_es_it():
    assert client_ollama.rileva_lingua_testo("How to fix boiler pressure drop when cold?") == "en"
    assert client_ollama.rileva_lingua_testo("¿Qué arancel aplica a la caldera con pérdida de presión?") == "es"
    assert client_ollama.rileva_lingua_testo("Perdita di pressione della caldaia a freddo") == "it"

    q_en = client_ollama.traduci_query_per_ricerca("boiler pressure drop 0.4 bar")
    assert "caldaia" in q_en
    assert "pressione" in q_en
    assert "perdita" in q_en

    ris_en = seed_bottega.cerca_nel_prontuario_esterno("boiler pressure drop when cold")
    assert any("Schrader" in testo for _, testo in ris_en)

    ris_es = seed_bottega.cerca_nel_prontuario_esterno("arancel antidumping aluminio 7604210000")
    assert any("32,10%" in testo for _, testo in ris_es)


def test_algoritmo_del_banchiere_ewd116_stato_sicuro_e_insicuro():
    assert verifica_stato_sicuro_banchiere(10, [3, 2, 2], [6, 4, 7]) is True
    assert verifica_stato_sicuro_banchiere(10, [3, 3, 3], [6, 6, 6]) is False


def test_segretario_the_holyness_counter_ewd113_e_banchiere():
    segretario = PresidioConcorrenzaTHE(capitale_slot=2)
    assert segretario.holyness_di("generale") == 0
    assert segretario.puo_essere_vittima("generale") is True

    with segretario.sezione_sacra("generale", fabbisogno_massimo=2):
        assert segretario.holyness_di("generale") == 1
        assert segretario.puo_essere_vittima("generale") is False

    assert segretario.holyness_di("generale") == 0
    assert segretario.puo_essere_vittima("generale") is True

    with pytest.raises(RuntimeError, match="Violazione EWD116"):
        with segretario.sezione_sacra("generale", fabbisogno_massimo=5):
            pass
    assert segretario.holyness_di("generale") == 0


def test_arrotondamento_esatto_el_x8_ewd145_e_conservazione_percentuali():
    assert arrotonda_esatto_el_x8("12.345", 2) == Decimal("12.35")
    assert arrotonda_esatto_el_x8("-12.345", 2) == Decimal("-12.35")
    assert verifica_conservazione_percentuali_decimal(
        "Il dazio applicabile e' del 2,7 %.", "Derecho terceros paises: 2.70%"
    ) is True
    assert verifica_conservazione_percentuali_decimal(
        "Il dazio applicabile e' del 2,8 %.", "Derecho terceros paises: 2.70%"
    ) is False


def test_marcatura_tricolore_ewd496a_e_zeri_finali_percentuali():
    ctx = "Codice TARIC 7604210000 con antidumping 32,10 % dal 2021."
    assert classifica_nodo_tricolore("", ctx) == ("BIANCO", [])

    colore, orfane = classifica_nodo_tricolore(
        "Il codice 7604210000 ha antidumping 32,1% dal 2021.", ctx
    )
    assert colore == "NERO"
    assert orfane == []

    colore, orfane = classifica_nodo_tricolore(
        "Il codice 7604210000 ha antidumping 15,00 % dal 2024.", ctx
    )
    assert colore == "GRIGIO"
    assert "15.00%" in orfane
    assert "2024" in orfane


def test_write_barrier_blocca_decimali_tecnici_allucinati():
    ctx = "Pressione a freddo 0.3 bar, precarica vaso di espansione 1.0 bar."
    colore_ok, orfane_ok = classifica_nodo_tricolore(
        "La pressione e' 0,3 bar e la precarica va portata a 1,00 bar.", ctx
    )
    assert colore_ok == "NERO"
    assert orfane_ok == []

    colore_ko, orfane_ko = classifica_nodo_tricolore(
        "Ripristinare precarica a 2.5 bar.", ctx
    )
    assert colore_ko == "GRIGIO"
    assert "2.5" in orfane_ko


def test_paradosso_migliaia_14400_vs_decimale_14_4():
    ctx = "Fattura doganale di importo pari a 14.400 EUR."
    assert verifica_grounding_numerico("Importo confermato di 14.400 EUR.", ctx) == []

    colore, orfane = classifica_nodo_tricolore("Importo ridotto a 14,4 EUR.", ctx)
    assert colore == "GRIGIO"
    assert "14.4" in orfane


def test_normalizzazione_l2_e_controllo_dimensioni_coseno():
    v = [3.0, 4.0]
    vn = normalizza_l2(v)
    assert math.isclose(vn[0], 0.6, rel_tol=1e-9)
    assert math.isclose(vn[1], 0.8, rel_tol=1e-9)
    assert math.isclose(similitudine_coseno(vn, vn), 1.0, rel_tol=1e-9)

    with pytest.raises(ValueError):
        normalizza_l2([0.0, 0.0, 0.0])
    with pytest.raises(ValueError, match="incompatibili"):
        similitudine_coseno([1.0, 0.0], [1.0, 0.0, 0.0])


def test_costruisci_testo_ancorato():
    testo = costruisci_testo_ancorato(
        "generale", "Metodo Empirico", "Osservazione", "Misurare l'AST prima di giudicare."
    )
    assert testo.startswith("[GENERALE] Metodo Empirico > Osservazione\n\n")
    assert testo.endswith("Misurare l'AST prima di giudicare.")


def test_fusione_pura_rrf_peso_simple_batte_vettoriale():
    vett = [{"id": 1, "testo": "Vettoriale", "similitudine": 0.85}]
    simple = [{"id": 2, "testo": "Codice esatto", "similitudine": 0.65}]
    fusi = fondi_rrf(vett, [], simple, top_k=2)
    assert fusi[0]["id"] == 2
    assert fusi[0]["rrf"] > fusi[1]["rrf"]


def test_valuta_semaforo_guarded_commands_ewd472():
    assert valuta_semaforo([], s_dominio=0.8) == ("ROJO", 0.0)
    assert valuta_semaforo([{"similitudine": 0.70}], s_dominio=0.15, ha_match_lessicale=False)[0] == "ROJO"
    assert valuta_semaforo(
        [{"similitudine": 0.68}, {"similitudine": 0.52}], s_dominio=0.50, ha_match_lessicale=False
    ) == ("VERDE", 0.68)
    assert valuta_semaforo(
        [{"similitudine": 0.50}], s_dominio=0.40, ha_match_lessicale=False
    ) == ("AMBAR", 0.50)


def test_verifica_grounding_numerico_quattro_categorie_jiso():
    contesto = (
        "Codice TARIC 7604210000: dazio ordinario 7.50%, antidumping 32,10 % dal 2021, "
        "export pari a 20.528.272,00 EUR nel 2026."
    )
    risposta_corretta = (
        "Per il codice 7604210000 il dazio e' 7,5 % e l'antidumping 32.10% dal 2021 "
        "(export 20.528.272,00 EUR nel 2026)."
    )
    assert verifica_grounding_numerico(risposta_corretta, contesto) == []


def test_client_ollama_autostabilizzazione_ewd426_e_variante_t_ewd316(monkeypatch):
    risposte = [
        '{"esito": "ok", "valore": "NON_UN_INTERO"}',
        '{"esito": "riparato", "valore": 42}',
    ]

    class _FakeResp:
        def __init__(self, testo: str):
            self._testo = testo

        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": self._testo}}

    monkeypatch.setattr(
        client_ollama.requests,
        "post",
        lambda url, json, timeout: _FakeResp(risposte.pop(0)),
    )
    ris = client_ollama.chiama_ollama_json("sys", "usr", _SchemaTest, max_passi_variante=2, provider="ollama")
    assert ris.esito == "riparato"
    assert ris.valore == 42

    monkeypatch.setattr(
        client_ollama.requests,
        "post",
        lambda url, json, timeout: _FakeResp('{"json_rotto": '),
    )
    with pytest.raises(RuntimeError, match="variante t=0"):
        client_ollama.chiama_ollama_json("sys", "usr", _SchemaTest, max_passi_variante=2, provider="ollama")


def test_client_cloud_free_gemini_groq_openrouter_compatibilita(monkeypatch):
    chiamate = []

    class _FakeCloudResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "```json\n{\"esito\": \"cloud_ok\", \"valore\": 7}\n```"}}]}

    def finto_post(url, headers=None, json=None, timeout=120):
        chiamate.append((url, headers, json))
        return _FakeCloudResp()

    monkeypatch.setattr(client_ollama.requests, "post", finto_post)
    fn_gemini = client_ollama.costruisci_llm_fn(provider="gemini", api_key="test_key_free")
    ris = fn_gemini("sys", "usr", _SchemaTest)
    assert ris.esito == "cloud_ok"
    assert ris.valore == 7
    assert "generativelanguage.googleapis.com" in chiamate[0][0]
    assert chiamate[0][1]["Authorization"] == "Bearer test_key_free"


def test_client_cloud_retry_su_http_429_rate_limit(monkeypatch):
    tentativi = {"n": 0}
    monkeypatch.setattr(client_ollama.time, "sleep", lambda s: None)

    class _Resp429:
        status_code = 429

        def raise_for_status(self):
            err = requests.exceptions.HTTPError("429 Too Many Requests")
            err.response = self
            raise err

    class _Resp200:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": '{"esito": "dopo_429", "valore": 99}'}}]}

    def finto_post(url, headers=None, json=None, timeout=120):
        tentativi["n"] += 1
        if tentativi["n"] == 1:
            return _Resp429()
        return _Resp200()

    monkeypatch.setattr(client_ollama.requests, "post", finto_post)
    ris = client_ollama.chiama_ollama_json(
        "sys", "usr", _SchemaTest, max_passi_variante=2, provider="groq", api_key="k"
    )
    assert tentativi["n"] == 2
    assert ris.esito == "dopo_429"
    assert ris.valore == 99


def test_calcola_embedding_fallback_lessicale_senza_ollama(monkeypatch):
    def finto_post_spento(url, json=None, timeout=10):
        raise requests.exceptions.ConnectionError("Ollama spento")

    monkeypatch.setattr(store_pgvector.requests, "post", finto_post_spento)
    vettori = store_pgvector.calcola_embedding(["Contratto di fornitura idraulica 2026"])
    assert len(vettori) == 1
    assert len(vettori[0]) == EMBED_DIM
    assert math.isclose(similitudine_coseno(vettori[0], vettori[0]), 1.0, rel_tol=1e-6)


def test_cerca_nel_prontuario_esterno_chiama_api_wikipedia_su_tema_nuovo(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setattr(config, "LLM_API_KEY", "")

    class _FakeResp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    def finto_get(url, params=None, headers=None, timeout=10):
        if "duckduckgo" in url:
            return _FakeResp({"AbstractText": ""})
        return _FakeResp({
            "query": {
                "search": [
                    {
                        "title": "Colpo d'ariete",
                        "snippet": 'Fenomeno idraulico di <span class="searchmatch">sovrappressione</span> nella pompa centrifuga.',
                    }
                ]
            }
        })

    monkeypatch.setattr(seed_bottega.requests, "get", finto_get)
    ris = seed_bottega.cerca_nel_prontuario_esterno("cavitazione girante pompa centrifuga")
    assert len(ris) == 1
    assert ris[0][0] == "API Wikipedia: Colpo d'ariete"
    assert "<span" not in ris[0][1]
    assert "sovrappressione" in ris[0][1]


def test_cascata_opzione_b_web_search_ai_verso_opzione_a(monkeypatch):
    class _FakeGeminiSearchResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "Normativa UNI 9182 portata minima 0.5 l/s."}]
                        }
                    }
                ]
            }

    monkeypatch.setattr(
        seed_bottega.requests,
        "post",
        lambda url, json=None, headers=None, timeout=15: _FakeGeminiSearchResp(),
    )
    ris_b = seed_bottega.cerca_nel_prontuario_esterno(
        "normativa uni 9182 portata", provider="gemini", api_key="key_test"
    )
    assert len(ris_b) == 1
    assert "Gemini Grounding" in ris_b[0][0]
    assert "0.5 l/s" in ris_b[0][1]

    def finto_post_fallito(url, json=None, headers=None, timeout=15):
        raise requests.exceptions.ConnectionError("Gemini non raggiungibile")

    class _FakeDdgResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"Heading": "UNI 9182", "AbstractText": "Impianti di alimentazione acqua 0.5 l/s."}

    monkeypatch.setattr(seed_bottega.requests, "post", finto_post_fallito)
    monkeypatch.setattr(
        seed_bottega.requests,
        "get",
        lambda url, params=None, headers=None, timeout=10: _FakeDdgResp(),
    )
    ris_fallback = seed_bottega.cerca_nel_prontuario_esterno(
        "normativa uni 9182 portata", provider="gemini", api_key="key_test"
    )
    assert len(ris_fallback) == 1
    assert "API DuckDuckGo: UNI 9182" in ris_fallback[0][0]


def test_connessione_db_chiude_sempre_conn_anche_su_eccezione(monkeypatch):
    stato = {"chiusa": False, "rollback": False}

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is not None:
                stato["rollback"] = True
            return False

        def close(self):
            stato["chiusa"] = True

    monkeypatch.setattr(store_pgvector.psycopg2, "connect", lambda **kw: _FakeConn())

    with pytest.raises(ValueError, match="errore simulato"):
        with store_pgvector.connessione_db(registra_vettore=False):
            raise ValueError("errore simulato")

    assert stato["rollback"] is True
    assert stato["chiusa"] is True, "Connessione non chiusa nel blocco finally!"


def test_config_prod_rifiuta_password_di_default(monkeypatch):
    monkeypatch.setattr(config, "BOTTEGA_ENV", "prod")
    monkeypatch.setenv("DB_PASSWORD", "bottega2026")
    with pytest.raises(RuntimeError, match="BOTTEGA_ENV=prod"):
        config.get_db_config()


def test_risolutore_artigiano_stop_onesto_su_semaforo_rojo(monkeypatch):
    monkeypatch.setattr(
        risolutore_artigiano,
        "recupera_con_semaforo",
        lambda q, dominio="generale", top_k=3: {"semaforo": "ROJO", "s_max": 0.12, "frammenti": []},
    )
    esito = risolutore_artigiano.risolvi_da_artigiano(
        "La caldaia segna E04 e pressione 0.3 bar",
        llm_fn=lambda sys_p, usr_p, schema: risolutore_artigiano.PianoRicercaArtigiano(
            fatti_accertati_nel_problema=["Caldaia in blocco E04", "Pressione 0.3 bar"],
            dato_esatto_mancante="Schema idraulico valvola di carico",
            query_chirurgica_esterna="manuale tecnico errore E04 pressione 0.3 bar",
            ispezione_preliminare_sul_campo="Controllare manometro e perdite collettore",
        ),
    )
    assert esito["semaforo"] == "ROJO"
    assert esito["modalita"] == "RICERCA_PRIMA_DI_AGIRE"
    assert esito["ricerca_esterna_eseguita"] is False
    assert esito["colore_nodo_ewd496a"] == "GRIGIO"


def test_risolutore_artigiano_ciclo_chiuso_cerca_fuori_e_risolve_senza_mucchio(monkeypatch):
    stato_chiamate = {"n": 0}

    def finto_recupera(q, dominio="generale", top_k=3):
        stato_chiamate["n"] += 1
        if stato_chiamate["n"] == 1:
            return {"semaforo": "ROJO", "s_max": 0.10, "frammenti": []}
        return {
            "semaforo": "VERDE",
            "s_max": 0.78,
            "frammenti": [
                {"id": 1, "testo": "Se la pressione scende a 0.3 bar a freddo, vaso espansione scarico (precarica 1.0 bar)."},
                {"id": 2, "testo": "Rumore ventilatore fumi: verificare cuscinetti estrattore."},
            ],
        }

    monkeypatch.setattr(risolutore_artigiano, "recupera_con_semaforo", finto_recupera)
    monkeypatch.setattr(risolutore_artigiano, "incasella_e_salva", lambda dom, tit, blocchi: len(blocchi))

    def finto_llm(sys_p, usr_p, schema):
        if schema is risolutore_artigiano.PianoRicercaArtigiano:
            return risolutore_artigiano.PianoRicercaArtigiano(
                fatti_accertati_nel_problema=["Pressione 0.3 bar a freddo"],
                dato_esatto_mancante="Procedura verifica precarica vaso di espansione",
                query_chirurgica_esterna="perdita pressione 0.3 bar vaso espansione",
                ispezione_preliminare_sul_campo="Misurare pressione valvola Schrader del vaso",
            )
        return risolutore_artigiano.SoluzioneArtigiano(
            principio_guida_unico="[Frammento 1] Precarica vaso espansione 1.0 bar",
            elementi_scartati_per_non_fare_mucchio=["[Frammento 2] Cuscinetti ventilatore fumi (non pertinente alla pressione)"],
            precondizione_wp_richiesta="Circuito idraulico isolato e scarico da pressione residua",
            invariante_violato="Conservazione pressione statica nel circuito chiuso (scesa a 0.3 bar)",
            ipotesi_causale_unica="Membrana vaso di espansione scarica sotto 1.0 bar",
            azione_correttiva_singola="Ripristinare precarica aria vaso a 1.0 bar e ricaricare circuito",
            esperimento_di_verifica_pratica="Verificare tenuta stabile dopo 2 cicli termici",
        )

    esito = risolutore_artigiano.risolvi_da_artigiano(
        "Caldaia a 0.3 bar a freddo",
        cercatore_esterno_fn=lambda query: [("Vaso espansione", "Precarica nominale 1.0 bar")],
        llm_fn=finto_llm,
    )
    assert esito["semaforo"] == "VERDE"
    assert esito["modalita"] == "AZIONE_SINGOLA_VERIFICABILE"
    assert esito["ricerca_esterna_eseguita"] is True
    assert esito["colore_nodo_ewd496a"] == "NERO"
    assert len(esito["risultato"]["elementi_scartati_per_non_fare_mucchio"]) == 1


def test_risolutore_artigiano_falsificazione_sul_campo_e_prompt_ponte_web(monkeypatch):
    monkeypatch.setattr(
        risolutore_artigiano,
        "recupera_con_semaforo",
        lambda q, dominio="generale", top_k=3: {
            "semaforo": "VERDE",
            "s_max": 0.82,
            "frammenti": [
                {
                    "id": 1,
                    "testo": "Perdita 0.4 bar: Ipotesi 1 vaso espansione (1.0 bar); Ipotesi 2 perdita collettore sotto pavimento.",
                }
            ],
        },
    )

    prompt_catturato = {"usr": ""}

    def finto_llm_secondo_giro(sys_p, usr_p, schema):
        prompt_catturato["usr"] = usr_p
        return risolutore_artigiano.SoluzioneArtigiano(
            principio_guida_unico="[Frammento 1] Isolamento binario caldaia vs collettore",
            elementi_scartati_per_non_fare_mucchio=[],
            precondizione_wp_richiesta="Valvole di mandata e ritorno sotto caldaia chiuse per 1 ora",
            invariante_violato="Perdita di 0.4 bar localizzata nel ramo esterno all'apparecchio",
            ipotesi_causale_unica="Perdita occulta nel collettore dell'impianto sotto pavimento",
            azione_correttiva_singola="Sezionare i singoli anelli del collettore e mettere in prova a 2.5 bar",
            esperimento_di_verifica_pratica="Individuare l'anello che cede pressione di 0.4 bar in 1 ora",
        )

    esito = risolutore_artigiano.risolvi_da_artigiano(
        "L'impianto perde 0.4 bar ogni ora ma a valvole chiuse la caldaia resta a 1.0 bar",
        ipotesi_gia_escluse=["Vaso di espansione scarico"],
        llm_fn=finto_llm_secondo_giro,
    )
    assert "IPOTESI GIA' FALSIFICATE SUL CAMPO" in prompt_catturato["usr"]
    assert any(
        "Vaso di espansione scarico" in s
        for s in esito["risultato"]["elementi_scartati_per_non_fare_mucchio"]
    )

    prompt_web = risolutore_artigiano.genera_prompt_ponte_web_gratuito(
        "Perdita 0.4 bar",
        [("Idraulica", "Verifica vaso a 1.0 bar")],
        ipotesi_gia_escluse=["Valvola radiatore"],
    )
    assert "NON FARE MUCCHIO" in prompt_web
    assert "Valvola radiatore" in prompt_web


def test_estrazione_pdf_e_archivio_ram_senza_postgres(monkeypatch):
    class _FakePage:
        def extract_text(self):
            return (
                "Bando voucher digitali I4.0 Anno 2022 dotazione 1.150.000,00 EUR "
                "agevolazione 50% fino a 10.000,00 EUR oltre premialita 250,00 EUR."
            )

    class _FakePdfReader:
        def __init__(self, stream):
            self.pages = [_FakePage()]

    monkeypatch.setattr(store_pgvector, "PdfReader", _FakePdfReader)
    monkeypatch.setattr(
        store_pgvector.requests,
        "post",
        lambda url, json=None, timeout=10: (_ for _ in ()).throw(
            requests.exceptions.ConnectionError("Ollama spento")
        ),
    )
    monkeypatch.setattr(
        store_pgvector.psycopg2,
        "connect",
        lambda **kw: (_ for _ in ()).throw(
            store_pgvector.psycopg2.OperationalError("Postgres non attivo su Streamlit Cloud")
        ),
    )

    store_pgvector._ARCHIVIO_MEMORIA_RAM.clear()
    blocchi = store_pgvector.estrai_blocchi_documento("Consegna_Too_Fast_17.pdf", b"%PDF-1.7 fake")
    assert len(blocchi) == 1
    assert blocchi[0][0] == "Page 1"
    assert "1.150.000,00" in blocchi[0][1]

    n_salvati = store_pgvector.incasella_e_salva("tecnico", "Consegna_Too_Fast_17.pdf", blocchi)
    assert n_salvati == 1

    rag_res = store_pgvector.recupera_con_semaforo(
        "voucher digitali 1.150.000,00 agevolazione 50%",
        dominio="tecnico",
        top_k=3,
    )
    assert rag_res["semaforo"] in ("VERDE", "AMBAR")
    assert len(rag_res["frammenti"]) == 1
    assert "10.000,00" in rag_res["frammenti"][0]["testo"]
    store_pgvector._ARCHIVIO_MEMORIA_RAM.clear()


def test_rotazione_modelli_gemini_su_404_503_e_fallback_deterministico_artigiano(monkeypatch):
    monkeypatch.setattr(client_ollama.time, "sleep", lambda s: None)
    modelli_tentati = []

    class _Resp404:
        status_code = 404

        def raise_for_status(self):
            err = requests.exceptions.HTTPError("404 Model Not Available")
            err.response = self
            raise err

    class _Resp200:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": '{"esito": "rotazione_ok", "valore": 1}'}}]}

    def finto_post_rotazione(url, headers=None, json=None, timeout=120):
        modelli_tentati.append(json["model"])
        if len(modelli_tentati) == 1:
            return _Resp404()
        return _Resp200()

    monkeypatch.setattr(client_ollama.requests, "post", finto_post_rotazione)
    ris = client_ollama.chiama_ollama_json(
        "sys",
        "usr",
        _SchemaTest,
        max_passi_variante=3,
        provider="gemini",
        api_key="AQ.test",
        model="gemini-2.5-flash",
    )
    assert ris.esito == "rotazione_ok"
    assert modelli_tentati[0] == "gemini-2.5-flash"
    assert modelli_tentati[1] == "gemini-2.5-flash-lite"

    monkeypatch.setattr(
        risolutore_artigiano,
        "recupera_con_semaforo",
        lambda q, dominio="tecnico", top_k=5: {
            "semaforo": "VERDE",
            "s_max": 0.85,
            "frammenti": [
                {
                    "id": 1,
                    "testo": "Il sito web da 10.000-15.000 euro rientra nel Bando Voucher I4.0 al 50%, escluse brochure da 1.500 euro.",
                }
            ],
        },
    )

    def llm_spento(sys_p, usr_p, schema):
        raise RuntimeError("API momentaneamente irraggiungibile")

    esito_fb = risolutore_artigiano.risolvi_da_artigiano(
        "I costi per il sito web (10.000-15.000 euro) e brochure (1.500 euro) sono coperti?",
        dominio="tecnico",
        llm_fn=llm_spento,
    )
    assert esito_fb["semaforo"] == "VERDE"
    assert esito_fb["colore_nodo_ewd496a"] == "NERO"
    assert "50%" in esito_fb["risultato"]["principio_guida_unico"]


def test_logging_bottega_queue_handler_sette_chiavi_json_e_assenza_log_file():
    import json
    import logging
    import logging.handlers
    import time
    import logging_bottega

    assert not hasattr(logging_bottega, "LOG_FILE")
    assert not hasattr(logging_bottega, "resolver_log_file")

    logger = logging_bottega.configura_logger("test_coda_cap_7_3")
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], logging.handlers.QueueHandler)

    assert "__init__" not in logging_bottega.FormatterJSON.__dict__
    assert "converter" not in logging_bottega.FormatterJSON.__dict__

    assert logging_bottega.resolver_log_format("  JSON \n") == "json"
    assert logging_bottega.resolver_log_format("xml_invalido") == "text"
    assert logging_bottega.resolver_log_format(None) in ("text", "json")

    fmt = logging_bottega.FormatterJSON()
    record = logging.LogRecord(
        name="bottega",
        level=logging.INFO,
        pathname="store_pgvector.py",
        lineno=42,
        msg="Tariffa doganale più 4,50% verificata",
        args=(),
        exc_info=None,
    )
    record.code = "RAG_RET_001"
    record.s_max = Decimal("0.8223")
    record.dominio = "tecnico"

    riga_json = fmt.format(record)
    assert fmt.converter is time.gmtime
    assert "più" in riga_json

    dati = json.loads(riga_json)
    assert list(dati.keys())[:7] == [
        "ts",
        "level",
        "code",
        "logger",
        "process",
        "thread",
        "msg",
    ]
    assert dati["code"] == "RAG_RET_001"
    assert dati["s_max"] == "0.8223"
    assert dati["dominio"] == "tecnico"

    listener = getattr(logger, "_queue_listener", None)
    if listener is not None:
        listener.stop()


def test_nodo_nero_ewd496a_con_frammenti_scartati_risposta_monolingua_en_es_e_30_documenti(monkeypatch):
    assert config.MAX_DOCUMENTI_PER_RICHIESTA == 30
    assert config.MAX_MB_PER_RICHIESTA == 200
    assert config.MAX_BYTES_PER_RICHIESTA == 200 * 1024 * 1024

    q_en = (
        "According to the business project, what is the retail price of the shirt and shorts kit "
        "(maglia e pantaloncino), what is the unit margin in euros, and what is the maximum delivery lead time in months?"
    )
    q_es = (
        "¿Cuál es el presupuesto estimado en euros para el desarrollo del sitio web (sito web) "
        "y para los folletos (brochure) en el plan de inversiones de Too Fast?"
    )
    assert client_ollama.rileva_lingua_testo(q_en) == "en"
    assert client_ollama.rileva_lingua_testo(q_es) == "es"

    monkeypatch.setattr(
        risolutore_artigiano,
        "recupera_con_semaforo",
        lambda q, dominio="generale", top_k=5: {
            "semaforo": "VERDE",
            "s_max": 0.95,
            "frammenti": [
                {
                    "id": 1,
                    "testo": "1.9a Modello di Business: prezzo imposto 40 euro, margine tra 15 e 20 euro, consegna 3 mesi.",
                },
                {
                    "id": 2,
                    "testo": "Bando Voucher digitali I4.0: contributo 50% fino a 10.000,00 euro, consulenza 10%.",
                },
            ],
        },
    )

    def finto_llm_en(sys_p, usr_p, schema):
        assert "100% ENGLISH ONLY" in sys_p
        return risolutore_artigiano.SoluzioneArtigiano(
            risposta_finale_discorsiva=(
                "The retail price for the shirt and shorts kit is 40 euro, with a unit margin between 15 and 20 euro "
                "and a maximum delivery lead time of 3 months."
            ),
            principio_guida_unico="Business Model section 1.9a: retail price 40 euro, margin 15 to 20 euro, lead time 3 months.",
            elementi_scartati_per_non_fare_mucchio=["Digital Voucher Grant I4.0: 50% up to 10.000,00 euro"],
            precondizione_wp_richiesta="wp(S, R) requires extracting 40 euro, 15-20 euro, and 3 months from section 1.9a.",
            invariante_violato="Alignment between retail price and unit contribution margin.",
            ipotesi_causale_unica="The unit margin of 15 to 20 euro is calculated on the 40 euro retail price.",
            azione_correttiva_singola="Extract the verified values 40 euro, 15 to 20 euro, and 3 months.",
            esperimento_di_verifica_pratica="Verify that 40 euro, 15-20 euro, and 3 months match section 1.9a.",
        )

    esito_en = risolutore_artigiano.risolvi_da_artigiano(
        q_en,
        dominio="generale",
        ipotesi_gia_escluse=["Foreign supplier delay"],
        llm_fn=finto_llm_en,
    )
    assert esito_en["lingua"] == "en"
    assert esito_en["colore_nodo_ewd496a"] == "NERO"
    assert esito_en["percentuali_conservate"] is True
    assert "**1. Main Answer & Root Diagnosis:**" in esito_en["risposta_discorsiva"]
    assert "**6. Excluded Items or Hypotheses (Anti-Clutter Filter):**" in esito_en["risposta_discorsiva"]
    assert "[Falsified in the field] Foreign supplier delay" in esito_en["risposta_discorsiva"]
    assert "Risposta e Diagnosi Principale" not in esito_en["risposta_discorsiva"]

    def finto_llm_es(sys_p, usr_p, schema):
        assert "100% ESPAÑOL ÚNICAMENTE" in sys_p
        return risolutore_artigiano.SoluzioneArtigiano(
            risposta_finale_discorsiva=(
                "El Bando Voucher digitali I4.0 cubre el 50% hasta 10.000,00 euro, mientras que el precio es 40 euro."
            ),
            principio_guida_unico="Bando Voucher digitali I4.0 (Reggio Emilia)",
            elementi_scartati_per_non_fare_mucchio=["Modelo de negocio 1.9a: 40 euro"],
            precondizione_wp_richiesta="wp(S, R) exige separar costos digitales (50%) de folletos impresos.",
            invariante_violato="Elegibilidad de gastos digitales frente a tipografía.",
            ipotesi_causale_unica="El subsidio del 50% aplica únicamente a la plataforma web hasta 10.000,00 euro.",
            azione_correttiva_singola="Aplicar el 50% hasta 10.000,00 euro.",
            esperimento_di_verifica_pratica="Comprobar el límite de 10.000,00 euro y el 50%.",
        )

    esito_es = risolutore_artigiano.risolvi_da_artigiano(
        q_es,
        dominio="generale",
        ipotesi_gia_escluse=["Bando Invitalia descartado"],
        llm_fn=finto_llm_es,
    )
    assert esito_es["lingua"] == "es"
    assert esito_es["colore_nodo_ewd496a"] == "NERO"
    assert "**1. Respuesta y Diagnóstico Principal:**" in esito_es["risposta_discorsiva"]
    assert "**6. Elementos o Hipótesis Excluidas (para no mezclar soluciones):**" in esito_es["risposta_discorsiva"]
    assert "[Falsificada en el campo] Bando Invitalia descartado" in esito_es["risposta_discorsiva"]
    assert "Risposta e Diagnosi Principale" not in esito_es["risposta_discorsiva"]


def test_normalizzazione_spazi_pdf_incollati_e_barriera_numerica_su_contesto_reale(monkeypatch):
    testo_incollato = (
        "Siimmaginaunbudgetstimatotrai10-15.000euro(preventivodarealizzare) "
        "Adoggi,ilprezzoimpostoalmercatosumagliapiùpantaloncinoèdi40euro,conun "
        "marginecheoscillatrai15ei20euroapezzo. 1.9a ModellodiBusiness "
        "50%deicostisostenutiedentroillimitemassimodi40.000€perlemicroepiccoleimprese "
        "BandoVoucherdigitaliI4.0eErroreE04"
    )
    normalizzato = store_pgvector.normalizza_spazi_testo_pdf(testo_incollato)
    assert "trai 10-15.000 euro (preventivodarealizzare)" in normalizzato
    assert "di 40 euro, conun" in normalizzato
    assert "trai 15 ei 20 euro apezzo" in normalizzato
    assert "50% deicostisostenutiedentroillimitemassimodi 40.000 € perlemicroepiccoleimprese" in normalizzato
    assert "1.9a Modellodi Business" in normalizzato
    assert "I4.0" in normalizzato
    assert "E04" in normalizzato

    assert verifica_grounding_numerico(
        "Il budget e' 15.000 euro, il contributo 50% fino a 40.000 euro al punto 1.9.",
        testo_incollato,
    ) == []

    monkeypatch.setattr(
        risolutore_artigiano,
        "recupera_con_semaforo",
        lambda q, dominio="tecnico", top_k=5: {
            "semaforo": "VERDE",
            "s_max": 0.95,
            "frammenti": [
                {
                    "id": 2,
                    "testo": "4. Bando Nazionale Innovation Manager 2023 contratti non inferiore a nove mesi.",
                },
                {
                    "id": 5,
                    "testo": "50%deicostisostenutiedentroillimitemassimodi40.000€perlemicroepiccoleimprese.",
                },
            ],
        },
    )

    def finto_llm_innovation_manager(sys_p, usr_p, schema):
        return risolutore_artigiano.SoluzioneArtigiano(
            risposta_finale_discorsiva=(
                "Il contributo copre il 50% dei costi sostenuti fino a un massimo di 40.000 euro per le micro e piccole imprese."
            ),
            principio_guida_unico="Bando Nazionale Innovation Manager 2023 (Frammento 2 e 5)",
            elementi_scartati_per_non_fare_mucchio=["Bando Voucher digitali I4.0 - Reggio Emilia"],
            precondizione_wp_richiesta="Contratto di consulenza non inferiore a nove mesi",
            invariante_violato="Equilibrio tra qualificazione del consulente e ammissibilita' spesa",
            ipotesi_causale_unica="Necessita' di iscrizione nell'elenco ministeriale",
            azione_correttiva_singola="Verificare iscrizione del consulente nell'elenco del Ministero",
            esperimento_di_verifica_pratica="Controllare presenza nominativo nell'elenco pubblico",
        )

    esito_im = risolutore_artigiano.risolvi_da_artigiano(
        "Quali sono i requisiti aggiornati del Ministero delle Imprese per i voucher di consulenza in innovazione?",
        dominio="tecnico",
        llm_fn=finto_llm_innovation_manager,
    )
    assert esito_im["colore_nodo_ewd496a"] == "NERO"
    assert esito_im["percentuali_conservate"] is True
    assert esito_im["cifre_non_ancorate"] == []


def test_deduplicazione_file_duplicati_ragioneria_multilingua_e_cascata_rojo_verde(monkeypatch):
    monkeypatch.setattr(store_pgvector, "_OLLAMA_EMBED_OFFLINE", True)
    monkeypatch.setattr(store_pgvector, "_POSTGRES_OFFLINE", True)
    store_pgvector._ARCHIVIO_MEMORIA_RAM.clear()

    blocchi_paniere = [
        ("Page 1", "Lezione 041: credito 10.000 euro cliente Rossi scadenza 90 giorni anticipo 90% oneri 35 euro interesse 6% costo 168,15 euro."),
        ("Page 2", "Lezione 048: Gamma Spa conferimento 35.000 euro, ATTIVITA 60000+20000=80000 - PASSIVITA 50000 = 30000, AVVIAMENTO = 5000."),
    ]
    n_primo = store_pgvector.incasella_e_salva(
        "generale", "eaa78fa0-cc37-4a38-a8a9-cad55f19aa4c.pdf", blocchi_paniere
    )
    n_secondo_duplicato = store_pgvector.incasella_e_salva(
        "generale", "f6d6dbaa-b02d-4116-b558-cb49fc505d13.pdf", blocchi_paniere
    )
    assert n_primo == 2
    assert n_secondo_duplicato == 0

    ctx_ragioneria = (
        "ATTIVITA 60000+20000=80000 - PASSIVITA 50000 = 30000 AVVIAMENTO = 5000. "
        "Spese legali 4.160, IVA 915,20, Ritenuta 800, FIFO 47.650,00."
    )
    assert verifica_grounding_numerico(
        "Attivita' 80.000 euro, capitale netto 30.000 euro, avviamento 5.000 euro, "
        "spese 4.160,00 euro, ritenuta 800,00 euro e in inglese 47,650.00 euro.",
        ctx_ragioneria,
    ) == []

    q_oic34 = (
        "Cosa prevede il nuovo principio contabile OIC 34 sui ricavi entrato in vigore per i bilanci dal 2024 "
        "in merito all'identificazione delle unita' elementari di contabilizzazione?"
    )
    assert client_ollama.rileva_lingua_testo(q_oic34) == "it"
    rag_rojo = store_pgvector.recupera_con_semaforo(
        client_ollama.traduci_query_per_ricerca(q_oic34), dominio="generale", top_k=5
    )
    assert rag_rojo["semaforo"] == "ROJO"

    assert not hasattr(store_pgvector, "_BLOCCHI_OCR_RAGIONERIA")
    assert hasattr(seed_bottega, "_BLOCCHI_OCR_RAGIONERIA")
    trovati_oic34 = seed_bottega.cerca_nel_prontuario_locale(q_oic34)
    assert len(trovati_oic34) == 1
    assert "OIC 34" in trovati_oic34[0][0]
    store_pgvector._ARCHIVIO_MEMORIA_RAM.clear()


def test_strati_l_a_d_senza_nomi_propri_e_rilevamento_globali_mutabili_ast(monkeypatch):
    import cascata_strutturata
    import tempfile

    codice_sample = (
        "CACHE_FATTURE = []\n"
        "def elabora(valore):\n"
        "    CACHE_FATTURE.append(valore)\n"
        "    return valore\n"
    )
    res_ast = analizza_codice_ast(codice_sample)
    assert res_ast["usi_global_mutabili"] == 1

    monkeypatch.setattr(
        cascata_strutturata,
        "recupera_con_semaforo",
        lambda q, dom, top_k=2: {"semaforo": "VERDE", "s_max": 0.90, "s_dominio": 0.85, "frammenti": []},
    )

    def finto_llm_cascata(sys_p, usr_p, schema):
        if schema is cascata_strutturata.OutputLeonardo:
            return cascata_strutturata.OutputLeonardo(
                osservazione_architetturale="Struttura semplice a 1 funzione.",
                scomposizione_moduli=["Modulo puro"],
                complessita_inutile_rilevata=["Lista mutabile globale"],
                proposta_semplificata="Eliminare stato mutabile.",
            )
        if schema is cascata_strutturata.OutputAntirez:
            return cascata_strutturata.OutputAntirez(
                criticita_sicurezza_e_limiti=["Race condition su lista globale"],
                guardrail_mancanti=["Validazione input"],
                valutazione_originalita="Codice minimale.",
                test_consigliati=["Test concorrenza"],
            )
        return cascata_strutturata.OutputDijkstra(
            dominio_e_codominio="int -> int",
            invarianti=["Nessuna mutazione globale"],
            complessita_big_o="O(1)",
            codice_raffinato_finale="def elabora(valore: int) -> int:\n    return valore",
            voto_finale=8,
        )

    with tempfile.TemporaryDirectory() as td:
        file_py = Path(td) / "sample_audit.py"
        file_py.write_text(codice_sample, encoding="utf-8")
        referto = cascata_strutturata.esegui_cascata(str(file_py), llm_fn=finto_llm_cascata)
    assert "## 1. Strato L" in referto
    assert "## 2. Strato A" in referto
    assert "## 3. Strato D" in referto
    assert "Semafori RAG**: Strato L" in referto
    assert "Leonardo" not in referto
    assert "antirez" not in referto
    assert "Dijkstra" not in referto

    prompt_ponte = risolutore_artigiano.genera_prompt_ponte_web_gratuito(
        "Verifica bilancio", [("Sez 1", "Dato 100 euro")]
    )
    assert "Strato L + Strato A + Strato D" in prompt_ponte
    assert "Leonardo" not in prompt_ponte
    assert "Dijkstra" not in prompt_ponte


def test_guardia_anti_trappola_polisemica_blocca_falso_verde_su_ragioneria(monkeypatch):
    frammento_ragioneria_trappola = (
        "[GENERALE] Appunti Ragioneria OIC 19 > Page 18\n\n"
        "Nel bilancio di esercizio dopo 12 mesi si rileva una perdita su crediti del 20% "
        "e una quota di ammortamento. Il passivo di 10.000 euro e la riserva legale del 5% "
        "in compensazione con i BOT da 30.000 euro e aliquota del 15% seguono il principio OIC 19. "
        "Gestione di immobili civili da parte di un'impresa meccanica, regolare tenuta delle scritture "
        "contabili, registrazione in maniera continua e continuativa che rappresenta un debito e costi "
        "della produzione con disponibilita liquide."
    )

    trappole = (
        "Nel bilancio energetico di un compressore volumetrico alternativo con pressione di mandata a 8 bar, "
        "si registra una perdita di portata del 20% dopo 12 mesi di esercizio e la rottura della molla di "
        "ammortamento della valvola di aspirazione: qual e' la causa meccanica radice e quale verifica va "
        "eseguita sulla tenuta delle fasce elastiche del pistone?",
        "En un inversor fotovoltaico trifasico de 10.000 W con bateria de reserva en corriente continua, "
        "el filtro pasivo LCL presenta una caida de tension del 5% y se bloquea el rele de compensacion de "
        "potencia reactiva: cual es el fallo electronico en el puente de transistores IGBT y que medicion "
        "con osciloscopio se debe realizar?",
        "In a reverse osmosis desalination plant processing 30.000 liters per hour, the mass balance "
        "shows a 15% salt rejection drop across the polyamide membrane and a rapid pressure depreciation "
        "in the high-pressure feed pump: what is the chemical scaling root cause and which osmotic backwash "
        "check must be performed?",
        "In un cluster Kubernetes di produzione in alta disponibilita, il pod di bilanciamento del carico "
        "(load balancer) esaurisce la quota di memoria RAM allocata e i nodi worker azzerano i crediti di "
        "CPU disponibili nel namespace, provocando il riavvio forzato dei container: qual e' la strategia "
        "di resource quota e l'azione di health check da configurare nel file YAML per evitare il crash?",
        "Durante un test de penetracion (pentesting) en la red corporativa de la empresa en el ejercicio "
        "fiscal actual, se detecta que el firewall perimetral permite trafico saliente no autorizado en el "
        "puerto activo 443 a traves de un tunel DNS encubierto: cual es la regla de filtrado DPI y que "
        "comando de iptables se debe aplicar para bloquear este canal pasivo de exfiltracion de datos?",
        "In a distributed PostgreSQL cluster running with synchronous multi-master replication via the Raft "
        "consensus protocol, the cluster balance is lost due to a split-brain scenario caused by a network "
        "partition and excessive heartbeat timeout rates between replica nodes: what is the leader election "
        "recovery procedure and how must the consensus quorum configuration be adjusted?",
    )

    monkeypatch.setattr(store_pgvector, "_OLLAMA_EMBED_OFFLINE", True)
    monkeypatch.setattr(store_pgvector, "_POSTGRES_OFFLINE", True)
    store_pgvector._ARCHIVIO_MEMORIA_RAM.clear()
    store_pgvector.incasella_e_salva(
        "generale",
        "Appunti_Ragioneria_Completi.pdf",
        [("Page 18", frammento_ragioneria_trappola)],
    )

    for query_trappola in trappole:
        q_trad = client_ollama.traduci_query_per_ricerca(query_trappola)
        n_spec, ratio_spec = store_pgvector._copertura_termini_specifici(
            query_trappola, q_trad, frammento_ragioneria_trappola
        )
        assert n_spec == 0
        assert ratio_spec == 0.0
        esito_ram = store_pgvector.recupera_con_semaforo(q_trad, dominio="generale", top_k=5)
        assert esito_ram["semaforo"] == "ROJO"
        assert esito_ram["frammenti"] == []

    q_vera_ragioneria = (
        "Come si rileva nel bilancio di esercizio la quota di ammortamento e la riserva legale "
        "secondo il principio contabile OIC 19?"
    )
    n_ok, ratio_ok = store_pgvector._copertura_termini_specifici(
        q_vera_ragioneria, q_vera_ragioneria, frammento_ragioneria_trappola
    )
    assert n_ok >= 2
    assert ratio_ok >= 0.35

    esito_stop = risolutore_artigiano.risolvi_da_artigiano(
        trappole[3],
        dominio="generale",
        cercatore_esterno_fn=None,
        llm_fn=lambda sys_p, usr_p, schema: risolutore_artigiano.PianoRicercaArtigiano(
            fatti_accertati_nel_problema=["Cluster Kubernetes load balancer OOMKilled"],
            dato_esatto_mancante="Specifica ResourceQuota e livenessProbe YAML",
            query_chirurgica_esterna="kubernetes resourcequota limits livenessprobe yaml",
            ispezione_preliminare_sul_campo="Eseguire kubectl describe pod sul load balancer",
        ),
    )
    assert esito_stop["semaforo"] == "ROJO"
    assert esito_stop["modalita"] == "RICERCA_PRIMA_DI_AGIRE"
    store_pgvector._ARCHIVIO_MEMORIA_RAM.clear()


def test_isolamento_chiavi_provider_e_routing_trasparente_su_gemini(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "AQ.ChiaveSoloPerGoogleGemini")

    assert config.ha_chiave_dedicata_provider("gemini") is True
    assert len(config._decodifica_chiave_cloud_default()) > 0
    assert config._decodifica_chiave_cloud_default().startswith("AQ.")
    assert config.ha_chiave_dedicata_provider("deepseek") is False
    assert config.ha_chiave_dedicata_provider("openai") is False
    assert config.ha_chiave_dedicata_provider("groq") is False
    assert config.ha_chiave_dedicata_provider("ollama") is False

    cfg_ds_senza_chiave = config.get_llm_endpoint_config(provider="deepseek", api_key=None)
    assert cfg_ds_senza_chiave["provider"] == "gemini"
    assert "generativelanguage.googleapis.com" in cfg_ds_senza_chiave["chat_url"]

    cfg_ds_con_chiave = config.get_llm_endpoint_config(provider="deepseek", api_key="sk-deepseek-reale")
    assert cfg_ds_con_chiave["provider"] == "deepseek"
    assert cfg_ds_con_chiave["api_key"] == "sk-deepseek-reale"
    assert "api.deepseek.com" in cfg_ds_con_chiave["chat_url"]


def test_articolo_45_costituzione_non_fa_falso_verde_su_gamma_spa_45000_e_auto_guarigione(monkeypatch):
    def finto_conn(**kwargs):
        raise store_pgvector.psycopg2.OperationalError("PostgreSQL locale non attivo")

    def finto_post_off(url, json=None, timeout=10):
        raise requests.exceptions.ConnectionError("Ollama spento")

    monkeypatch.setattr(store_pgvector.psycopg2, "connect", finto_conn)
    monkeypatch.setattr(store_pgvector.requests, "post", finto_post_off)
    store_pgvector._ARCHIVIO_MEMORIA_RAM.clear()

    frammento_gamma_45mila = (
        "Per la costituzione della Gamma Spa il socio conferisce un fabbricato dal valore di 200.000 euro e "
        "crediti v/clienti per 45.000 euro. Cosa prevede l'articolo 2430 del c.c. sulla riserva legale del 20% "
        "prima delle modifiche del d.lgs 139/2015."
    )
    store_pgvector.incasella_e_salva(
        "generale",
        "paniere_ragioneria_gamma.pdf",
        [("Page 33", frammento_gamma_45mila)],
    )

    q_art45 = "Qual è il contenuto dell'articolo 45 della Costituzione italiana e quali modifiche storiche ha subito?"
    rag_off = store_pgvector.recupera_con_semaforo(q_art45, dominio="generale", top_k=5)
    assert rag_off["semaforo"] == "ROJO"
    assert rag_off["frammenti"] == []

    monkeypatch.setattr(
        risolutore_artigiano,
        "recupera_con_semaforo",
        lambda q, dominio="generale", top_k=5: {
            "semaforo": "VERDE",
            "s_max": 0.77,
            "frammenti": [{"id": 1, "testo": frammento_gamma_45mila}],
        },
    )

    esito_auto_stop = risolutore_artigiano.risolvi_da_artigiano(
        q_art45,
        dominio="generale",
        cercatore_esterno_fn=None,
        llm_fn=lambda sys_p, usr_p, schema: risolutore_artigiano.SoluzioneArtigiano(
            risposta_finale_discorsiva=(
                "I frammenti recuperati trattano esclusivamente argomenti di ragioneria e non è presente alcun riferimento "
                "all'articolo 45 della Costituzione italiana."
            ),
            principio_guida_unico="Assenza di copertura documentale",
            elementi_scartati_per_non_fare_mucchio=["Gamma Spa 45.000 euro"],
            precondizione_wp_richiesta="Presenza del testo costituzionale",
            invariante_violato="Impossibilità di rispondere con frammenti estranei alla norma",
            ipotesi_causale_unica="Nei documenti caricati non è presente alcun riferimento all'art. 45 Cost.",
            azione_correttiva_singola="Attivare la ricerca esterna",
            esperimento_di_verifica_pratica="Verificare il testo dell'articolo 45 della Costituzione",
        ),
    )
    assert esito_auto_stop["semaforo"] == "ROJO"
    assert esito_auto_stop["modalita"] == "RICERCA_PRIMA_DI_AGIRE"
    assert esito_auto_stop["colore_nodo_ewd496a"] == "GRIGIO"
    assert esito_auto_stop["frammenti_usati"] == []

    chiamate_llm = {"n": 0}

    def finto_llm_guarigione(sys_p, usr_p, schema):
        chiamate_llm["n"] += 1
        if chiamate_llm["n"] == 1:
            return risolutore_artigiano.SoluzioneArtigiano(
                risposta_finale_discorsiva="Nei frammenti non è presente alcun riferimento all'articolo 45 della Costituzione.",
                principio_guida_unico="Frammenti estranei alla norma",
                elementi_scartati_per_non_fare_mucchio=["Gamma Spa"],
                precondizione_wp_richiesta="Art. 45 Cost.",
                invariante_violato="Mancanza fonte",
                ipotesi_causale_unica="Impossibilità di rispondere senza ricerca esterna",
                azione_correttiva_singola="Cercare fuori",
                esperimento_di_verifica_pratica="Verifica fonte",
            )
        return risolutore_artigiano.SoluzioneArtigiano(
            risposta_finale_discorsiva=(
                "L'articolo 45 della Costituzione (entrata in vigore il 1 gennaio 1948) riconosce al comma 1 la funzione "
                "sociale della cooperazione a carattere di mutualita' e al comma 2 la tutela dell'artigianato (Legge 443/1985)."
            ),
            principio_guida_unico="Articolo 45 della Costituzione Italiana (Comma 1 e Comma 2)",
            elementi_scartati_per_non_fare_mucchio=["Gamma Spa 45.000 euro", "Articolo 2430 c.c."],
            precondizione_wp_richiesta="Tutela costituzionale cooperazione e artigianato dal 1948",
            invariante_violato="Nessuna revisione costituzionale subita dal testo dell'articolo 45 dal 1947",
            ipotesi_causale_unica="Attuazione tramite Legge 443/1985",
            azione_correttiva_singola="Verificare i requisiti di mutualita' prevalente",
            esperimento_di_verifica_pratica="Controllo statuto cooperativa e Legge 443/1985",
        )

    esito_on = risolutore_artigiano.risolvi_da_artigiano(
        q_art45,
        dominio="generale",
        cercatore_esterno_fn=lambda q: [
            (
                "API Wikipedia: Articolo 45 della Costituzione italiana",
                "L'articolo 45 della Costituzione (1948, approvato nel 1947) al comma 1 tutela la cooperazione e al comma 2 l'artigianato (Legge 443/1985).",
            )
        ],
        llm_fn=finto_llm_guarigione,
    )
    assert esito_on["semaforo"] == "VERDE"
    assert esito_on["ricerca_esterna_eseguita"] is True
    assert esito_on["colore_nodo_ewd496a"] == "NERO"
    store_pgvector._ARCHIVIO_MEMORIA_RAM.clear()


def test_domanda_meteo_reggio_emilia_non_aggancia_bando_voucher_camera_commercio():
    query_meteo = "Che tempo fa a Reggio Emilia domani 10 novembre"
    trovati_prontuario = seed_bottega.cerca_nel_prontuario_locale(query_meteo)
    assert trovati_prontuario == []

    store_pgvector._ARCHIVIO_MEMORIA_RAM.clear()
    bando_entry = [
        item for item in seed_bottega.PRONTUARIO_ESTERNO_SOCCORSO
        if "Bando Voucher" in item[0]
    ][0]
    store_pgvector.incasella_e_salva("generale", bando_entry[0], [(bando_entry[0], bando_entry[1])])

    rag_meteo = store_pgvector.recupera_con_semaforo(query_meteo, dominio="generale", top_k=5)
    assert rag_meteo["semaforo"] == "ROJO"
    assert rag_meteo["frammenti"] == []

    esito_stop = risolutore_artigiano.risolvi_da_artigiano(
        query_meteo,
        dominio="generale",
        cercatore_esterno_fn=None,
        llm_fn=lambda sys_p, usr_p, schema: risolutore_artigiano._costruisci_piano_deterministico(query_meteo),
    )
    assert esito_stop["semaforo"] == "ROJO"
    assert esito_stop["modalita"] == "RICERCA_PRIMA_DI_AGIRE"
    assert esito_stop["colore_nodo_ewd496a"] == "GRIGIO"

    query_vera_bando = "Quali spese sono ammissibili per il bando voucher digitali I4.0 della Camera di Commercio di Reggio Emilia?"
    trovati_bando = seed_bottega.cerca_nel_prontuario_locale(query_vera_bando)
    assert len(trovati_bando) == 1
    assert "Bando Voucher" in trovati_bando[0][0]

    rag_bando = store_pgvector.recupera_con_semaforo(query_vera_bando, dominio="generale", top_k=5)
    assert rag_bando["semaforo"] == "VERDE"
    assert len(rag_bando["frammenti"]) >= 1

    store_pgvector._ARCHIVIO_MEMORIA_RAM.clear()


def test_tronca_senza_spezzare_parola_e_ripara_parola_troncata():
    testo = "Se la banca accredita in conto corrente interessi attivi"
    troncato_20 = tronca_senza_spezzare_parola(testo, 20)
    assert troncato_20 == "Se la banca"
    assert not troncato_20.endswith("accredit")
    assert len(troncato_20) <= 20

    troncato_suff = tronca_senza_spezzare_parola(testo, 20, suffisso="...")
    assert troncato_suff == "Se la banca..."
    assert len(troncato_suff) <= 20

    testo_incompleto = "La registrazione contabile prevede l'accredito in banca c/c di 730 euro e la ritenuta all'era"
    riparato = ripara_parola_troncata(testo_incompleto)
    assert riparato == "La registrazione contabile prevede l'accredito in banca c/c di 730 euro e la ritenuta"
    assert not riparato.endswith("all'era")

    testo_finito = "Il totale netto accreditato e' 730 euro."
    assert ripara_parola_troncata(testo_finito) == testo_finito


def test_suddividi_in_pagine_con_continua_e_protocollo_continua_artigiano(monkeypatch):
    testo_lungo = (
        "Prima sezione: interessi attivi bancari lordi per 1.000 euro con ritenuta fiscale al 27% pari a 270 euro. "
        "Seconda sezione: accredito netto in conto corrente per 730 euro presso l'istituto di credito. "
        "Terza sezione: scrittura in partita doppia con Erario c/ritenute e Banca c/c per chiusura esercizio."
    )
    pagine = suddividi_in_pagine_con_continua(testo_lungo, max_caratteri_pagina=130)
    assert len(pagine) >= 2
    for p in pagine[:-1]:
        assert p.endswith("\n\ncontinua")
        assert not p.endswith("...\n\ncontinua")
    assert not pagine[-1].endswith("\n\ncontinua")

    assert risolutore_artigiano.e_richiesta_continua("continua")
    assert risolutore_artigiano.e_richiesta_continua("Continue")
    assert risolutore_artigiano.e_richiesta_continua("continúa")
    assert risolutore_artigiano.e_richiesta_continua("prosegui")
    assert not risolutore_artigiano.e_richiesta_continua("Quali sono gli interessi?")

    risolutore_artigiano.svuota_pagine_continua()

    monkeypatch.setattr(
        risolutore_artigiano,
        "recupera_con_semaforo",
        lambda q, dominio="generale", top_k=5: {
            "semaforo": "VERDE",
            "s_max": 0.88,
            "frammenti": [
                {
                    "id": 1,
                    "testo": "interessi attivi 1.000 euro ritenuta fiscale 27% 270 euro netto 730 euro",
                }
            ],
        },
    )

    def finto_llm_lungo(sys_p, usr_p, schema):
        return risolutore_artigiano.SoluzioneArtigiano(
            risposta_finale_discorsiva=(
                "Interessi attivi bancari lordi 1.000 euro con ritenuta fiscale al 27% pari a 270 euro "
                "ed accredito netto pari a 730 euro in banca conto corrente con chiusura esercizio verificata."
            ),
            principio_guida_unico="Principio contabile bancario e ritenuta 27%",
            elementi_scartati_per_non_fare_mucchio=["Gamma Spa"],
            precondizione_wp_richiesta="Accredito interessi attivi lordi 1.000 euro",
            invariante_violato="Nessuno: ritenuta 270 euro e netto 730 euro",
            ipotesi_causale_unica="Ritenuta d'acconto 27% su 1.000 euro",
            azione_correttiva_singola="Registrare accredito 730 euro",
            esperimento_di_verifica_pratica="Controllo estratto conto bancario",
        )

    esito_p1 = risolutore_artigiano.risolvi_da_artigiano(
        "Se la banca accredita interessi attivi per 1.000 euro con ritenuta 27%, qual e' il netto?",
        dominio="generale",
        llm_fn=finto_llm_lungo,
        max_caratteri_turno=280,
    )
    assert esito_p1["semaforo"] == "VERDE"
    assert esito_p1["colore_nodo_ewd496a"] == "NERO"
    assert esito_p1["risposta_discorsiva"].endswith("\n\ncontinua")
    assert risolutore_artigiano.ha_pagine_continua_in_sospeso("generale")

    pagine_ricevute = [esito_p1["risposta_discorsiva"]]
    while risolutore_artigiano.ha_pagine_continua_in_sospeso("generale"):
        esito_succ = risolutore_artigiano.risolvi_da_artigiano(
            "continua",
            dominio="generale",
        )
        assert esito_succ["semaforo"] == "VERDE"
        assert esito_succ["colore_nodo_ewd496a"] == "NERO"
        assert esito_succ["modalita"] == "CONTINUAZIONE_TESTO"
        pagine_ricevute.append(esito_succ["risposta_discorsiva"])

    assert len(pagine_ricevute) >= 2
    for p in pagine_ricevute[:-1]:
        assert p.endswith("\n\ncontinua")
    assert not pagine_ricevute[-1].endswith("\n\ncontinua")
    assert not risolutore_artigiano.ha_pagine_continua_in_sospeso("generale")

    esito_vuoto = risolutore_artigiano.risolvi_da_artigiano(
        "continua",
        dominio="generale",
    )
    assert esito_vuoto["modalita"] == "CONTINUAZIONE_TESTO"
    assert "Nessuna continuazione in sospeso" in esito_vuoto["risposta_discorsiva"]


def test_senior_engineering_20_principi_integrita_architetturale():
    radice = _trova_radice_progetto()
    for nome_modulo in GERARCHIA_LIVELLI_THE:
        percorso = radice / f"{nome_modulo}.py"
        codice = percorso.read_text(encoding="utf-8")
        albero = ast.parse(codice)

        for nodo in ast.walk(albero):
            assert not isinstance(nodo, ast.Assert), (
                f"Principio 16 violato: trovato 'assert' in produzione nel file {nome_modulo}.py riga {nodo.lineno}"
            )
            if isinstance(nodo, ast.ExceptHandler):
                assert nodo.type is not None, (
                    f"Principio 3 violato: trovato except nudo in {nome_modulo}.py riga {nodo.lineno}"
                )

    req_file = radice / "requirements.txt"
    if req_file.is_file():
        righe = [r.strip() for r in req_file.read_text(encoding="utf-8").splitlines() if r.strip() and not r.startswith("#")]
        for riga in righe:
            assert "==" in riga, f"Principio 19 violato: dipendenza non fissata con '==' in requirements.txt: {riga}"

    assert isinstance(store_pgvector.TERMINI_ECONOMICI_AFFINI, frozenset)
    assert isinstance(store_pgvector.STOPWORDS_RICERCA_COMUNI, frozenset)
    assert isinstance(seed_bottega.STOPWORDS_PRONTUARIO, frozenset)
    assert isinstance(seed_bottega._STOPWORDS_RICERCA_WEB, frozenset)
    assert isinstance(seed_bottega.SIGLE_FINANZIARIE_BREVI, frozenset)
    assert isinstance(risolutore_artigiano._STOPWORDS_CHIRURGICHE, frozenset)
    assert isinstance(client_ollama.GLOSSARIO_MULTILINGUA_IT, MappingProxyType)
    assert isinstance(client_ollama.PAROLE_SPIA_LINGUA, MappingProxyType)
    assert isinstance(risolutore_artigiano._ETICHETTE_FALSIFICATA, MappingProxyType)
    assert isinstance(risolutore_artigiano._ETICHETTE_SCARTATO, MappingProxyType)
    assert isinstance(config.GERARCHIA_LIVELLI_THE, MappingProxyType)

    file_app = radice / "app.py"
    if file_app.is_file():
        albero_app = ast.parse(file_app.read_text(encoding="utf-8"))

        def _e_chiamata_expander(nodo_with):
            for item in nodo_with.items:
                ctx_expr = item.context_expr
                if isinstance(ctx_expr, ast.Call):
                    fn = ctx_expr.func
                    if isinstance(fn, ast.Attribute) and fn.attr == "expander":
                        return True
                    if isinstance(fn, ast.Name) and fn.id == "expander":
                        return True
            return False

        for nodo in ast.walk(albero_app):
            if isinstance(nodo, ast.With) and _e_chiamata_expander(nodo):
                for figlio in ast.walk(nodo):
                    if figlio is not nodo and isinstance(figlio, ast.With) and _e_chiamata_expander(figlio):
                        assert False, (
                            f"Violazione Streamlit: expander annidato dentro altro expander "
                            f"alla riga {figlio.lineno} di app.py"
                        )


def test_sfida_sp500_blocca_frammenti_wikipedia_spuri_oriana_fallaci_e_forza_stop_onesto_rojo(monkeypatch):
    domanda_sfida = "Si preciso che ti hanno sfidato : mi sai dire l'andamento dei prossimi due anni dell'S&P 500?"

    def cercatore_spuri(query: str):
        return [
            ("API Wikipedia: Oriana Fallaci", "Oriana Fallaci è stata una scrittrice e giornalista italiana."),
            ("API Wikipedia: Metamorfosi (Ovidio)", "Le metamorfosi sono un poema epico-mitologico di Ovidio."),
        ]

    def mock_piano(sistema, utente, schema):
        return risolutore_artigiano.PianoRicercaArtigiano(
            stato_memoria="INSUFFICIENTE_CERCA_FUORI",
            fatti_accertati_nel_problema=["Richiesta previsione S&P 500"],
            dato_esatto_mancante="Dati storici e quotazioni indice",
            query_chirurgica_esterna="S&P 500",
            ispezione_preliminare_sul_campo="Verificare fonti finanziarie ufficiali",
        )

    esito_a1 = risolutore_artigiano.risolvi_da_artigiano(
        domanda_sfida,
        dominio="generale",
        cercatore_esterno_fn=cercatore_spuri,
        llm_fn=mock_piano,
    )
    assert esito_a1["semaforo"] == "ROJO", f"Atteso ROJO su frammenti spuri Fallaci/Ovidio, ottenuto {esito_a1['semaforo']}"
    assert esito_a1["modalita"] == "RICERCA_PRIMA_DI_AGIRE"
    assert esito_a1["s_max"] != 0.90, "Il punteggio s_max non deve essere forzato a 0.90 su frammenti spuri"
    assert esito_a1["frammenti_usati"] == []

    def mock_llm_rifiuto(sistema, utente, schema):
        if schema is risolutore_artigiano.PianoRicercaArtigiano:
            return risolutore_artigiano.PianoRicercaArtigiano(
                stato_memoria="INSUFFICIENTE_CERCA_FUORI",
                fatti_accertati_nel_problema=["Richiesta previsione S&P 500"],
                dato_esatto_mancante="Dati storici e quotazioni indice",
                query_chirurgica_esterna="S&P 500",
                ispezione_preliminare_sul_campo="Verificare fonti finanziarie ufficiali",
            )
        return risolutore_artigiano.SoluzioneArtigiano(
            principio_guida_unico="Prudenza e veridicita contabile",
            elementi_scartati_per_non_fare_mucchio=["Previsioni non dimostrabili"],
            precondizione_wp_richiesta="Dati certificati disponibili",
            invariante_violato="wp(S, false) = false",
            ipotesi_causale_unica="Non disponiamo di informazioni sufficienti per formulare alcuna previsione sui prossimi due anni",
            azione_correttiva_singola="Sospendere il giudizio predittivo in assenza di dati",
            esperimento_di_verifica_pratica="Consultare il prospetto dell'indice ufficiale",
            risposta_finale_discorsiva="Non disponiamo di informazioni nei documenti recuperati e non è possibile formulare alcuna previsione attendibile sui prossimi due anni per S&P 500.",
        )

    monkeypatch.setattr(
        risolutore_artigiano,
        "recupera_con_semaforo",
        lambda q, dominio="generale", top_k=5: {
            "semaforo": "VERDE",
            "s_max": 0.85,
            "frammenti": [{"id": 1, "testo": "[GENERALE] Dati di mercato generici"}],
        },
    )

    esito_a2 = risolutore_artigiano.risolvi_da_artigiano(
        domanda_sfida,
        dominio="generale",
        llm_fn=mock_llm_rifiuto,
    )
    assert esito_a2["semaforo"] == "ROJO", f"Atteso ROJO su rifiuto esplicito LLM, ottenuto {esito_a2['semaforo']}"
    assert esito_a2["modalita"] == "RICERCA_PRIMA_DI_AGIRE"
    assert esito_a2["s_max"] == 0.18
    assert esito_a2["frammenti_usati"] == []

    query_compatta = seed_bottega._estrai_query_compatta_web(domanda_sfida)
    assert "S&P 500" in query_compatta
    assert "sfidato" not in query_compatta.lower()
    assert "preciso" not in query_compatta.lower()

    termini = seed_bottega._estrai_termini_chiave_sostantivi(query_compatta)
    assert any(t in ("s&p", "sp", "500") for t in termini)

    class _FakeWikiMista:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "query": {
                    "search": [
                        {"title": "Oriana Fallaci", "snippet": "Scrittrice e giornalista italiana."},
                        {"title": "S&P 500", "snippet": "Indice azionario composto da 500 titoli USA."},
                    ]
                }
            }

    def finto_get_wiki(url, params=None, headers=None, timeout=10):
        return _FakeWikiMista()

    monkeypatch.setattr(seed_bottega.requests, "get", finto_get_wiki)
    risultati_wiki = seed_bottega._cerca_tramite_wikipedia_api(domanda_sfida, query_compatta)
    assert len(risultati_wiki) == 1
    assert "S&P 500" in risultati_wiki[0][0]
    assert "Oriana Fallaci" not in [item[0] for item in risultati_wiki]


def test_benchmark_verticale_25_casi_b2b_qualita_e_sicurezza():
    from benchmarks.valuta_benchmark_verticale import esegui_benchmark_completo
    radice = _trova_radice_progetto()
    file_json = radice / "benchmarks" / "golden_dataset_verticale.json"
    report = esegui_benchmark_completo(file_json)
    assert report["casi_totali"] == 25
    assert report["casi_superati"] == 25
    assert report["accuratezza_complessiva_pct"] == 100.0
    assert report["metriche_chiave_b2b"]["precisione_relazionale_write_barrier_pct"] == 100.0
    assert report["metriche_chiave_b2b"]["accuratezza_calcoli_derivati_pct"] == 100.0
    assert report["metriche_chiave_b2b"]["diagnostica_cause_multiple_pct"] == 100.0
    assert report["metriche_chiave_b2b"]["gestione_revisioni_documentali_pct"] == 100.0
    assert report["metriche_chiave_b2b"]["sicurezza_owasp_rag_injection_pct"] == 100.0


def test_pulizia_ligature_slide_esclusione_agenda_e_modelli_gemini_reali():
    testo_corrotto = "Se\ue009e regole con e\ue008etto e\ufb00etto su \ufb01le, \ufb02usso, u\ufb03cio e a\ufb04itto\r\nNuova riga."
    pulito = store_pgvector.normalizza_spazi_testo_pdf(testo_corrotto)
    assert pulito == "Sette regole con effetto effetto su file, flusso, ufficio e afflitto\nNuova riga."

    assert store_pgvector._e_slide_rumore_o_indice("AGENDA DEL GIORNO\nOre 9:00 avvio") is True
    assert store_pgvector._e_slide_rumore_o_indice("Pausa pranzo dalle 13 alle 14") is True
    assert store_pgvector._e_slide_rumore_o_indice("SOLO PER PREPARARE - NON SI PROIETTA") is True
    assert store_pgvector._e_slide_rumore_o_indice("Appendice AhaSlides per il docente") is True
    assert store_pgvector._e_slide_rumore_o_indice("Rompighiaccio: due verità e una bugia") is True
    assert store_pgvector._e_slide_rumore_o_indice("Biglietto di uscita finale") is True
    assert store_pgvector._e_slide_rumore_o_indice("Le sette regole per la leggibilità del codice Python") is False

    pagine_finto_slide = [
        (1, "Corso Arkemis\nIntroduzione"),
        (2, "AGENDA DEL GIORNO\nOre 9:00 Benvenuto\nOre 13:00 Pausa pranzo"),
        (3, "Regola 1\nNomi parlanti e descrittivi"),
        (4, "Regola 2\nFunzioni brevi e pure"),
        (5, "Regola 3\nNon ripetere codice identico"),
        (6, "Regola 4\nZero commenti vuoti"),
        (7, "Regola 5\nGestire eccezioni con rigore"),
    ]
    blocchi_slide = store_pgvector._elabora_pagine_pdf(pagine_finto_slide)
    assert len(blocchi_slide) <= 2
    testo_totale = " ".join(t for _, t in blocchi_slide)
    assert "AGENDA DEL GIORNO" not in testo_totale
    assert "Regola 1" in testo_totale
    assert "Regola 5" in testo_totale
    assert "### [Page 3]" in testo_totale

    assert config.PROVIDER_CLOUD_CONFIG["gemini"]["default_model"] == "gemini-2.5-flash"
    assert "gemini-2.5-flash" in config.MODELLI_FALLBACK_GEMINI
    assert "gemini-3.5-flash-lite" not in config.MODELLI_FALLBACK_GEMINI
    assert "gemini-3.1-flash-lite" not in config.MODELLI_FALLBACK_GEMINI
    assert "gemini-3.8-flash" not in config.MODELLI_FALLBACK_GEMINI

    finto_frammenti = [
        {"id": 1, "testo": "[TECNICO] corso_arkemis.pdf > Page 3\nRegola 1: Nomi parlanti"},
        {"id": 2, "testo": "[TECNICO] corso_arkemis.pdf > Page 4\nRegola 2: Funzioni brevi"},
    ]
    sol_det = risolutore_artigiano._costruisci_soluzione_deterministica(
        "Quali sono le regole del corso?",
        finto_frammenti,
        [],
        lingua="it",
    )
    assert "[TECNICO]" not in sol_det.risposta_finale_discorsiva
    assert "Regola 1: Nomi parlanti" in sol_det.risposta_finale_discorsiva
    assert "Regola 2: Funzioni brevi" in sol_det.risposta_finale_discorsiva
    assert "---" in sol_det.risposta_finale_discorsiva
