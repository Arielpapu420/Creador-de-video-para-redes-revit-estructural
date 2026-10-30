# -*- coding: utf-8 -*-
# =============================================================================
#  PIEZAS DE OBRA - Nodo Python de Dynamo (crear blocks y piedras para el video)
#  Revit 2025 · Dynamo 3.x · motor CPython3 (pythonnet 2.5) · sin pyRevit
# =============================================================================
#  En Revit un muro es un solo sólido. Para que el video muestre cómo se colocan
#  los blocks y las piedras, este nodo crea cada pieza como DirectShape
#  (Modelo genérico) marcada con ApplicationId = "VIDEO_OBRA". Después,
#  nodo_video.py oculta el muro original y coloca las piezas hilada por hilada.
#
#  SEGURIDAD: solo corre si el nombre del archivo contiene "VIDEO" (por ejemplo,
#  MODELO_VIDEO.rvt). Trabaja SIEMPRE sobre una copia del modelo. No modifica
#  ni borra elementos existentes: solo crea (o borra) sus propias piezas.
#
#  Entradas del nodo:
#    IN[0]  Largo del block en cm (40)
#    IN[1]  Alto del block en cm (20)
#    IN[2]  Espesor del block en cm (12)
#    IN[3]  Junta de mortero en cm (1)
#    IN[4]  Generar piedras en cimientos de mampostería (True)
#    IN[5]  Solo borrar las piezas creadas antes (False)
#  Salida:
#    OUT    Resumen en texto (piezas por muro, muros omitidos, errores)
#
#  Las medidas del block son nominales (con junta): un block 12x20x40 con junta
#  de 1 cm se dibuja de 39 x 19 cm y ocupa un módulo de 40 x 20 cm.
# =============================================================================

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitServices")

from System.Collections.Generic import List
from Autodesk.Revit.DB import (
    BuiltInCategory, CurveLoop, DirectShape, Element, ElementId, FilteredElementCollector,
    GeometryCreationUtilities, GeometryObject, Line, SolidOptions, XYZ,
)
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

import math
import random
import time
import traceback

# =============================================================================
#  PARÁMETROS EDITABLES
# =============================================================================

APLICACION = "VIDEO_OBRA"          # marca de las piezas (la lee nodo_video.py)
NOMBRE_REQUERIDO = "VIDEO"         # el archivo debe llamarse así (seguridad)

# Muros que se convierten (palabras en tipo, familia o material; sin acentos)
PALABRAS_BLOCK = ("block", "bloque", "tabique", "tabicon", "ladrillo")
PALABRAS_PIEDRA = ("piedra", "roca", "mamposter", "braza")
PALABRAS_EXCLUIR = ("concreto armado", "cisterna", "muro de concreto")

# Obstáculos que cortan las hiladas (castillos, dalas, cerramientos, vanos)
CATEGORIAS_OBSTACULO = ["OST_StructuralColumns", "OST_StructuralFraming", "OST_Doors", "OST_Windows"]

# Piedra braza (metros)
PIEDRA_ALTO = (0.20, 0.30)         # alto de hilada (mín, máx)
PIEDRA_LARGO = (0.25, 0.45)
PIEDRA_JUNTA = 0.025
PIEDRAS_A_LO_ANCHO = 2             # piedras en el espesor del cimiento
MORTERO_RETIRO = 0.03              # la cama de mortero queda 3 cm adentro de la cara
MORTERO_ALTO = 0.6                 # y llega al 60 % de la hilada: las piedras sobresalen

PIEZA_MINIMA = 0.05                # trozos más cortos no se dibujan (m)
SEMILLA = 7                        # misma semilla = mismas piedras en cada corrida


# =============================================================================
#  UTILIDADES
# =============================================================================

M = 1.0 / 0.3048  # metros -> pies


def _sin_acentos(texto):
    tabla = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n"}
    return "".join(tabla.get(c, c) for c in (texto or "").lower())


def id_entero(eid):
    try:
        return int(eid.Value)
    except AttributeError:
        return int(eid.IntegerValue)


def lista_net(tipo, items):
    lista = List[tipo]()
    for i in items:
        lista.Add(i)
    return lista


def nombre_elemento(e):
    try:
        return Element.Name.GetValue(e) or ""
    except Exception:
        try:
            return e.Name or ""
        except Exception:
            return ""


def texto_de(doc, e):
    """Tipo + familia + materiales, para buscar palabras clave."""
    partes = []
    try:
        tipo = doc.GetElement(e.GetTypeId())
        if tipo is not None:
            partes.append(nombre_elemento(tipo))
            try:
                partes.append(tipo.FamilyName or "")
            except Exception:
                pass
    except Exception:
        pass
    try:
        for mid in e.GetMaterialIds(False):
            m = doc.GetElement(mid)
            if m is not None:
                partes.append(nombre_elemento(m))
    except Exception:
        pass
    return _sin_acentos(" | ".join(partes))


def material_de(e):
    try:
        for mid in e.GetMaterialIds(False):
            return mid
    except Exception:
        pass
    return ElementId.InvalidElementId


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


def cerrar_transaccion():
    TransactionManager.Instance.TransactionTaskDone()
    TransactionManager.Instance.ForceCloseTransaction()


# =============================================================================
#  GEOMETRÍA DEL MURO (coordenadas locales: s a lo largo, t a lo ancho, z)
# =============================================================================

class Marco(object):
    """Eje del muro en planta: origen, dirección u y normal v (flotantes, en pies)."""

    def __init__(self, p0, p1):
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        self.largo = math.sqrt(dx * dx + dy * dy)
        self.ox, self.oy = p0[0], p0[1]
        self.ux, self.uy = dx / self.largo, dy / self.largo
        self.vx, self.vy = -self.uy, self.ux

    def a_local(self, x, y):
        rx, ry = x - self.ox, y - self.oy
        return rx * self.ux + ry * self.uy, rx * self.vx + ry * self.vy

    def a_mundo(self, s, t, z):
        return XYZ(self.ox + self.ux * s + self.vx * t, self.oy + self.uy * s + self.vy * t, z)


def eje_del_muro(muro):
    """Extremos del eje (LocationCurve recta) o None si el muro es curvo."""
    try:
        curva = muro.Location.Curve
        if curva.GetType().Name != "Line":
            return None
        a, b = curva.GetEndPoint(0), curva.GetEndPoint(1)
        return (a.X, a.Y), (b.X, b.Y)
    except Exception:
        return None


def obstaculos_del_muro(marco, ancho, cajas):
    """Intervalos (s0, s1, z0, z1) de obstáculos que cruzan la franja del muro."""
    res = []
    tol = 0.01 * M
    for (x0, y0, z0), (x1, y1, z1) in cajas:
        ss, ts = [], []
        for x in (x0, x1):
            for y in (y0, y1):
                s, t = marco.a_local(x, y)
                ss.append(s)
                ts.append(t)
        if max(ts) <= -ancho / 2 + tol or min(ts) >= ancho / 2 - tol:
            continue
        if max(ss) <= tol or min(ss) >= marco.largo - tol:
            continue
        res.append((min(ss), max(ss), z0, z1))
    return res


def tramos_libres(largo, bloqueos):
    """[0, largo] menos los intervalos bloqueados."""
    libres = [(0.0, largo)]
    for b0, b1 in sorted(bloqueos):
        nuevos = []
        for a0, a1 in libres:
            if b1 <= a0 or b0 >= a1:
                nuevos.append((a0, a1))
            else:
                if b0 > a0:
                    nuevos.append((a0, b0))
                if b1 < a1:
                    nuevos.append((b1, a1))
        libres = nuevos
    return libres


def caja_solida(marco, s0, s1, t0, t1, z0, z1, material):
    """Prisma rectangular alineado al muro, como Solid de Revit."""
    lazo = CurveLoop()
    pts = [marco.a_mundo(s0, t0, z0), marco.a_mundo(s1, t0, z0),
           marco.a_mundo(s1, t1, z0), marco.a_mundo(s0, t1, z0)]
    for i in range(4):
        lazo.Append(Line.CreateBound(pts[i], pts[(i + 1) % 4]))
    opciones = SolidOptions(material, ElementId.InvalidElementId)
    return GeometryCreationUtilities.CreateExtrusionGeometry(
        lista_net(CurveLoop, [lazo]), XYZ.BasisZ, z1 - z0, opciones)


# =============================================================================
#  GENERADORES
# =============================================================================

def piezas_block(marco, ancho_muro, z_base, z_tope, obst, cfg):
    """Blocks cuatrapeados: lista de (tipo, hilada, s0, s1, t0, t1, z0, z1)."""
    res = []
    mod_l, mod_h, junta = cfg.largo, cfg.alto, cfg.junta
    espesor = min(cfg.espesor, ancho_muro)
    t0, t1 = -espesor / 2.0, espesor / 2.0
    minimo = PIEZA_MINIMA * M
    hilada, z = 0, z_base
    while z_tope - z > minimo:
        z1 = min(z + mod_h, z_tope)
        zc0, zc1 = z, z1 - junta
        if zc1 - zc0 < minimo:
            break
        bloqueos = [(b0, b1) for b0, b1, o0, o1 in obst if o0 < zc1 - 1e-6 and o1 > zc0 + 1e-6]
        for a0, a1 in tramos_libres(marco.largo, bloqueos):
            s = a0 - (mod_l / 2.0 if hilada % 2 else 0.0)  # cuatrapeado
            while s < a1 - 1e-9:
                p0, p1 = max(s, a0), min(s + mod_l - junta, a1)
                if p1 - p0 >= minimo:
                    res.append(("block", hilada, p0, p1, t0, t1, zc0, zc1))
                s += mod_l
        hilada += 1
        z = z1
    return res


def piezas_piedra(marco, ancho_muro, z_base, z_tope, obst, rng):
    """Piedras irregulares por hilada, con cama de mortero."""
    res = []
    junta = PIEDRA_JUNTA * M
    minimo = PIEZA_MINIMA * M
    hilada, z = 0, z_base
    while z_tope - z > minimo:
        h = rng.uniform(*PIEDRA_ALTO) * M
        z1 = z_tope if z_tope - (z + h) < PIEDRA_ALTO[0] * M * 0.5 else z + h
        bloqueos = [(b0, b1) for b0, b1, o0, o1 in obst if o0 < z1 and o1 > z]
        retiro = MORTERO_RETIRO * M
        for a0, a1 in tramos_libres(marco.largo, bloqueos):
            if a1 - a0 < minimo:
                continue
            res.append(("mortero", hilada, a0 + retiro, a1 - retiro, -ancho_muro / 2.0 + retiro,
                        ancho_muro / 2.0 - retiro, z, z + MORTERO_ALTO * (z1 - z)))
            # Divisiones a lo ancho (cada hilada distinta)
            cortes = [-ancho_muro / 2.0]
            for k in range(1, PIEDRAS_A_LO_ANCHO):
                base = -ancho_muro / 2.0 + ancho_muro * k / PIEDRAS_A_LO_ANCHO
                cortes.append(base + rng.uniform(-0.1, 0.1) * ancho_muro)
            cortes.append(ancho_muro / 2.0)
            for c0, c1 in zip(cortes[:-1], cortes[1:]):
                s = a0 + rng.uniform(0.0, PIEDRA_LARGO[0]) * M * (hilada % 2)
                if s > a0:
                    res.append(("piedra", hilada, a0, s - junta, c0 + junta / 2, c1 - junta / 2,
                                z + rng.uniform(0, 0.02) * M, z1 - junta - rng.uniform(0, 0.03) * M))
                while s < a1 - minimo:
                    largo = rng.uniform(*PIEDRA_LARGO) * M
                    p1 = min(s + largo - junta, a1)
                    if p1 - s >= minimo:
                        res.append(("piedra", hilada, s, p1, c0 + junta / 2, c1 - junta / 2,
                                    z + rng.uniform(0, 0.02) * M, z1 - junta - rng.uniform(0, 0.03) * M))
                    s += largo
        hilada += 1
        z = z1
    return [r for r in res if r[3] - r[2] >= minimo and r[5] > r[4] and r[7] > r[6]]


# =============================================================================
#  PRINCIPAL
# =============================================================================

def piezas_existentes(doc):
    return [e for e in FilteredElementCollector(doc).OfClass(DirectShape).ToElements()
            if (e.ApplicationId or "") == APLICACION]


def borrar_piezas(doc):
    ids = [e.Id for e in piezas_existentes(doc)]
    if ids:
        doc.Delete(lista_net(ElementId, ids))
    return len(ids)


def ejecutar(entradas):
    L = []
    t0 = time.time()
    try:
        doc = DocumentManager.Instance.CurrentDBDocument
        # Solo el NOMBRE del archivo, no la ruta: una carpeta "VIDEO" no debe habilitar el modelo original
        ruta = doc.PathName or ""
        nombre = ruta.replace("\\", "/").split("/")[-1] if ruta else (doc.Title or "")
        if NOMBRE_REQUERIDO.upper() not in nombre.upper():
            return ("NO SE HIZO NADA: este nodo solo trabaja en una COPIA del modelo cuyo nombre "
                    "contenga '%s' (por ejemplo, MODELO_VIDEO.rvt). Archivo actual: %s"
                    % (NOMBRE_REQUERIDO, doc.Title))

        class Cfg(object):
            pass
        cfg = Cfg()
        cfg.largo = float(_entrada(entradas, 0, 40)) / 100.0 * M
        cfg.alto = float(_entrada(entradas, 1, 20)) / 100.0 * M
        cfg.espesor = float(_entrada(entradas, 2, 12)) / 100.0 * M
        cfg.junta = float(_entrada(entradas, 3, 1)) / 100.0 * M
        cfg.piedras = _a_bool(_entrada(entradas, 4, True))
        solo_borrar = _a_bool(_entrada(entradas, 5, False))
        if cfg.junta >= min(cfg.largo, cfg.alto):
            raise ValueError("La junta debe ser menor que el block.")

        TransactionManager.Instance.EnsureInTransaction(doc)
        try:
            borradas = borrar_piezas(doc)
            L.append("Piezas anteriores borradas: %d" % borradas)
            if solo_borrar:
                return "\n".join(L)

            cajas_obst = []
            for nombre_cat in CATEGORIAS_OBSTACULO:
                try:
                    bic = getattr(BuiltInCategory, nombre_cat)
                except AttributeError:
                    continue
                for e in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType().ToElements():
                    bb = e.get_BoundingBox(None)
                    if bb is not None:
                        cajas_obst.append(((bb.Min.X, bb.Min.Y, bb.Min.Z), (bb.Max.X, bb.Max.Y, bb.Max.Z)))

            muros = (FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Walls)
                     .WhereElementIsNotElementType().ToElements())
            categoria = ElementId(BuiltInCategory.OST_GenericModel)
            total = {"block": 0, "piedra": 0, "mortero": 0}
            omitidos = []
            for muro in muros:
                texto = texto_de(doc, muro)
                if any(w in texto for w in PALABRAS_EXCLUIR):
                    continue
                es_piedra = any(w in texto for w in PALABRAS_PIEDRA)
                es_block = any(w in texto for w in PALABRAS_BLOCK)
                if not (es_block or (es_piedra and cfg.piedras)):
                    continue
                k = id_entero(muro.Id)
                eje = eje_del_muro(muro)
                bb = muro.get_BoundingBox(None)
                if eje is None or bb is None:
                    omitidos.append("%d: muro curvo o sin geometría" % k)
                    continue
                try:
                    ancho = muro.Width
                    marco = Marco(*eje)
                    obst = obstaculos_del_muro(marco, ancho, cajas_obst)
                    if es_piedra:
                        lista = piezas_piedra(marco, ancho, bb.Min.Z, bb.Max.Z, obst,
                                              random.Random(SEMILLA * 100003 + k))
                    else:
                        lista = piezas_block(marco, ancho, bb.Min.Z, bb.Max.Z, obst, cfg)
                    material = material_de(muro)
                    for n, (tipo, hilada, s0, s1, t0_, t1_, z0, z1) in enumerate(lista):
                        ds = DirectShape.CreateElement(doc, categoria)
                        ds.ApplicationId = APLICACION
                        ds.ApplicationDataId = "pieza|%s|%d|%d|%d" % (tipo, k, hilada, n)
                        ds.SetShape(lista_net(GeometryObject,
                                              [caja_solida(marco, s0, s1, t0_, t1_, z0, z1, material)]))
                        total[tipo] += 1
                    L.append("Muro %d (%s): %d piezas, %d hiladas"
                             % (k, "piedra" if es_piedra else "block", len(lista),
                                1 + max([r[1] for r in lista] or [0])))
                except Exception:
                    omitidos.append("%d: error\n%s" % (k, traceback.format_exc()))
        finally:
            cerrar_transaccion()

        L.insert(1, "Piezas creadas: %d blocks, %d piedras, %d camas de mortero"
                 % (total["block"], total["piedra"], total["mortero"]))
        if omitidos:
            L.append("Muros omitidos:")
            L += ["  " + o for o in omitidos]
    except Exception:
        L.append("ERROR:\n" + traceback.format_exc())
        try:
            TransactionManager.Instance.ForceCloseTransaction()
        except Exception:
            pass
    L.append("Tiempo: %.1f s" % (time.time() - t0))
    return "\n".join(L)


OUT = ejecutar(IN)
