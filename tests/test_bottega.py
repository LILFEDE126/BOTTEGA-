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
    """Finds the directory containing config.py whether run from tests/ or project root."""
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
    """JISO TARIC discipline: verifies that none of the 13 application modules contain inline '#'
    comments (except the '#!/usr/bin/env python3' shebang on line 1)."""
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
    """Verifies that queries written in English or Spanish are translated to match the Italian handbook."""
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
    assert segretario.holyness_di("dijkstra") == 0
    assert segretario.puo_essere_vittima("dijkstra") is True

    with segretario.sezione_sacra("dijkstra", fabbisogno_massimo=2):
        assert segretario.holyness_di("dijkstra") == 1
        assert segretario.puo_essere_vittima("dijkstra") is False

    assert segretario.holyness_di("dijkstra") == 0
    assert segretario.puo_essere_vittima("dijkstra") is True

    with pytest.raises(RuntimeError, match="Violazione EWD116"):
        with segretario.sezione_sacra("dijkstra", fabbisogno_massimo=5):
            pass
    assert segretario.holyness_di("dijkstra") == 0


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
        "leonardo", "Metodo Empirico", "Osservazione", "Misurare l'AST prima di giudicare."
    )
    assert testo.startswith("[LEONARDO] Metodo Empirico > Osservazione\n\n")
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
        lambda q, dominio="leonardo", top_k=3: {"semaforo": "ROJO", "s_max": 0.12, "frammenti": []},
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

    def finto_recupera(q, dominio="leonardo", top_k=3):
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
        lambda q, dominio="leonardo", top_k=3: {
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