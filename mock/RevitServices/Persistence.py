# -*- coding: utf-8 -*-
"""Simulación de RevitServices.Persistence.DocumentManager."""
import simulador


class _Gestor(object):
    @property
    def CurrentDBDocument(self):
        return simulador.estado.doc


class DocumentManager(object):
    Instance = _Gestor()
