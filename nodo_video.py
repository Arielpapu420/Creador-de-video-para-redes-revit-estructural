# -*- coding: utf-8 -*-
# =============================================================================
#  VIDEO DE OBRA - Nodo Python de Dynamo
#  Revit 2025 · Dynamo 3.x · motor CPython3 (pythonnet 2.5) · sin pyRevit
# =============================================================================
#  Exporta una secuencia de PNG donde el modelo estructural "se construye" por
#  etapas de obra mientras la cámara gira. Después, armar_video.py une los PNG
#  en un MP4 vertical 1080x1920.
#
#  Entradas del nodo:
#    IN[0]  Carpeta de salida (texto)
#    IN[1]  Nombre de la vista 3D base (texto, isométrica, NO perspectiva)
#    IN[2]  Cuadros por segundo de exportación (número, 15 por defecto)
#    IN[3]  Duración del video en segundos (número, 30 por defecto)
#    IN[4]  Grados de giro de la cámara (número, 180 por defecto)
#    IN[5]  Incluir acero de refuerzo (booleano, False por defecto)
#  Salida:
#    OUT    Ruta de informe_video.txt
#
#  Seguridad del modelo: el nodo NUNCA modifica ni borra elementos. Solo crea
#  (o reutiliza) la vista "VIDEO OBRA" y en ella oculta/muestra elementos,
#  cambia la orientación de la cámara y la caja de recorte.
#
#  Trampas de pythonnet en este entorno (respetadas en todo el código):
#    - XYZ no tiene operadores: se usa .Add() .Subtract() .Multiply() .CrossProduct()
#    - tipo.Name no se lee directo en los tipos: Element.Name.GetValue(tipo)
#      o el parámetro SYMBOL_NAME_PARAM
#    - Las unidades internas de Revit son pies
#    - Las colecciones .NET se arman con List[ElementId]() y .Add()
# =============================================================================

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitServices")

from System.Collections.Generic import List
from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, Category, Element, ElementId,
    ExportRange, FilteredElementCollector, FitDirectionType, ImageExportOptions,
    ImageFileType, ImageResolution, Level, View3D, ViewDuplicateOption,
    ViewOrientation3D, XYZ, ZoomFitType,
)
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

import bisect
import datetime
import json
import math
import os
import re
import time
import traceback

# =============================================================================
#  PARÁMETROS EDITABLES
# =============================================================================

NOMBRE_VISTA_VIDEO = "VIDEO OBRA"
PREFIJO_CUADRO = "frame_"          # frame_00001, frame_00002, ...
NOMBRE_INFORME = "informe_video.txt"
NOMBRE_GUION = "guion_video.json"  # lo lee armar_video.py para los rótulos

# Valores por defecto de las entradas (si llegan vacías)
CARPETA_DEFECTO = r"C:\VIDEO_OBRA\cuadros"
VISTA_BASE_DEFECTO = "{3D}"
FPS_DEFECTO = 15
DURACION_DEFECTO = 30.0
GRADOS_DEFECTO = 180.0

# Guion, como fracción de la duración (para 30 s: 1.5 s y 24 s)
FRACCION_INICIO_OBRA = 1.5 / 30.0  # antes: solo terreno
FRACCION_FIN_OBRA = 24.0 / 30.0    # después: estructura completa terminando el giro

# Cámara isométrica
ELEVACION_GRADOS = 30.0        # ángulo de la cámara sobre la horizontal
AZIMUT_INICIAL_GRADOS = -45.0  # dirección centro->ojo en planta (-45 = desde +X,-Y)
SUAVIZAR_GIRO = True           # arranque y final suaves (coseno)
RELACION_ASPECTO = 9.0 / 16.0  # ancho / alto del cuadro
MARGEN_ENCUADRE = 0.08         # 8 % de aire alrededor de la estructura
PIXELES_ALTO = 1920            # PixelSize con FitDirection Vertical

# Secuencia
BANDA_Z_PIES = 0.5                # dentro de una etapa, elementos en la misma banda de Z se barren en planta
DIRECCION_BARRIDO_GRADOS = 45.0   # dirección del barrido en planta (0 = de -X a +X)
TOLERANCIA_NIVEL_PIES = 0.1       # Z inferior + tolerancia >= elevación del nivel
TOLERANCIA_DESPLANTE_PIES = 1.0   # una viga es "de desplante" si su Z inferior <= nivel + esto
# Tiempo relativo por elemento (1.0 si la categoría no aparece). Una losa es un
# evento grande con pocos elementos: pesa más para que se alcance a ver.
PESOS_CATEGORIA = {"OST_Rebar": 0.25, "OST_Floors": 4.0, "OST_Stairs": 2.0}

# Exportación
MAX_ERRORES_SEGUIDOS = 5

# Categorías que se recogen para la secuencia (clave BuiltInCategory, nombre en Revit)
CATEGORIAS_OBRA = [
    ("OST_StructuralFoundation", "Cimentación estructural"),
    ("OST_StructuralColumns", "Pilares estructurales"),
    ("OST_StructuralFraming", "Armazón estructural"),
    ("OST_Walls", "Muros"),
    ("OST_Floors", "Suelos"),
    ("OST_Stairs", "Escaleras"),
]
CATEGORIA_ACERO = ("OST_Rebar", "Armadura estructural")

# Categorías que se ocultan siempre en la vista de video (solo ajuste de vista),
# para que nada fuera de la secuencia aparezca "construido" desde el inicio.
# Si no se incluye el acero, también se oculta OST_Rebar.
# Modelos genéricos y terreno NO se tocan: quedan visibles como base.
CATEGORIAS_OCULTAS_SIEMPRE = [
    "OST_Doors", "OST_Windows", "OST_Roofs", "OST_Ceilings", "OST_Railings", "OST_StairsRailing",
    "OST_Columns", "OST_CurtainWallPanels", "OST_CurtainWallMullions", "OST_StructConnections",
    "OST_AreaRein", "OST_PathRein", "OST_Furniture", "OST_Casework", "OST_PlumbingFixtures",
    "OST_LightingFixtures", "OST_SpecialityEquipment", "OST_Levels", "OST_Grids",
]

# -----------------------------------------------------------------------------
#  TABLA DE ETAPAS (orden de obra DENTRO de cada nivel)
# -----------------------------------------------------------------------------
#  Se evalúa de arriba abajo: la primera fila que cumple define la etapa del
#  elemento. La columna "orden" decide qué etapa aparece primero en el video.
#  Condiciones disponibles (ver CONDICIONES más abajo):
#    None         siempre cumple
#    "corrido"    cimiento corrido / losa de cimentación (no dado aislado)
#    "desplante"  viga en la Z más baja del nivel, cerca del nivel
#  Para cambiar la secuencia: mueve filas, cambia "orden" o agrega filas.
REGLAS_ETAPA = [
    # orden  etapa          categoría                    condición
    (10,     "cimentacion", "OST_StructuralFoundation",  "corrido"),
    (20,     "dados",       "OST_StructuralFoundation",  None),
    (30,     "desplante",   "OST_StructuralFraming",     "desplante"),
    (40,     "columnas",    "OST_StructuralColumns",     None),
    (50,     "muros",       "OST_Walls",                 None),
    (60,     "trabes",      "OST_StructuralFraming",     None),
    (70,     "losas",       "OST_Floors",                None),
    (80,     "escaleras",   "OST_Stairs",                None),
]
ETAPA_OTROS = (90, "otros")          # si ninguna fila cumple
ETAPA_ACERO_SUELTO = (35, "acero")   # varillas sin anfitrión recogido
# Las varillas con anfitrión aparecen justo antes de su anfitrión.

# Palabras clave en el nombre del TIPO (minúsculas, sin importar acentos)
PALABRAS_AISLADO = ("dado", "zapata aislada", "pila", "pilote", "candelero")
PALABRAS_CORRIDO = ("corrid", "cimiento", "losa de cimentacion", "contratrabe")


# =============================================================================
#  UTILIDADES
# =============================================================================

def _sin_acentos(texto):
    tabla = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n"}
    texto = (texto or "").lower()
    return "".join(tabla.get(c, c) for c in texto)


def id_entero(eid):
    """Entero de un ElementId (Revit 2024+ usa .Value; antes .IntegerValue)."""
    try:
        return int(eid.Value)
    except AttributeError:
        return int(eid.IntegerValue)


def lista_ids(ids):
    """Lista .NET List[ElementId] (pythonnet no convierte listas de Python)."""
    lista = List[ElementId]()
    for i in ids:
        lista.Add(i)
    return lista


def nombre_tipo(doc, elemento):
    """Nombre del tipo sin usar tipo.Name (no se lee directo en pythonnet)."""
    try:
        tipo = doc.GetElement(elemento.GetTypeId())
    except Exception:
        return ""
    if tipo is None:
        return ""
    try:
        nombre = Element.Name.GetValue(tipo)
        if nombre:
            return nombre
    except Exception:
        pass
    try:
        p = tipo.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if p is not None:
            return p.AsString() or ""
    except Exception:
        pass
    return ""


def nombre_clase(elemento):
    try:
        return elemento.GetType().Name
    except Exception:
        return type(elemento).__name__


def cerrar_transaccion():
    """Cierra la transacción de Dynamo para poder exportar fuera de ella."""
    TransactionManager.Instance.TransactionTaskDone()
    TransactionManager.Instance.ForceCloseTransaction()


def _entrada(entradas, i, defecto):
    try:
        v = entradas[i]
    except (IndexError, TypeError):
        return defecto
    if isinstance(v, (list, tuple)):
        v = v[0] if v else None
    if v is None or (isinstance(v, str) and not v.strip()):
        return defecto
    return v


def _a_bool(v):
    if isinstance(v, str):
        return v.strip().lower() in ("true", "si", "sí", "1", "verdadero")
    return bool(v)


# =============================================================================
#  ESTRUCTURAS
# =============================================================================

class Config(object):
    pass


class Pieza(object):
    """Un elemento del modelo dentro de la secuencia de obra."""

    def __init__(self, elemento, cat, etiqueta_cat, caja, clase, tipo, anfitrion):
        self.elemento = elemento
        self.eid = elemento.Id
        self.clave = id_entero(elemento.Id)
        self.cat = cat
        self.etiqueta_cat = etiqueta_cat
        self.xmin, self.ymin, self.zmin = caja[0]
        self.xmax, self.ymax, self.zmax = caja[1]
        self.cx = 0.5 * (self.xmin + self.xmax)
        self.cy = 0.5 * (self.ymin + self.ymax)
        self.clase = clase
        self.tipo = tipo
        self.anfitrion = anfitrion
        self.nivel = 0
        self.orden = 0
        self.etapa = ""
        self.peso = PESOS_CATEGORIA.get(cat, 1.0)
        self.clave_orden = None


class Cuadro(object):
    def __init__(self, n, t, fase, visibles, azimut):
        self.n = n
        self.t = t
        self.fase = fase
        self.visibles = visibles
        self.azimut = azimut
        self.etapa = None
        self.nivel = None


class Informe(object):
    def __init__(self):
        self.inicio = time.time()
        self.notas = []
        self.errores = []
        self.conteo = {}
        self.omitidos = []
        self.niveles = []
        self.parametros = []
        self.cuadros_total = 0
        self.exportados = 0
        self.saltados = 0
        self.fallidos = 0
        self.tiempos_export = []
        self.tiempos_cuadro = []

    def nota(self, texto):
        self.notas.append(texto)

    def error(self, donde, tb):
        self.errores.append((donde, tb))

    def escribir(self, ruta):
        L = []
        L.append("INFORME - VIDEO DE OBRA")
        L.append("Fecha: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        L.append("Duración del nodo: %.1f s" % (time.time() - self.inicio))
        L.append("")
        if self.parametros:
            L.append("PARÁMETROS")
            for k, v in self.parametros:
                L.append("  %-28s %s" % (k, v))
            L.append("")
        if self.niveles:
            L.append("NIVELES (elevación en m)")
            for i, (elev, nombre) in enumerate(self.niveles):
                L.append("  [%d] %-30s %8.2f" % (i, nombre, elev * 0.3048))
            L.append("")
        L.append("ELEMENTOS POR CATEGORÍA Y ETAPA (en orden de aparición)")
        if self.conteo:
            L.append("  %-5s %-22s %-14s %-26s %s" % ("Niv.", "Nombre nivel", "Etapa", "Categoría", "Cant."))
            total = 0
            for (niv, orden, etapa, cat), n in sorted(self.conteo.items()):
                nom = self.niveles[niv][1] if niv < len(self.niveles) else "?"
                L.append("  %-5d %-22s %-14s %-26s %d" % (niv, nom[:22], etapa, cat, n))
                total += n
            L.append("  Total en la secuencia: %d" % total)
        else:
            L.append("  (ninguno)")
        L.append("")
        if self.omitidos:
            L.append("ELEMENTOS OMITIDOS DE LA SECUENCIA")
            for t in self.omitidos:
                L.append("  " + t)
            L.append("")
        L.append("CUADROS")
        L.append("  Total del guion:            %d" % self.cuadros_total)
        L.append("  Exportados en esta corrida: %d" % self.exportados)
        L.append("  Ya existían (saltados):     %d" % self.saltados)
        L.append("  Con error:                  %d" % self.fallidos)
        faltan = self.cuadros_total - self.exportados - self.saltados
        L.append("  Faltan:                     %d" % max(0, faltan))
        L.append("")
        L.append("TIEMPO POR CUADRO")
        if self.tiempos_cuadro:
            tc, te = self.tiempos_cuadro, self.tiempos_export
            L.append("  Cuadro completo (vista + exportación): promedio %.2f s, mín %.2f s, máx %.2f s"
                     % (sum(tc) / len(tc), min(tc), max(tc)))
            L.append("  Solo ExportImage:                       promedio %.2f s, mín %.2f s, máx %.2f s"
                     % (sum(te) / len(te), min(te), max(te)))
            L.append("  Tiempo total de cuadros: %.1f min" % (sum(tc) / 60.0))
        else:
            L.append("  (no se exportó ningún cuadro en esta corrida)")
        L.append("")
        if self.notas:
            L.append("NOTAS")
            for t in self.notas:
                L.append("  - " + t)
            L.append("")
        L.append("ERRORES (%d)" % len(self.errores))
        if not self.errores:
            L.append("  Ninguno.")
        for donde, tb in self.errores:
            L.append("-" * 70)
            L.append("  " + donde)
            L.append(tb.rstrip())
        L.append("")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("\n".join(L))


# =============================================================================
#  LECTURA DEL MODELO
# =============================================================================

def leer_entradas(entradas):
    c = Config()
    c.carpeta = str(_entrada(entradas, 0, CARPETA_DEFECTO)).strip().strip('"')
    c.vista_base = str(_entrada(entradas, 1, VISTA_BASE_DEFECTO)).strip()
    c.fps = max(1, int(round(float(_entrada(entradas, 2, FPS_DEFECTO)))))
    c.duracion = float(_entrada(entradas, 3, DURACION_DEFECTO))
    c.grados = float(_entrada(entradas, 4, GRADOS_DEFECTO))
    c.acero = _a_bool(_entrada(entradas, 5, False))
    if c.duracion <= 0:
        raise ValueError("La duración debe ser mayor que cero.")
    return c


def buscar_vista_3d(doc, nombre):
    for v in FilteredElementCollector(doc).OfClass(View3D).ToElements():
        if v.IsTemplate:
            continue
        if v.Name == nombre:
            return v
    return None


def nombres_vistas_3d(doc):
    return sorted(v.Name for v in FilteredElementCollector(doc).OfClass(View3D).ToElements()
                  if not v.IsTemplate)


def leer_niveles(doc):
    niveles = []
    for nivel in FilteredElementCollector(doc).OfClass(Level).ToElements():
        try:
            elev = nivel.ProjectElevation
        except Exception:
            elev = nivel.Elevation
        niveles.append((float(elev), nivel.Name))
    niveles.sort(key=lambda x: x[0])
    if not niveles:
        niveles = [(0.0, "Sin nivel")]
    return niveles


def caja_de(elemento):
    bb = elemento.get_BoundingBox(None)
    if bb is None:
        return None
    mn, mx = bb.Min, bb.Max
    return (mn.X, mn.Y, mn.Z), (mx.X, mx.Y, mx.Z)


def anfitrion_de(elemento):
    try:
        hid = elemento.GetHostId()
    except Exception:
        return None
    if hid is None:
        return None
    k = id_entero(hid)
    return k if k > 0 else None


def recoger_piezas(doc, vista_base, incluir_acero, inf):
    categorias = list(CATEGORIAS_OBRA)
    if incluir_acero:
        categorias.append(CATEGORIA_ACERO)
    vistos = set()
    piezas = []
    for cat, etiqueta in categorias:
        bic = getattr(BuiltInCategory, cat)
        elementos = (FilteredElementCollector(doc, vista_base.Id)
                     .OfCategory(bic).WhereElementIsNotElementType().ToElements())
        for e in elementos:
            k = id_entero(e.Id)
            if k in vistos:
                continue
            vistos.add(k)
            try:
                if e.IsHidden(vista_base):
                    inf.omitidos.append("%d (%s): oculto en la vista base, se respeta" % (k, etiqueta))
                    continue
                caja = caja_de(e)
            except Exception:
                inf.error("Leyendo elemento %d" % k, traceback.format_exc())
                continue
            if caja is None:
                inf.omitidos.append("%d (%s): sin BoundingBox" % (k, etiqueta))
                continue
            anf = anfitrion_de(e) if cat == "OST_Rebar" else None
            piezas.append(Pieza(e, cat, etiqueta, caja, nombre_clase(e), nombre_tipo(doc, e), anf))
    return piezas


# =============================================================================
#  SECUENCIA DE OBRA
# =============================================================================

def nivel_de(z, niveles):
    """Índice del nivel más cercano por debajo de z (o el más bajo)."""
    idx = 0
    for i, (elev, _) in enumerate(niveles):
        if elev <= z + TOLERANCIA_NIVEL_PIES:
            idx = i
    return idx


def _es_corrido(p, ctx):
    t = _sin_acentos(p.tipo)
    if any(w in t for w in PALABRAS_AISLADO):
        return False
    if any(w in t for w in PALABRAS_CORRIDO):
        return True
    return p.clase in ("WallFoundation", "Floor")


def _es_desplante(p, ctx):
    zmin_nivel = ctx["min_armazon"].get(p.nivel)
    if zmin_nivel is None:
        return False
    elev = ctx["niveles"][p.nivel][0]
    return (p.zmin <= zmin_nivel + BANDA_Z_PIES and
            p.zmin <= elev + TOLERANCIA_DESPLANTE_PIES)


CONDICIONES = {
    None: lambda p, ctx: True,
    "corrido": _es_corrido,
    "desplante": _es_desplante,
}


def _clave_base(p):
    a = math.radians(DIRECCION_BARRIDO_GRADOS)
    barrido = p.cx * math.cos(a) + p.cy * math.sin(a)
    banda = int(math.floor(p.zmin / BANDA_Z_PIES + 1e-9))
    return (p.nivel, p.orden, banda, round(barrido, 3))


def ordenar_piezas(piezas, niveles, inf):
    for p in piezas:
        p.nivel = nivel_de(p.zmin, niveles)

    min_armazon = {}
    for p in piezas:
        if p.cat == "OST_StructuralFraming":
            actual = min_armazon.get(p.nivel)
            min_armazon[p.nivel] = p.zmin if actual is None else min(actual, p.zmin)
    ctx = {"niveles": niveles, "min_armazon": min_armazon}

    por_clave = {}
    for p in piezas:
        if p.cat == "OST_Rebar":
            continue
        p.orden, p.etapa = ETAPA_OTROS
        for orden, etapa, cat, cond in REGLAS_ETAPA:
            if cat == p.cat and CONDICIONES[cond](p, ctx):
                p.orden, p.etapa = orden, etapa
                break
        p.clave_orden = _clave_base(p) + (1, 0, 0.0, p.clave)
        por_clave[p.clave] = p

    for p in piezas:
        if p.cat != "OST_Rebar":
            continue
        anf = por_clave.get(p.anfitrion)
        if anf is not None:
            # La varilla aparece justo antes de su anfitrión
            p.nivel, p.orden, p.etapa = anf.nivel, anf.orden, anf.etapa
            propia = _clave_base(p)
            p.clave_orden = _clave_base(anf) + (0, propia[2], propia[3], p.clave)
        else:
            p.orden, p.etapa = ETAPA_ACERO_SUELTO
            p.clave_orden = _clave_base(p) + (1, 0, 0.0, p.clave)

    piezas.sort(key=lambda p: p.clave_orden)

    for p in piezas:
        k = (p.nivel, p.orden, p.etapa, p.etiqueta_cat)
        inf.conteo[k] = inf.conteo.get(k, 0) + 1
    return piezas


def construir_guion(piezas, cfg):
    n = int(round(cfg.duracion * cfg.fps))
    t_ini = FRACCION_INICIO_OBRA * cfg.duracion
    t_fin = FRACCION_FIN_OBRA * cfg.duracion
    acumulado = []
    suma = 0.0
    for p in piezas:
        suma += p.peso
        acumulado.append(suma)
    cuadros = []
    for i in range(n):
        t = i / float(cfg.fps)
        if t < t_ini:
            fase, visibles = "terreno", 0
        elif t >= t_fin or not piezas:
            fase, visibles = "final", len(piezas)
        else:
            avance = (t - t_ini) / (t_fin - t_ini)
            fase = "obra"
            visibles = bisect.bisect_right(acumulado, avance * suma + 1e-9)
        u = i / float(n - 1) if n > 1 else 1.0
        if SUAVIZAR_GIRO:
            u = 0.5 - 0.5 * math.cos(math.pi * u)
        c = Cuadro(i + 1, t, fase, visibles, AZIMUT_INICIAL_GRADOS + cfg.grados * u)
        if visibles > 0:
            ultima = piezas[visibles - 1]
            c.etapa, c.nivel = ultima.etapa, ultima.nivel
        cuadros.append(c)
    return cuadros


# =============================================================================
#  CÁMARA
# =============================================================================

def _vectores(az_grados, el_grados):
    """Vectores de cámara en flotantes: (centro->ojo, adelante, derecha, arriba)."""
    az, el = math.radians(az_grados), math.radians(el_grados)
    d = (math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))
    f = (-d[0], -d[1], -d[2])
    r = (f[1], -f[0], 0.0)  # f x Z
    lr = math.sqrt(r[0] ** 2 + r[1] ** 2)
    r = (r[0] / lr, r[1] / lr, 0.0)
    u = (r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0])
    return d, f, r, u


def orientacion_camara(centro, az_grados, distancia):
    """ViewOrientation3D isométrica mirando al centro (solo métodos de XYZ)."""
    az, el = math.radians(az_grados), math.radians(ELEVACION_GRADOS)
    d = XYZ(math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))
    ojo = centro.Add(d.Multiply(distancia))
    adelante = centro.Subtract(ojo).Normalize()
    derecha = adelante.CrossProduct(XYZ.BasisZ).Normalize()
    arriba = derecha.CrossProduct(adelante).Normalize()
    return ViewOrientation3D(ojo, arriba, adelante)


def calcular_encuadre(piezas, cuadros):
    """Centro, semiancho y semialto constantes para todo el giro (9:16 con margen)."""
    xmin = min(p.xmin for p in piezas)
    ymin = min(p.ymin for p in piezas)
    zmin = min(p.zmin for p in piezas)
    xmax = max(p.xmax for p in piezas)
    ymax = max(p.ymax for p in piezas)
    zmax = max(p.zmax for p in piezas)
    c = (0.5 * (xmin + xmax), 0.5 * (ymin + ymax), 0.5 * (zmin + zmax))
    esquinas = [(x, y, z) for x in (xmin, xmax) for y in (ymin, ymax) for z in (zmin, zmax)]
    sw = sh = 1e-6
    for az in sorted(set(round(q.azimut, 3) for q in cuadros)):
        _, _, r, u = _vectores(az, ELEVACION_GRADOS)
        for e in esquinas:
            rel = (e[0] - c[0], e[1] - c[1], e[2] - c[2])
            sw = max(sw, abs(rel[0] * r[0] + rel[1] * r[1] + rel[2] * r[2]))
            sh = max(sh, abs(rel[0] * u[0] + rel[1] * u[1] + rel[2] * u[2]))
    sw *= 1.0 + MARGEN_ENCUADRE
    sh *= 1.0 + MARGEN_ENCUADRE
    if sw / sh > RELACION_ASPECTO:
        sh = sw / RELACION_ASPECTO
    else:
        sw = sh * RELACION_ASPECTO
    diagonal = math.sqrt((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2)
    return c, sw, sh, diagonal


def ajustar_recorte(vista, centro, semi_ancho, semi_alto, profundidad):
    """Caja de recorte centrada en el centro de la estructura, en coordenadas de vista."""
    cb = vista.CropBox
    c = cb.Transform.Inverse.OfPoint(centro)
    cb.Min = XYZ(c.X - semi_ancho, c.Y - semi_alto, c.Z - profundidad)
    cb.Max = XYZ(c.X + semi_ancho, c.Y + semi_alto, c.Z + profundidad)
    vista.CropBox = cb


# =============================================================================
#  VISTA Y EXPORTACIÓN
# =============================================================================

def _fijar_categoria(doc, vista, nombre, oculta, inf):
    try:
        cat = Category.GetCategory(doc, getattr(BuiltInCategory, nombre))
        if cat is not None:
            vista.SetCategoryHidden(cat.Id, oculta)
            return True
    except Exception:
        inf.nota("No se pudo %s la categoría %s (¿plantilla de vista?)."
                 % ("ocultar" if oculta else "mostrar", nombre))
    return False


def preparar_vista(doc, vista_base, piezas, incluir_acero, inf):
    """Crea o reutiliza VIDEO OBRA y deja ocultas todas las piezas de la secuencia."""
    vista = buscar_vista_3d(doc, NOMBRE_VISTA_VIDEO)
    TransactionManager.Instance.EnsureInTransaction(doc)
    try:
        if vista is None:
            nueva_id = vista_base.Duplicate(ViewDuplicateOption.Duplicate)
            vista = doc.GetElement(nueva_id)
            vista.Name = NOMBRE_VISTA_VIDEO
            inf.nota("Vista '%s' creada como duplicado de '%s'." % (NOMBRE_VISTA_VIDEO, vista_base.Name))
        else:
            inf.nota("Vista '%s' ya existía: se reutiliza." % NOMBRE_VISTA_VIDEO)
        if vista.IsPerspective:
            raise ValueError("La vista '%s' está en perspectiva; bórrala y usa una vista base isométrica."
                             % NOMBRE_VISTA_VIDEO)
        if vista.IsLocked:
            vista.Unlock()
        try:
            if vista.IsSectionBoxActive:
                inf.nota("La vista tiene caja de sección activa: puede recortar el modelo.")
        except Exception:
            pass
        vista.CropBoxActive = True
        vista.CropBoxVisible = False

        ocultas = list(CATEGORIAS_OCULTAS_SIEMPRE)
        if incluir_acero:
            _fijar_categoria(doc, vista, CATEGORIA_ACERO[0], False, inf)  # por si una corrida previa la ocultó
        else:
            ocultas.append(CATEGORIA_ACERO[0])
        hechas = [n for n in ocultas if _fijar_categoria(doc, vista, n, True, inf)]
        inf.nota("Categorías ocultas en la vista de video: %s" % (", ".join(hechas) or "ninguna"))

        ocultables = []
        for p in piezas:
            if p.elemento.CanBeHidden(vista):
                ocultables.append(p)
            else:
                inf.omitidos.append("%d (%s): no se puede ocultar, queda siempre visible"
                                    % (p.clave, p.etiqueta_cat))
        a_ocultar = [p.eid for p in ocultables if not p.elemento.IsHidden(vista)]
        if a_ocultar:
            vista.HideElements(lista_ids(a_ocultar))
        doc.Regenerate()
    finally:
        cerrar_transaccion()
    return vista, ocultables


def opciones_exportacion(vista):
    op = ImageExportOptions()
    op.ExportRange = ExportRange.SetOfViews
    op.SetViewsAndSheets(lista_ids([vista.Id]))
    op.HLRandWFViewsFileType = ImageFileType.PNG
    op.ShadowViewsFileType = ImageFileType.PNG
    op.ImageResolution = ImageResolution.DPI_150
    op.ZoomType = ZoomFitType.FitToPage
    op.FitDirection = FitDirectionType.Vertical
    op.PixelSize = PIXELES_ALTO
    return op


_PATRON_CUADRO = re.compile(r"^" + re.escape(PREFIJO_CUADRO) + r"(\d{5})(?:\D.*)?\.png$", re.IGNORECASE)


def cuadros_existentes(carpeta):
    """Números de cuadro ya exportados (Revit agrega el nombre de la vista al archivo)."""
    hechos = set()
    for nombre in os.listdir(carpeta):
        m = _PATRON_CUADRO.match(nombre)
        if m and os.path.getsize(os.path.join(carpeta, nombre)) > 0:
            hechos.add(int(m.group(1)))
    return hechos


def escribir_guion(ruta, cfg, niveles, piezas, cuadros):
    datos = {
        "version": 1,
        "fps": cfg.fps,
        "duracion": cfg.duracion,
        "grados": cfg.grados,
        "cuadros_total": len(cuadros),
        "prefijo": PREFIJO_CUADRO,
        "niveles": [{"indice": i, "nombre": n, "elevacion_m": round(e * 0.3048, 3)}
                    for i, (e, n) in enumerate(niveles)],
        "piezas": len(piezas),
        "cuadros": [{"n": c.n, "t": round(c.t, 4), "fase": c.fase, "visibles": c.visibles,
                     "etapa": c.etapa, "nivel": c.nivel, "azimut": round(c.azimut, 4)}
                    for c in cuadros],
    }
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)


def exportar(doc, vista, piezas, cuadros, cfg, inf):
    centro_f, semi_ancho, semi_alto, diagonal = calcular_encuadre(piezas, cuadros)
    centro = XYZ(centro_f[0], centro_f[1], centro_f[2])
    distancia = 2.0 * diagonal + 10.0
    op = opciones_exportacion(vista)
    existentes = cuadros_existentes(cfg.carpeta)
    inf.parametros.append(("Encuadre (m)", "%.2f x %.2f" % (2 * semi_ancho * 0.3048, 2 * semi_alto * 0.3048)))

    visibles = 0  # tras preparar_vista, todas las piezas están ocultas
    seguidos = 0
    for c in cuadros:
        if c.n in existentes:
            inf.saltados += 1
            continue
        t0 = time.time()
        try:
            TransactionManager.Instance.EnsureInTransaction(doc)
            try:
                if c.visibles > visibles:
                    vista.UnhideElements(lista_ids([p.eid for p in piezas[visibles:c.visibles]]))
                    visibles = c.visibles
                vista.SetOrientation(orientacion_camara(centro, c.azimut, distancia))
                doc.Regenerate()
                ajustar_recorte(vista, centro, semi_ancho, semi_alto, diagonal)
                doc.Regenerate()
            finally:
                cerrar_transaccion()
            op.FilePath = os.path.join(cfg.carpeta, "%s%05d" % (PREFIJO_CUADRO, c.n))
            t1 = time.time()
            doc.ExportImage(op)
            inf.tiempos_export.append(time.time() - t1)
            inf.tiempos_cuadro.append(time.time() - t0)
            inf.exportados += 1
            seguidos = 0
        except Exception:
            inf.fallidos += 1
            seguidos += 1
            inf.error("Cuadro %d (t = %.2f s)" % (c.n, c.t), traceback.format_exc())
            if seguidos >= MAX_ERRORES_SEGUIDOS:
                inf.nota("Se detuvo tras %d errores seguidos. Corrige y vuelve a ejecutar: "
                         "los cuadros hechos se saltan." % seguidos)
                break


# =============================================================================
#  PRINCIPAL
# =============================================================================

def ejecutar(entradas):
    inf = Informe()
    carpeta = CARPETA_DEFECTO
    try:
        cfg = leer_entradas(entradas)
        carpeta = cfg.carpeta
        if not os.path.isdir(carpeta):
            os.makedirs(carpeta)
        inf.parametros += [
            ("Carpeta de salida", cfg.carpeta),
            ("Vista base", cfg.vista_base),
            ("FPS de exportación", cfg.fps),
            ("Duración (s)", cfg.duracion),
            ("Grados de giro", cfg.grados),
            ("Incluir acero", "sí" if cfg.acero else "no"),
        ]
        doc = DocumentManager.Instance.CurrentDBDocument
        if cfg.vista_base == NOMBRE_VISTA_VIDEO:
            raise ValueError("La vista base no puede llamarse '%s'." % NOMBRE_VISTA_VIDEO)
        vista_base = buscar_vista_3d(doc, cfg.vista_base)
        if vista_base is None:
            raise ValueError("No existe la vista 3D '%s'. Vistas 3D disponibles: %s"
                             % (cfg.vista_base, ", ".join(nombres_vistas_3d(doc))))
        if vista_base.IsPerspective:
            raise ValueError("La vista '%s' está en perspectiva. Usa una vista 3D isométrica."
                             % cfg.vista_base)

        niveles = leer_niveles(doc)
        inf.niveles = niveles
        piezas = recoger_piezas(doc, vista_base, cfg.acero, inf)
        if not piezas:
            raise ValueError("No se encontraron elementos estructurales visibles en la vista base.")
        vista, piezas = preparar_vista(doc, vista_base, piezas, cfg.acero, inf)
        piezas = ordenar_piezas(piezas, niveles, inf)
        cuadros = construir_guion(piezas, cfg)
        inf.cuadros_total = len(cuadros)
        escribir_guion(os.path.join(carpeta, NOMBRE_GUION), cfg, niveles, piezas, cuadros)
        exportar(doc, vista, piezas, cuadros, cfg, inf)
    except Exception:
        inf.error("Error general", traceback.format_exc())
        try:
            TransactionManager.Instance.ForceCloseTransaction()
        except Exception:
            pass
    finally:
        if not os.path.isdir(carpeta):
            try:
                os.makedirs(carpeta)
            except Exception:
                carpeta = os.path.expanduser("~")
        ruta = os.path.join(carpeta, NOMBRE_INFORME)
        inf.escribir(ruta)
    return ruta


OUT = ejecutar(IN)
