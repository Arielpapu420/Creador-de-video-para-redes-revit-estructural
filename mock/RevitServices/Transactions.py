# -*- coding: utf-8 -*-
"""Simulación de RevitServices.Transactions.TransactionManager.

Imita la estrategia automática de Dynamo: EnsureInTransaction abre si no hay
transacción, TransactionTaskDone no confirma nada y ForceCloseTransaction
confirma y cierra. Así se detecta un ExportImage con la transacción abierta.
"""
import simulador


class _Gestor(object):
    def EnsureInTransaction(self, doc):
        simulador.estado.registro.append(("EnsureInTransaction",))
        doc._transaccion = True

    def TransactionTaskDone(self):
        simulador.estado.registro.append(("TransactionTaskDone",))

    def ForceCloseTransaction(self):
        simulador.estado.registro.append(("ForceCloseTransaction",))
        doc = simulador.estado.doc
        if doc is not None:
            doc._transaccion = False


class TransactionManager(object):
    Instance = _Gestor()
