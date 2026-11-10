#!/usr/bin/env python3
"""Layer 1 (THE): Concurrency guard with Banker's Algorithm (EWD116),
P/V Semaphore (EWD123) and active domain reference counter (Holyness Counter, EWD113)."""

from contextlib import contextmanager
import threading
from typing import Dict, List

from config import CAPITALE_SLOT_CONCORRENTI
from logging_bottega import log


def verifica_stato_sicuro_banchiere(
    capitale_totale: int,
    prestiti_attuali: List[int],
    fabbisogni_massimi: List[int],
) -> bool:
    """EWD116 / EWD123-77 (Banker's Algorithm): Verifies a priori whether resource allocation
    is in a Safe State, mathematically preventing Deadlock."""
    if len(prestiti_attuali) != len(fabbisogni_massimi):
        raise ValueError("Le liste prestiti_attuali e fabbisogni_massimi devono avere uguale lunghezza.")
    if capitale_totale < 0:
        raise ValueError("Il capitale totale non puo' essere negativo.")

    numero_processi = len(prestiti_attuali)
    for indice in range(numero_processi):
        if prestiti_attuali[indice] < 0 or fabbisogni_massimi[indice] < 0:
            return False
        if prestiti_attuali[indice] > fabbisogni_massimi[indice]:
            return False

    somma_prestiti = sum(prestiti_attuali)
    if somma_prestiti > capitale_totale:
        return False

    free_money = capitale_totale - somma_prestiti
    claims = [fabbisogni_massimi[idx] - prestiti_attuali[idx] for idx in range(numero_processi)]
    finish_doubtful = [True] * numero_processi

    progresso = True
    passi_residui = numero_processi + 1
    while progresso and passi_residui > 0:
        passi_residui -= 1
        progresso = False
        for idx in range(numero_processi):
            if finish_doubtful[idx] and claims[idx] <= free_money:
                finish_doubtful[idx] = False
                free_money += prestiti_attuali[idx]
                progresso = True

    return not any(finish_doubtful) and free_money == capitale_totale


class PresidioConcorrenzaTHE:
    """EWD310 (Secretary) + EWD123 (P/V Semaphores) + EWD113 (Holyness Counter)."""

    def __init__(self, capitale_slot: int = CAPITALE_SLOT_CONCORRENTI) -> None:
        self._capitale = capitale_slot
        self._semaforo_pv = threading.BoundedSemaphore(value=capitale_slot)
        self._mutex_segretario = threading.Lock()
        self._holyness_counter: Dict[str, int] = {}
        self._prestiti_thread: Dict[int, int] = {}
        self._fabbisogni_thread: Dict[int, int] = {}

    def holyness_di(self, dominio: str) -> int:
        """Returns the number of currently active operations on the domain (EWD113)."""
        with self._mutex_segretario:
            return self._holyness_counter.get(dominio, 0)

    def puo_essere_vittima(self, dominio: str) -> bool:
        """EWD113 Cap. 4.2: Forbids evicting or overwriting a domain while Holyness > 0."""
        return self.holyness_di(dominio) == 0

    @contextmanager
    def sezione_sacra(self, dominio: str, fabbisogno_massimo: int = 1):
        """Acquires a P/V slot, verifies Safe State via the Banker's Algorithm (EWD116),
        increments the Holyness Counter (EWD113) and deterministically releases in finally."""
        if fabbisogno_massimo < 1:
            raise ValueError("Il fabbisogno_massimo deve essere >= 1.")

        identificativo_thread = threading.get_ident()
        self._semaforo_pv.acquire()
        allocato = False
        try:
            with self._mutex_segretario:
                prestito_corrente = self._prestiti_thread.get(identificativo_thread, 0) + 1
                need_corrente = max(
                    self._fabbisogni_thread.get(identificativo_thread, 0),
                    prestito_corrente,
                    fabbisogno_massimo,
                )
                self._prestiti_thread[identificativo_thread] = prestito_corrente
                self._fabbisogni_thread[identificativo_thread] = need_corrente

                identificativi_attivi = list(self._prestiti_thread.keys())
                lista_prestiti = [self._prestiti_thread[ident] for ident in identificativi_attivi]
                lista_needs = [self._fabbisogni_thread[ident] for ident in identificativi_attivi]

                if not verifica_stato_sicuro_banchiere(self._capitale, lista_prestiti, lista_needs):
                    if prestito_corrente <= 1:
                        self._prestiti_thread.pop(identificativo_thread, None)
                        self._fabbisogni_thread.pop(identificativo_thread, None)
                    else:
                        self._prestiti_thread[identificativo_thread] = prestito_corrente - 1
                    raise RuntimeError(
                        f"Violazione EWD116: Stato Insicuro rilevato per dominio '{dominio}'."
                    )

                self._holyness_counter[dominio] = self._holyness_counter.get(dominio, 0) + 1
                allocato = True
            yield
        finally:
            if allocato:
                profanato = False
                with self._mutex_segretario:
                    nuovo_val = self._holyness_counter.get(dominio, 1) - 1
                    self._holyness_counter[dominio] = max(0, nuovo_val)
                    profanato = self._holyness_counter[dominio] == 0
                    residuo = self._prestiti_thread.get(identificativo_thread, 1) - 1
                    if residuo <= 0:
                        self._prestiti_thread.pop(identificativo_thread, None)
                        self._fabbisogni_thread.pop(identificativo_thread, None)
                    else:
                        self._prestiti_thread[identificativo_thread] = residuo
                if profanato:
                    log.debug("Segmento '%s' profanato (Holyness=0)", dominio, extra={"code": "THE_HOLY_000"})
            self._semaforo_pv.release()


SEGRETARIO_THE = PresidioConcorrenzaTHE()
