#!/usr/bin/env python3
"""Layer 5 (THE): Complete suite of 26 pure unit tests (zero network, zero DB, zero LLM).
Includes AST check for zero '#' comments in source modules and multilingual EN/ES -> IT search tests."""

from decimal import Decimal
import io
import math
from pathlib import Path
import tokenize
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
                        "snippet": 'Fenomeno idraulico di <span class="searchmatch">sovrappressione</span>.',
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
    assert modelli_tentati[1] == "gemini-3.5-flash-lite"

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


def test_strati_l_a_d_senza_nomi_propri_e_rilevamento_globali_mutabili_ast(tmp_path, monkeypatch):
    import cascata_strutturata

    codice_sample = (
        "CACHE_FATTURE = []\n"
        "def elabora(valore):\n"
        "    CACHE_FATTURE.append(valore)\n"
        "    return valore\n"
    )
    res_ast = analizza_codice_ast(codice_sample)
    assert res_ast["usi_global_mutabili"] == 1

    file_py = tmp_path / "sample_audit.py"
    file_py.write_text(codice_sample, encoding="utf-8")

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
        "in compensazione con i BOT da 30.000 euro e aliquota del 15% seguono il principio OIC 19."
    )

    q_it = (
        "Nel bilancio energetico di un compressore volumetrico alternativo con pressione di mandata a 8 bar, "
        "si registra una perdita di portata del 20% dopo 12 mesi di esercizio e la rottura della molla di "
        "ammortamento della valvola di aspirazione: qual e' la causa sulle fasce elastiche del pistone?"
    )
    q_es = (
        "En un inversor fotovoltaico trifasico de 10.000 W con bateria de reserva en corriente continua, "
        "el filtro pasivo LCL presenta una caida de tension del 5% y se bloquea el rele de compensacion: "
        "cual es el fallo en el puente de transistores IGBT y que medicion con osciloscopio realizar?"
    )
    q_en = (
        "In a reverse osmosis desalination plant processing 30.000 liters per hour, the mass balance "
        "shows a 15% salt rejection drop across the polyamide membrane and a rapid pressure depreciation "
        "in the high-pressure feed pump: what is the chemical scaling root cause and backwash check?"
    )

    for query_trappola in (q_it, q_es, q_en):
        q_trad = client_ollama.traduci_query_per_ricerca(query_trappola)
        n_spec, ratio_spec = store_pgvector._copertura_termini_specifici(
            query_trappola, q_trad, frammento_ragioneria_trappola
        )
        assert n_spec == 0
        assert ratio_spec == 0.0

    q_vera_ragioneria = (
        "Come si rileva nel bilancio di esercizio la quota di ammortamento e la riserva legale "
        "secondo il principio contabile OIC 19?"
    )
    n_ok, ratio_ok = store_pgvector._copertura_termini_specifici(
        q_vera_ragioneria, q_vera_ragioneria, frammento_ragioneria_trappola
    )
    assert n_ok >= 2
    assert ratio_ok >= 0.35

    monkeypatch.setattr(
        risolutore_artigiano,
        "recupera_con_semaforo",
        lambda q, dominio="generale", top_k=3: {"semaforo": "ROJO", "s_max": 0.18, "frammenti": []},
    )
    esito = risolutore_artigiano.risolvi_da_artigiano(
        q_it,
        dominio="generale",
        cercatore_esterno_fn=None,
        llm_fn=lambda sys_p, usr_p, schema: risolutore_artigiano.PianoRicercaArtigiano(
            fatti_accertati_nel_problema=["Compressore volumetrico a 8 bar", "Perdita portata 20%"],
            dato_esatto_mancante="Curva di tenuta valvola aspirazione e fasce pistone",
            query_chirurgica_esterna="compressore volumetrico alternativo valvola aspirazione fasce pistone",
            ispezione_preliminare_sul_campo="Misurare compressione cilindro a freddo",
        ),
    )
    assert esito["semaforo"] == "ROJO"
    assert esito["modalita"] == "RICERCA_PRIMA_DI_AGIRE"






