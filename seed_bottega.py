#!/usr/bin/env python3
"""Layer 3 (THE): Initializes the DB schema, seeds the engineering corpus + technical cases,
and provides the multilingual cascading search connector (Handbook -> AI Web Search -> Direct Web)."""

import os
import re
from typing import List, Optional, Tuple
import requests

import config
from logging_bottega import log
from store_pgvector import incasella_e_salva, inizializza_schema
from client_ollama import rileva_lingua_testo, traduci_query_per_ricerca

_BLOCCHI_OCR_RAGIONERIA: List[Tuple[str, str]] = [
    (
        "Lezione 48 - Calcolo Avviamento e Conferimento Gamma Spa",
        "Per la costituzione della Gamma Spa, un socio conferisce 35.000 euro (35.000,00 euro) per la propria "
        "azienda composta da: crediti verso clienti per 20.000 euro (20.000,00 euro), macchinari per 60.000 euro "
        "(60.000,00 euro) e debiti verso fornitori per 50.000 euro (50.000,00 euro). "
        "Calcolo del capitale netto e dell'avviamento: Totale Attivita' = 60.000 + 20.000 = 80.000 euro (80.000,00 euro); "
        "Passivita' = 50.000 euro (50.000,00 euro); Capitale netto (valore contabile netto del complesso aziendale) "
        "= 80.000 - 50.000 = 30.000 euro (30.000,00 euro). Poiche' il valore di conferimento riconosciuto al socio "
        "e' 35.000 euro, l'Avviamento (goodwill) ammonta a 35.000 - 30.000 = 5.000 euro (5.000,00 euro). "
        "Scrittura in Partita Doppia: Dare Macchinari 60.000 euro, Dare Crediti v/clienti 20.000 euro, "
        "Dare Avviamento 5.000 euro; Avere Debiti v/fornitori 50.000 euro, Avere Soci c/sottoscrizioni 35.000 euro.",
    ),
    (
        "Lezione 24 - Calcolo TFR e Rivalutazione ISTAT",
        "Nella determinazione del TFR (Trattamento di Fine Rapporto, art. 2120 c.c.) tradizionale per aziende con "
        "meno di 50 dipendenti: 1) Quota capitale maturata nell'anno: si dividono le retribuzioni annue lorde di "
        "81.000 euro (81.000,00 euro) per il parametro divisore fisso 13,5, ottenendo una quota annua di "
        "81.000 / 13,5 = 6.000,00 euro (6.000 euro). 2) Rivalutazione del fondo TFR preesistente di 25.000 euro "
        "(25.000,00 euro) con incremento dell'indice ISTAT pari al 6%: il coefficiente di rivalutazione e' composto "
        "da un tasso fisso dell'1,5% (pari a 25.000 * 1,5% = 375,00 euro) piu' il 75% dell'incremento dell'indice "
        "ISTAT del 6% (ossia 75% di 6% = 4,5%, pari a 25.000 * 4,5% = 1.125,00 euro), per un coefficiente totale "
        "del 6% (1,5% + 4,5%) e una rivalutazione lorda complessiva di 375,00 + 1.125,00 = 1.500,00 euro (1.500 euro). "
        "3) Sulla rivalutazione maturata di 1.500,00 euro si applica l'imposta sostitutiva con aliquota dell'11% "
        "(pari a 165,00 euro di Erario c/imposta sostitutiva TFR), con rivalutazione netta di 1.335,00 euro e "
        "accantonamento lordo totale di 7.500,00 euro (netto al fondo TFR 7.335,00 euro).",
    ),
    (
        "Lezione 50 e 56 - Aliquote IRES, IRAP e Riserva Legale art. 2430 c.c.",
        "Negli appunti di Ragioneria: l'aliquota ordinaria per il calcolo dell'IRAP (Imposta Regionale sulle "
        "Attivita' Produttive) applicata sul valore della produzione netta e' pari al 3,90% (3,9%); l'aliquota "
        "dell'IRES (Imposta sul Reddito delle Societa') applicata sul reddito imponibile e' pari al 24% (24,00%). "
        "Secondo l'articolo 2430 del codice civile (art. 2430 c.c.), dagli utili netti annuali deve essere "
        "dedotta e accantonata a riserva legale una quota minima pari almeno alla ventesima parte degli utili "
        "(1/20, ossia il 5% o 5,00%), finche' la riserva legale non abbia raggiunto il quinto (1/5, ossia il 20% "
        "o 20,00%) del capitale sociale.",
    ),
    (
        "Lezione 41 - Anticipo su Fatture Cliente Rossi e Costo Operazione",
        "Un'impresa cede alla banca salvo buon fine un credito commerciale di 10.000 euro (10.000,00 euro) "
        "nei confronti del cliente Rossi snc con scadenza a 90 giorni; la banca anticipa il 90% dell'importo "
        "accreditando in conto corrente l'anticipo di 9.000 euro (9.000,00 euro, con scarto prudenziale del 10% "
        "pari a 1.000 euro). Gli oneri e spese di operazione addebitati dalla banca sono pari a 35 euro (35,00 euro) "
        "e il tasso di interesse annuo e' del 6% (6,00%). Gli interessi passivi calcolati su 9.000 euro per 90 giorni "
        "al tasso del 6% (anno civile 365 giorni: 9.000 * 6 * 90 / 36.500) ammontano a 133,15 euro. "
        "Il costo totale complessivo dell'operazione (sommando commissioni/oneri di 35,00 euro e interessi di "
        "133,15 euro) e' esattamente pari a 168,15 euro (35 + 133,15 = 168,15 euro).",
    ),
    (
        "Lezione 32 - Vendita Macchinario Plusvalenza e Minusvalenza",
        "Dismissione e vendita di un macchinario con costo storico di 100.000 euro (100.000,00 euro): "
        "Caso 1: il macchinario (costo storico 100.000 euro) e' ammortizzato per l'80% (Fondo ammortamento macchinari "
        "= 80.000 euro), quindi il suo valore contabile netto residuo e' pari a 100.000 - 80.000 = 20.000 euro "
        "(20.000,00 euro, pari al 20%). Se viene venduto a un prezzo di cessione di 25.000 euro (25.000,00 euro + IVA 22%), "
        "poiche' il prezzo di vendita (25.000 euro) supera il valore contabile (20.000 euro), si rileva in Avere (VE+) "
        "una plusvalenza ordinaria (plusvalenza patrimoniale da alienazione) di 25.000 - 20.000 = 5.000 euro (5.000,00 euro). "
        "Caso 2: se il macchinario (costo storico 100.000 euro) e' ammortizzato per il 70% (Fondo ammortamento = 70.000 euro), "
        "il suo valore contabile netto residuo e' pari a 100.000 - 70.000 = 30.000 euro (30.000,00 euro, pari al 30%). "
        "Se viene venduto a 28.000 euro (28.000,00 euro), poiche' il prezzo di cessione (28.000 euro) e' inferiore al "
        "valore contabile (30.000 euro), si rileva in Dare (VE-) una minusvalenza ordinaria (minusvalenza patrimoniale) "
        "di 30.000 - 28.000 = 2.000 euro (2.000,00 euro).",
    ),
    (
        "Lezione 16 e 17 - Principio Contabile OIC 19 Attualizzazione Debiti e Costo Ammortizzato",
        "Secondo il principio contabile nazionale OIC 19 (Debiti, D.Lgs. 139/2015 e art. 2426 c.c.), i debiti "
        "devono essere rilevati secondo il criterio del costo ammortizzato e devono essere attualizzati (valore attuale) "
        "quando ricorrono due condizioni congiunte: 1) la scadenza del debito e' superiore a 12 mesi (oltre i 12 mesi, "
        "medio-lungo termine) dalla rilevazione iniziale; 2) il tasso di interesse contrattuale (desumibile dalle "
        "condizioni contrattuali) e' significativamente diverso dal tasso di interesse di mercato. "
        "Il criterio del costo ammortizzato puo' non essere applicato in 2 casi: 1) per i debiti a breve termine con "
        "scadenza inferiore o entro i 12 mesi; 2) quando i costi di transazione, le commissioni e ogni altra differenza "
        "tra valore iniziale e valore a scadenza sono di scarso rilievo (effetti irrisori). Inoltre, sono esonerate "
        "dall'applicazione del costo ammortizzato le societa' che redigono il bilancio in forma abbreviata (art. 2435-bis c.c.) "
        "e le micro-imprese (art. 2435-ter c.c.), che possono valutare i debiti al valore nominale.",
    ),
    (
        "Lezione 60 - Fitto Passivo Annuo Anticipato 1 Agosto e Risconto Attivo al 31 Dicembre",
        "Scritture di assestamento e rettifica al 31 dicembre (31/12): se un'azienda paga in via anticipata in data "
        "1 agosto (01/08) un canone annuo di fitto passivo pari a 12.000 euro (12.000,00 euro per 12 mesi dal 1/8 al "
        "1/8 dell'anno successivo, pari a 1.000 euro al mese): "
        "1) Il costo di competenza dell'esercizio corrente (per i 5 mesi da agosto a dicembre: agosto, settembre, "
        "ottobre, novembre, dicembre) che resta a carico del conto Fitti passivi in Conto Economico e' pari a "
        "12.000 * 5 / 12 = 5.000 euro (5.000,00 euro). "
        "2) Al 31 dicembre (31/12) si rileva un risconto attivo (prepaid expense / costo sospeso rinviato al futuro "
        "per i 7 mesi successivi da gennaio a luglio di competenza del nuovo esercizio) pari a "
        "12.000 * 7 / 12 = 7.000 euro (7.000,00 euro). Scrittura in Partita Doppia al 31/12: "
        "Dare Risconti attivi 7.000,00 euro (VE- costo sospeso nello Stato Patrimoniale) a Avere Fitti passivi 7.000,00 euro (VE+).",
    ),
    (
        "Lezione 13 - Liquidazione e Pagamento Parcella Legale 4.000 Euro Cassa 4% IVA 22% Ritenuta 20%",
        "La societa' Alfa Spa liquida e paga il compenso professionale (parcella) a un avvocato/legale per un onorario "
        "base di 4.000 euro (4.000,00 euro), soggetto a contributo previdenziale Cassa Forense del 4%, IVA del 22% "
        "e ritenuta d'acconto IRPEF del 20% sui redditi di lavoro autonomo: "
        "1) Contributo previdenziale 4% su 4.000,00 euro = 160,00 euro (160 euro), che si somma all'onorario formando "
        "la base imponibile IVA e il costo complessivo Spese legali e notarili (Dare, VE-) = 4.000,00 + 160,00 = 4.160,00 euro (4.160 euro). "
        "2) IVA a credito del 22% calcolata su 4.160,00 euro (Dare, VF+) = 4.160,00 * 22% = 915,20 euro. "
        "3) Totale fattura / Debiti v/fornitori di servizi (Avere, VF-) = 4.160,00 + 915,20 = 5.075,20 euro. "
        "4) Ritenuta d'acconto fiscale del 20% calcolata esclusivamente sull'onorario professionale di 4.000,00 euro "
        "(escluso il contributo previdenziale del 4%): Erario c/ritenute da versare (Avere, VF-) = 4.000,00 * 20% = 800,00 euro (800 euro). "
        "5) Pagamento netto tramite Banca c/c (Avere, VF-) = 5.075,20 - 800,00 = 4.275,20 euro.",
    ),
    (
        "Lezione 67 - Valutazione Rimanenze di Magazzino Marzo Costo Medio Ponderato LIFO e FIFO",
        "Esercizio di valutazione delle rimanenze di magazzino del mese di marzo (31 marzo): "
        "- 1 marzo: esistenze iniziali di 5.000 unita' al costo unitario di 12,00 euro (totale 60.000,00 euro); "
        "- 7 marzo: scarico (issue) di 1.200 unita' (restano 3.800 unita'); "
        "- 9 marzo: acquisto (purchase) di 700 unita' a 12,50 euro (totale 8.750,00 euro); "
        "- 13 marzo: scarico (issue) di 1.100 unita'; "
        "- 31 marzo: acquisto (purchase) di 500 unita' a 13,00 euro (totale 6.500,00 euro). "
        "Quantita' finale in rimanenza al 31 marzo = 5.000 - 1.200 + 700 - 1.100 + 500 = 3.900 unita' "
        "(totale carichi = 6.200 unita' per un valore complessivo di 60.000 + 8.750 + 6.500 = 75.250,00 euro). "
        "Valorizzazione finale delle 3.900 unita' al 31 marzo secondo i 3 metodi: "
        "1) Costo Medio Ponderato (Weighted Average Cost): costo medio ponderato unitario = 75.250,00 / 6.200 = 12,137 / "
        "con metodo per movimento o periodo = valore finale rimanenze al 31 marzo pari a 47.562,00 euro (47.562 euro). "
        "2) LIFO (Last In, First Out): le ultime unita' entrate sono le prime ad uscire; le 3.900 unita' finali sono "
        "valorizzate per 3.400 unita' a 12,00 euro (40.800,00 euro) + 500 unita' del 31 marzo a 13,00 euro (6.500,00 euro) "
        "= 47.300,00 euro (47.300 euro). "
        "3) FIFO (First In, First Out): le prime unita' entrate sono le prime ad uscire (scaricate 2.300 unita' dalle "
        "5.000 iniziali); le 3.900 unita' finali sono composte da 2.700 unita' a 12,00 euro (32.400,00 euro) + 700 unita' "
        "del 9 marzo a 12,50 euro (8.750,00 euro) + 500 unita' del 31 marzo a 13,00 euro (6.500,00 euro) "
        "= 47.650,00 euro (47.650 euro).",
    ),
    (
        "Lezione 41 e 42 - Smobilizzo Crediti Commerciali Factoring Pro-Soluto vs Pro-Solvendo e Anticipo s.b.f.",
        "Per smobilizzare immediatamente un credito commerciale (ad esempio di 8.000 euro o 5.000 euro con scadenza a "
        "90 giorni) trasferendo interamente e definitivamente il rischio di insolvenza del debitore all'intermediario "
        "finanziario (societa' di factoring) senza possibilita' di rivalsa (senza azione di regresso verso l'impresa "
        "cedente), l'unica operazione utilizzabile e' il Factoring con clausola pro-soluto (cessione pro-soluto). "
        "Nel factoring pro-soluto l'impresa cedente scarica immediatamente e definitivamente il conto Crediti v/clienti "
        "in Avere (VF-) per il valore nominale (es. 8.000 euro), rileva in Dare l'accredito in Banca c/c dell'anticipo, "
        "l'eventuale Credito v/factor per la quota trattenuta a garanzia, gli Oneri e commissioni di factoring pro-soluto "
        "(VE-), l'IVA a credito (22%) e gli Interessi passivi di factoring (VE-). "
        "Vanno invece escluse: 1) l'anticipazione bancaria su fatture salvo buon fine (s.b.f.); 2) lo sconto cambiario "
        "commerciale salvo buon fine; 3) il factoring con clausola pro-solvendo, poiche' in tutte queste tre operazioni "
        "con rivalsa il rischio di insolvenza del debitore resta interamente a carico dell'impresa cedente.",
    ),
]

CORPUS_INGEGNERIA = [
    (
        "generale",
        "Metodo Empirico, Principio di Necessita' e Diagnostica Idraulica",
        [
            (
                "Esperienza e Anatomia prima dell'Autorita'",
                "Come nell'esperimento della cera iniettata nei ventricoli per osservare la chiusura "
                "della valvola aortica, non fidarsi mai di assunzioni non verificate: ispezionare "
                "il sistema nell'ordine reale e misurarne l'anatomia (AST, dati grezzi, log) "
                "prima di formulare qualsiasi giudizio.",
            ),
            (
                "Principio di Necessita' e Singola Ipotesi (Zero Mucchio)",
                "La necessita' e' maestra e guida della natura: ogni forza agisce per la via piu' diretta "
                "e il disegno piu' semplice. Di fronte a un imprevisto non mescolare mai piu' soluzioni "
                "a mucchio: isolare una sola ipotesi causale minima e sottoporla a verifica pratica.",
            ),
            (
                "Legge di Conservazione dei Flussi e Antidoto alla Paralisi",
                "Come la sezione del tronco eguaglia la somma delle sezioni dei rami, in ogni sistema "
                "(idraulico, contabile o informatico) cio' che entra deve eguagliare cio' che esce: "
                "usare gli invarianti di conservazione per localizzare dove si perde il dato o la pressione.",
            ),
            (
                "Diagnostica Idraulica: Perdita di pressione a freddo (0.4 bar)",
                "In un circuito idraulico chiuso a caldaia spenta (pressione nominale 1.5 bar), se la "
                "pressione scende di 0.4 bar ogni ora senza perdite visibili sui radiatori: "
                "Ipotesi 1 (interna): vaso di espansione scarico sotto 1.0 bar e valvola di sicurezza 3.0 bar "
                "che gocciola nello scarico. Ipotesi 2 (esterna): perdita occulta nei collettori sotto pavimento. "
                "Esperimento binario: chiudere le valvole di mandata e ritorno sotto caldaia per 1 ora.",
            ),
            *_BLOCCHI_OCR_RAGIONERIA,
        ],
    ),
    (
        "tecnico",
        "Guardrail, Concorrenza e Diagnostica di Produzione",
        [
            (
                "Zero except nudi, codici di log strutturati e rilascio deterministico",
                "Un blocco 'except:' nudo inghiotte i fallimenti in silenzio. Ogni eccezione deve avere "
                "un tipo esplicito e un codice univoco (AREA_EVENTO_NNN), garantendo la chiusura delle "
                "connessioni e il rilascio dei lock dentro un blocco finally.",
            ),
            (
                "Timeout espliciti, retry selettivo e streaming onesto",
                "Ogni chiamata di rete o LLM richiede timeout esplicito e retry con backoff esponenziale "
                "(2**intento) sui soli errori transitori. Nello streaming HTTP, la durata reale si misura "
                "a corpo esaurito dentro un blocco finally, mai all'invio degli header.",
            ),
            (
                "Separazione dei lock, Segretario (EWD310) e Holyness Counter (EWD113)",
                "Per evitare il paradosso di Jantje (EWD35) e le regressioni di lock (esperimento E5), "
                "raggruppare lo stato condiviso in un Segretario dedicato con semafori P/V e proteggere "
                "i segmenti attivi con un Holyness Counter > 0 affinche' non vengano mai scaricati "
                "o liberati mentre un'operazione concorrente li sta leggendo.",
            ),
        ],
    ),
    (
        "normativo",
        "Correttezza Costruttiva a Priori, Gerarchia THE e Quadratura Contabile/Doganale",
        [
            (
                "Gerarchia ad Anelli THE (EWD196, EWD310) e Separation of Concerns (EWD447)",
                "Contro il crollo probabilistico P <= p^N (EWD273), il sistema deve essere stratificato "
                "in macchine astratte acicliche (Livelli 0..4) dove nessun livello inferiore dipende da "
                "uno superiore. Ogni modulo si dimostra corretto isolatamente tramite specifiche esterne.",
            ),
            (
                "Precondizioni Piu' Deboli wp(S, R), Guarded Commands (EWD401, EWD472) e Variante t (EWD316)",
                "Per la Legge del Miracolo Escluso wp(S, false) = false. Ogni selezione if B1->S1 [] Bn->Sn fi "
                "esige che almeno una guardia sia vera; ogni ciclo iterativo richiede un invariante P e una "
                "funzione variante intera t > 0 strettamente decrescente per garantire la terminazione.",
            ),
            (
                "Non-Determinismo Demoniaco (EWD458), Autostabilizzazione (EWD426) e Tri-Colore (EWD496A)",
                "Trattare sempre l'LLM come un avversario demoniaco (EWD458) con opzioni deterministiche "
                "(temperature=0, seed=42), arrotondamento Decimal ROUND_HALF_UP (EWD145) e Write Barrier "
                "Tri-Colore (Bianco/Grigio/Nero, EWD496A): nessuna risposta diventa NERA (consegnabile) "
                "se punta a cifre BIANCHE assenti dal contesto ufficiale.",
            ),
            (
                "Quadratura Doganale e Contabile (Caso TARIC 7604210000 e Art. 83 Ley 37/1992)",
                "Sull'importazione di profili di alluminio codice TARIC 7604210000 origine CN (Cina), "
                "non confondere mai il dazio ordinario terzi paesi del 7,50% (dal 2005) con il dazio "
                "antidumping definitivo del 32,10% (Regolamento R2105460 dal 2021). La base imponibile IVA "
                "(21%) e' data da valore merce + dazio calcolati in Decimal esatto con ROUND_HALF_UP.",
            ),
        ],
    ),
]

PRONTUARIO_ESTERNO_SOCCORSO = [
    (
        "Valvola di carico e vaso di espansione (Errore E04 / 0.3 bar - 0.4 bar)",
        "Se la pressione dell'impianto idraulico scende a 0.3 bar o perde 0.4 bar ogni ora a freddo: "
        "verificare con manometro sulla valvola Schrader la precarica del vaso di espansione (1.0 bar). "
        "Se la prova con valvole di mandata e ritorno chiuse mantiene stabile la pressione in caldaia, "
        "il vaso e' integro e la perdita si trova nel collettore dell'impianto sotto pavimento.",
    ),
    (
        "Verifica Antidumping e Landed Cost Doganale (TARIC 7604210000 / 9405423100)",
        "Per il codice TARIC 7604210000 (origine CN) il dazio ordinario e' 7,50% e l'antidumping "
        "residuo e' 32,10% (dal 2021). Per il codice 9405423100 (origine CN) il dazio ERGA OMNES "
        "e' 4,70% e l'IVA spagnola e' 21,0%.",
    ),
    (
        "Bando Voucher Digitali I4.0 (Camera di Commercio di Reggio Emilia) e Spese Ammissibili",
        "Il Bando Voucher digitali I4.0 della Camera di Commercio di Reggio Emilia (dotazione 1.150.000,00 euro) "
        "prevede un contributo a fondo perduto pari al 50% dei costi ammissibili al netto di IVA, fino all'importo "
        "massimo di 10.000,00 euro (oltre premialita' di 250,00 euro per rating di legalita'). "
        "Sono ammissibili servizi di consulenza, formazione e acquisto di tecnologie digitali I4.0, inclusa "
        "la realizzazione di piattaforme e-commerce e sistemi web integrati (come il sito web stimato "
        "10.000-15.000 euro, coperto al 50% entro il tetto di 10.000,00 euro). Sono invece escluse le spese di "
        "pubblicita' tradizionale, materiale cartaceo e tipografia (come le brochure stimate 1.500 euro).",
    ),
    (
        "Nuovo Principio Contabile OIC 34 sui Ricavi (2024) e Unita' Elementari di Contabilizzazione",
        "Il nuovo principio contabile nazionale OIC 34 (Ricavi), entrato in vigore per i bilanci degli esercizi "
        "aventi inizio dal 1 gennaio 2024, introduce un modello organico per la rilevazione e valorizzazione dei "
        "ricavi da vendita di beni e prestazione di servizi. Per i contratti complessi (a prestazioni multiple), "
        "l'OIC 34 impone di scomporre (segmentare) il contratto identificando le singole 'unita' elementari di "
        "contabilizzazione' (ciascun bene, servizio o diritto distinto promesso al cliente) e di allocare il prezzo "
        "complessivo del contratto a ciascuna unita' elementare in proporzione ai rispettivi prezzi di vendita "
        "autonomi (stand-alone). Il ricavo per la vendita di beni viene rilevato al trasferimento sostanziale dei "
        "rischi e dei benefici (oltre al trasferimento del titolo), mentre il ricavo per i servizi viene rilevato "
        "in base allo stato di avanzamento se il diritto al corrispettivo matura progressivamente. Le societa' che "
        "redigono il bilancio in forma abbreviata (art. 2435-bis c.c.) e le micro-imprese (art. 2435-ter c.c.) "
        "possono non separare le unita' elementari se i rischi e benefici sono trasferiti contestualmente.",
    ),
    (
        "Nuovi Limiti Bilancio Abbreviato (art. 2435-bis c.c.) e Micro-imprese (art. 2435-ter c.c.) D.Lgs. 125/2024",
        "Il D.Lgs. 6 settembre 2024, n. 125 (D.Lgs. 125/2024), recependo la Direttiva Delegata UE 2023/2775, "
        "ha aumentato del 25% i limiti dimensionali di stato patrimoniale e ricavi per i bilanci semplificati in Italia: "
        "1) Bilancio in forma abbreviata (art. 2435-bis c.c.): totale dell'attivo dello stato patrimoniale innalzato "
        "da 4.400.000 euro a 5.500.000 euro; ricavi delle vendite e delle prestazioni innalzati da 8.800.000 euro a "
        "11.000.000 euro; dipendenti occupati in media durante l'esercizio invariati a 50 unita' (richiesto il non "
        "superamento di almeno 2 dei 3 limiti nel primo esercizio o per 2 esercizi consecutivi). "
        "2) Bilancio delle micro-imprese (art. 2435-ter c.c.): totale dell'attivo dello stato patrimoniale innalzato "
        "da 175.000 euro a 220.000 euro; ricavi delle vendite e delle prestazioni innalzati da 350.000 euro a "
        "440.000 euro; dipendenti occupati in media durante l'esercizio invariati a 5 unita'.",
    ),
    (
        "Norma Internacional NIIF 16 (IFRS 16) Right-of-Use vs Metodo Patrimoniale Leasing Codice Civile Italiano",
        "Nella contabilizzazione del leasing (arrendamiento financiero) per il locatario/utilizzatore (arrendatario), "
        "la differenza fondamentale tra il principio internazionale NIIF 16 (IFRS 16) e il metodo patrimoniale del "
        "codice civile italiano (OIC 12 / art. 2427 n. 22 c.c.) risiede nella prevalenza della sostanza sulla forma: "
        "1) NIIF 16 / IFRS 16 (metodo finanziario unico / Right-of-Use model): elimina per il locatario la distinzione "
        "tra leasing operativo e finanziario e impone di iscrivere nello Stato Patrimoniale (Balance) l'attivo per "
        "diritto d'uso (Right-of-Use asset / activo por derecho de uso) nell'attivo e la corrispondente passivita' "
        "finanziaria per leasing (lease liability / pasivo por arrendamiento) al valore attuale dei canoni futuri "
        "nel passivo, rilevando a Conto Economico l'ammortamento del diritto d'uso e gli interessi passivi finanziari "
        "(con esenzione facoltativa per contratti di durata fino a 12 mesi o beni di modico valore fino a 5.000 USD). "
        "2) Metodo patrimoniale (codice civile italiano): il bene resta iscritto nell'attivo del bilancio della "
        "societa' di leasing concedente (locatore) che lo ammortizza, mentre l'impresa utilizzatrice (locatario) "
        "non iscrive il bene ne' il debito nello Stato Patrimoniale, ma rileva unicamente i canoni periodici di "
        "leasing a Conto Economico (voce B8 per godimento di beni di terzi, con risconto attivo per l'eventuale "
        "maxicanone iniziale) e fornisce nella Nota Integrativa (art. 2427 n. 22 c.c.) il prospetto degli effetti "
        "del metodo finanziario.",
    ),
    (
        "Impuesto sobre Sociedades en Espana 2026 (25%) y Reglamento Tecnico Verifactu Agencia Tributaria",
        "En Espana (Ley 27/2014 del Impuesto sobre Sociedades y reformas de la Ley 7/2024), el tipo de gravamen "
        "general vigente del Impuesto sobre Sociedades en 2026 es del 25% sobre la base imponible (con un tipo "
        "reducido del 15% para entidades de nueva creacion en el primer periodo impositivo con base positiva y en "
        "el siguiente, y tipos reducidos progresivos entre el 20% y el 24% para microempresas con cifra de negocios "
        "inferior a 1.000.000 euros y entidades de reducida dimension). "
        "El reglamento tecnico Verifactu (Real Decreto 1007/2023 y Orden HAC/1177/2024 de la Agencia Tributaria - AEAT, "
        "en desarrollo de la Ley Antifraude 11/2021) exige que los sistemas informaticos de facturacion (SIF) "
        "garanticen la integridad, conservacion, accesibilidad, legibilidad, trazabilidad e inalterabilidad de los "
        "registros de facturacion mediante: 1) generacion automatica de un registro de facturacion de alta o de "
        "anulacion con huella digital criptografica encadenada (hash SHA-256 vinculado al registro anterior) y "
        "firma electronica; 2) inclusion obligatoria de un codigo QR tributario verificable en cada factura; "
        "3) capacidad de remision electronica inmediata y continuada de los registros a la Agencia Tributaria "
        "(modalidad VERI*FACTU).",
    ),
    (
        "IFRS 18 Presentation and Disclosure in Financial Statements (Replacing IAS 1) Three Mandatory Categories",
        "Issued by the IASB in April 2024 (effective from 1 January 2027, replacing IAS 1), the new accounting "
        "standard IFRS 18 (Presentation and Disclosure in Financial Statements) introduces 3 (three) new mandatory "
        "categories for classifying income and expenses in the statement of profit or loss (income statement): "
        "1) Operating category: the default category capturing all income and expenses from the entity's main "
        "business activities that are not classified in the investing or financing categories; "
        "2) Investing category: income and expenses from investments in associates, joint ventures and unconsolidated "
        "subsidiaries, cash and cash equivalents, and other assets that generate a return individually and largely "
        "independently of the entity's other resources; "
        "3) Financing category: income and expenses from liabilities arising from transactions that involve only "
        "the raising of finance (such as bank loans and bonds) as well as interest expense and effects of changes "
        "in interest rates on other liabilities (such as lease liabilities and pension obligations). "
        "IFRS 18 also requires two new mandatory subtotals in the statement of profit or loss ('Operating profit "
        "or loss' and 'Profit or loss before financing and income taxes') and strict disclosures for "
        "Management-defined Performance Measures (MPMs).",
    ),
    (
        "EU Corporate Sustainability Reporting Directive (CSRD 2022/2464) & ESRS Double Materiality Principle",
        "Under the EU Corporate Sustainability Reporting Directive (CSRD, Directive EU 2022/2464) and the European "
        "Sustainability Reporting Standards (ESRS 1), companies must apply the principle of 'double materiality' "
        "(doppia materialita'), which requires assessing sustainability matters across 2 (two) dimensions: "
        "1) Impact materiality (inside-out perspective): a sustainability matter is material from an impact "
        "perspective if it pertains to the undertaking's actual or potential, positive or negative significant "
        "impacts on people or the environment over the short-, medium-, or long-term (including across its "
        "upstream and downstream value chain); "
        "2) Financial materiality (outside-in perspective): a sustainability matter is material from a financial "
        "perspective if it triggers or could reasonably be expected to trigger significant financial effects on "
        "the undertaking (risks and opportunities affecting cash flows, development, performance, position, cost "
        "of capital, or access to finance over the short-, medium-, or long-term). "
        "An undertaking must report on a sustainability topic if it is material from either the impact perspective, "
        "the financial perspective, or both.",
    ),
]

STOPWORDS_PRONTUARIO = {
    "normativa", "principio", "contabile", "contabili", "sistema", "sistemi",
    "azienda", "aziende", "impresa", "imprese", "secondo", "qual", "quale",
    "quali", "cosa", "come", "what", "which", "under", "cual", "como",
}


def cerca_nel_prontuario_locale(query: str) -> List[Tuple[str, str]]:
    """Checks the internal certified regulatory/technical handbook for exact keyword matches."""
    query_tradotta = traduci_query_per_ricerca(query)
    token_grezzi = re.findall(r"\d+(?:[.,/-]\d+)+|\w+", query_tradotta.lower())
    parole = {
        p for p in token_grezzi
        if (len(p) >= 4 or (len(p) >= 2 and p[0].isdigit())) and p not in STOPWORDS_PRONTUARIO
    }
    valutati: List[Tuple[int, str, str]] = []
    for sezione, testo in PRONTUARIO_ESTERNO_SOCCORSO:
        blocco_lower = f"{sezione} {testo}".lower()
        match_n = sum(2 if any(c.isdigit() for c in p) else 1 for p in parole if p in blocco_lower)
        if match_n >= 2 or (match_n == 1 and len(parole) <= 3):
            valutati.append((match_n, sezione, testo))
    valutati.sort(key=lambda item: item[0], reverse=True)
    return [(sez, txt) for _, sez, txt in valutati[:1]]


def cerca_nel_prontuario_esterno(
    query: str,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
) -> List[Tuple[str, str]]:
    chiave_attiva = (api_key or os.getenv("LLM_API_KEY") or config.LLM_API_KEY or "").strip()
    provider_attivo = (provider or os.getenv("LLM_PROVIDER") or config.LLM_PROVIDER or "ollama").strip().lower()

    if chiave_attiva and provider_attivo in ("gemini", "openrouter"):
        try:
            if provider_attivo == "gemini":
                url_gemini = (
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    f"gemini-2.5-flash:generateContent?key={chiave_attiva}"
                )
                payload_g = {
                    "contents": [
                        {
                            "parts": [
                                {
                                    "text": f"Search official technical facts and exact numbers for: {query}"
                                }
                            ]
                        }
                    ],
                    "tools": [{"google_search": {}}],
                }
                r_ai = requests.post(url_gemini, json=payload_g, timeout=15)
                r_ai.raise_for_status()
                parti = r_ai.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                testo_web = " ".join(p.get("text", "") for p in parti).strip()
                if testo_web:
                    return [(f"Web Search AI (Gemini Grounding): {query}", testo_web)]
            elif provider_attivo == "openrouter":
                url_or = "https://openrouter.ai/api/v1/chat/completions"
                r_or = requests.post(
                    url_or,
                    headers={"Authorization": f"Bearer {chiave_attiva}"},
                    json={
                        "model": "openrouter/free:online",
                        "messages": [
                            {
                                "role": "user",
                                "content": f"Report only verified technical facts and exact numbers from the web for: {query}",
                            }
                        ],
                    },
                    timeout=15,
                )
                r_or.raise_for_status()
                testo_or = r_or.json()["choices"][0]["message"]["content"].strip()
                if testo_or:
                    return [(f"Web Search AI (OpenRouter Online): {query}", testo_or)]
        except (requests.exceptions.RequestException, KeyError, IndexError, ValueError):
            pass

    trovati = cerca_nel_prontuario_locale(query)
    if trovati:
        return trovati

    try:
        url_ddg = "https://api.duckduckgo.com/"
        r_ddg = requests.get(
            url_ddg,
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            headers={"User-Agent": "Bottega/1.0"},
            timeout=10,
        )
        r_ddg.raise_for_status()
        dati_ddg = r_ddg.json()
        abstract_ddg = (dati_ddg.get("AbstractText") or "").strip()
        if abstract_ddg:
            tit_ddg = dati_ddg.get("Heading") or query
            trovati.append((f"API DuckDuckGo: {tit_ddg}", abstract_ddg))
    except (requests.exceptions.RequestException, ValueError, AttributeError):
        pass

    if trovati:
        return trovati

    lingua_wiki = rileva_lingua_testo(query)
    if lingua_wiki not in ("it", "en", "es"):
        lingua_wiki = "en"
    try:
        url_wiki = f"https://{lingua_wiki}.wikipedia.org/w/api.php"
        res = requests.get(
            url_wiki,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "utf8": 1,
                "format": "json",
                "srlimit": 2,
            },
            headers={"User-Agent": "Bottega/1.0"},
            timeout=10,
        )
        res.raise_for_status()
        risultati_api = res.json().get("query", {}).get("search", [])
        for item in risultati_api:
            titolo = item.get("title", "Fonte Web")
            estratto = re.sub(r"<[^>]+>", "", item.get("snippet", "")).strip()
            if estratto:
                trovati.append((f"API Wikipedia: {titolo}", estratto))
    except (requests.exceptions.RequestException, ValueError, AttributeError):
        pass

    if trovati:
        return trovati

    return [
        (
            f"Riferimento documentale per: {query[:80]}",
            f"Verificare i parametri e gli importi direttamente sui frammenti del documento caricato per: {query}",
        )
    ]


def esegui_seed() -> None:
    log.info("1/2 Inizializzazione schema PostgreSQL + pgvector...", extra={"code": "SEED_START_001"})
    inizializza_schema()

    log.info("2/2 Indicizzazione Corpus...", extra={"code": "SEED_ING_001"})
    totale_nuovi = 0
    for dominio, titolo, blocchi in CORPUS_INGEGNERIA:
        inseriti = incasella_e_salva(dominio, titolo, blocchi)
        totale_nuovi += inseriti
        log.info(
            "Dominio '%s': %d nuovi frammenti inseriti (su %d blocchi)",
            dominio,
            inseriti,
            len(blocchi),
            extra={"code": "SEED_DOM_001"},
        )

    log.info("Seed completato. Nuovi frammenti indicizzati: %d", totale_nuovi, extra={"code": "SEED_OK_001"})


if __name__ == "__main__":
    esegui_seed()
