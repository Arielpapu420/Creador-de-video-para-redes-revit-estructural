# -*- coding: utf-8 -*-
"""Simulación de System.Collections.Generic.List[T].

Como en pythonnet 2.5, la API de Revit no acepta listas de Python donde pide
ICollection<ElementId>: hay que construir List[ElementId]() y usar .Add().
"""


class ListaNet(object):
    def __init__(self, tipo):
        self.tipo = tipo
        self._items = []

    def Add(self, x):
        if not isinstance(x, self.tipo):
            raise TypeError("List[%s].Add recibió %s" % (self.tipo.__name__, type(x).__name__))
        self._items.append(x)

    @property
    def Count(self):
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)


class _FabricaLista(object):
    def __getitem__(self, tipo):
        def constructor(*args):
            if args:
                raise TypeError("El simulador exige List[T]() vacío y .Add() (patrón seguro en pythonnet 2.5)")
            return ListaNet(tipo)
        return constructor


List = _FabricaLista()
