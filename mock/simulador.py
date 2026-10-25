# -*- coding: utf-8 -*-
"""Estado del simulador y utilidades para ejecutar nodo_video.py como lo haría Dynamo.

Uso:
    import sys; sys.path.insert(0, "mock")
    import simulador, modelo_sintetico
    doc = modelo_sintetico.crear_documento()
    simulador.reiniciar(doc, exportador=simulador.exportador_rapido)
    ruta_informe = simulador.ejecutar_nodo("nodo_video.py", [carpeta, "{3D}", 15, 30, 180, False])
"""
import os


class CaidaDeRevit(BaseException):
    """Simula que Revit se cierra a media exportación (el nodo no puede atraparla)."""


class Estado(object):
    def __init__(self):
        self.doc = None
        self.registro = []              # llamadas relevantes en orden
        self.exportes = []              # un dict por imagen exportada
        self.modificaciones_modelo = []  # intentos de modificar/borrar elementos (debe quedar vacío)
        self.vistas_creadas = []
        self.ajustes_acero = []         # (id, vista, método, valor) de ajustes gráficos del acero
        self.piezas_creadas = 0         # DirectShape creadas por nodo_piezas.py
        self.fallos = {}                # {n_export: "error" | "caida"}
        self.contador_export = 0
        self.exportador = exportador_rapido
        self.escala = 0.125             # tamaño real del PNG simulado = escala * PixelSize


def reiniciar(doc, exportador=None, escala=None, fallos=None):
    """Prepara el estado para una corrida del nodo (conserva el documento que se pase)."""
    estado.doc = doc
    estado.registro = []
    estado.exportes = []
    estado.vistas_creadas = []
    estado.ajustes_acero = []
    estado.piezas_creadas = 0
    estado.fallos = dict(fallos or {})
    estado.contador_export = 0
    if exportador is not None:
        estado.exportador = exportador
    if escala is not None:
        estado.escala = escala


def ejecutar_nodo(ruta_nodo, entradas, devolver_espacio=False):
    """Ejecuta el código del nodo igual que Dynamo: variable global IN y lectura de OUT."""
    with open(ruta_nodo, encoding="utf-8") as f:
        codigo = f.read()
    espacio = {"IN": list(entradas), "__name__": "__dynamo_python_node__"}
    exec(compile(codigo, ruta_nodo, "exec"), espacio)
    if devolver_espacio:
        return espacio["OUT"], espacio
    return espacio["OUT"]


def exportador_rapido(doc, vista, ruta, ancho, alto):
    """Dibuja las cajas visibles con Pillow a escala reducida (rápido, para pruebas)."""
    import render
    render.dibujar_pillow(doc, vista, ruta, ancho, alto, estado.escala)


def exportador_matplotlib(doc, vista, ruta, ancho, alto):
    """Dibuja las cajas visibles con matplotlib (para la previa)."""
    import render
    render.dibujar_matplotlib(doc, vista, ruta, ancho, alto, estado.escala)


def exportador_vacio(doc, vista, ruta, ancho, alto):
    """Solo crea un PNG mínimo válido (lo más rápido)."""
    from PIL import Image
    Image.new("RGB", (max(1, int(ancho * estado.escala)), max(1, int(alto * estado.escala))),
              (255, 255, 255)).save(ruta)


def carpeta_mock():
    return os.path.dirname(os.path.abspath(__file__))


estado = Estado()
