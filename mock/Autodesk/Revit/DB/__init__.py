# -*- coding: utf-8 -*-
"""Simulador mínimo de Autodesk.Revit.DB para probar nodo_video.py fuera de Revit.

Solo implementa lo que usa el nodo, con las restricciones que importan:
  - XYZ sin operadores (+, -, *): como en pythonnet 2.5.
  - ElementType.Name no se puede leer directo; sí con Element.Name.GetValue(tipo).
  - Los elementos del modelo son de solo lectura: cualquier intento de
    modificarlos o borrarlos lanza un error.
  - Cambiar una vista exige transacción abierta; ExportImage exige que esté cerrada.
  - HideElements/UnhideElements exigen List[ElementId] de .NET, no listas de Python.
Unidades internas: pies.
"""
import math
import os

import simulador
from System.Collections.Generic import ListaNet


class ErrorRevit(Exception):
    """Equivale a las excepciones de la API (ArgumentException, InvalidOperationException...)."""


# -----------------------------------------------------------------------------
#  Enumeraciones
# -----------------------------------------------------------------------------

class _Miembro(object):
    def __init__(self, enum, nombre):
        self.enum = enum
        self.nombre = nombre

    def __repr__(self):
        return "%s.%s" % (self.enum, self.nombre)


def _enum(nombre, miembros):
    cls = type(nombre, (object,), {})
    for m in miembros:
        setattr(cls, m, _Miembro(nombre, m))
    return cls


BuiltInCategory = _enum("BuiltInCategory", [
    "OST_StructuralFoundation", "OST_StructuralColumns", "OST_StructuralFraming",
    "OST_Walls", "OST_Floors", "OST_Stairs", "OST_Rebar", "OST_GenericModel",
    "OST_Toposolid", "OST_Topography", "OST_Doors", "OST_Windows", "OST_Levels", "OST_Views",
    "OST_Roofs", "OST_Ceilings", "OST_Railings", "OST_StairsRailing", "OST_Columns",
    "OST_CurtainWallPanels", "OST_CurtainWallMullions", "OST_StructConnections", "OST_AreaRein",
    "OST_PathRein", "OST_Furniture", "OST_Casework", "OST_PlumbingFixtures", "OST_LightingFixtures",
    "OST_SpecialityEquipment", "OST_Grids", "OST_FabricReinforcement", "OST_FabricAreas", "OST_Coupler",
])
ViewDetailLevel = _enum("ViewDetailLevel", ["Undefined", "Coarse", "Medium", "Fine"])
BuiltInParameter = _enum("BuiltInParameter", ["SYMBOL_NAME_PARAM", "ALL_MODEL_TYPE_NAME"])
ViewDuplicateOption = _enum("ViewDuplicateOption", ["Duplicate", "WithDetailing", "AsDependent"])
ExportRange = _enum("ExportRange", ["CurrentView", "VisibleRegionOfCurrentView", "SetOfViews"])
ImageFileType = _enum("ImageFileType", ["BMP", "JPEGLossless", "JPEGMedium", "PNG", "TIFF"])
ImageResolution = _enum("ImageResolution", ["DPI_72", "DPI_150", "DPI_300", "DPI_600"])
ZoomFitType = _enum("ZoomFitType", ["FitToPage", "Zoom"])
FitDirectionType = _enum("FitDirectionType", ["Horizontal", "Vertical"])


# -----------------------------------------------------------------------------
#  Geometría
# -----------------------------------------------------------------------------

class XYZ(object):
    """Punto/vector. A propósito SIN __add__, __sub__, __mul__ (trampa de pythonnet)."""
    __slots__ = ("_x", "_y", "_z")

    def __init__(self, x=0.0, y=0.0, z=0.0):
        self._x, self._y, self._z = float(x), float(y), float(z)

    X = property(lambda s: s._x)
    Y = property(lambda s: s._y)
    Z = property(lambda s: s._z)

    def Add(self, o):
        return XYZ(self._x + o.X, self._y + o.Y, self._z + o.Z)

    def Subtract(self, o):
        return XYZ(self._x - o.X, self._y - o.Y, self._z - o.Z)

    def Multiply(self, s):
        return XYZ(self._x * s, self._y * s, self._z * s)

    def Divide(self, s):
        return XYZ(self._x / s, self._y / s, self._z / s)

    def Negate(self):
        return XYZ(-self._x, -self._y, -self._z)

    def DotProduct(self, o):
        return self._x * o.X + self._y * o.Y + self._z * o.Z

    def CrossProduct(self, o):
        return XYZ(self._y * o.Z - self._z * o.Y,
                   self._z * o.X - self._x * o.Z,
                   self._x * o.Y - self._y * o.X)

    def GetLength(self):
        return math.sqrt(self.DotProduct(self))

    def Normalize(self):
        n = self.GetLength()
        if n < 1e-12:
            raise ErrorRevit("No se puede normalizar un vector nulo")
        return self.Divide(n)

    def DistanceTo(self, o):
        return self.Subtract(o).GetLength()

    def IsAlmostEqualTo(self, o, tol=1e-9):
        return self.DistanceTo(o) <= tol

    def __repr__(self):
        return "XYZ(%.4f, %.4f, %.4f)" % (self._x, self._y, self._z)


XYZ.Zero = XYZ(0, 0, 0)
XYZ.BasisX = XYZ(1, 0, 0)
XYZ.BasisY = XYZ(0, 1, 0)
XYZ.BasisZ = XYZ(0, 0, 1)


class Transform(object):
    def __init__(self, origen=None, bx=None, by=None, bz=None):
        self.Origin = origen or XYZ.Zero
        self.BasisX = bx or XYZ.BasisX
        self.BasisY = by or XYZ.BasisY
        self.BasisZ = bz or XYZ.BasisZ

    @property
    def Inverse(self):
        # Solo bases ortonormales (es lo que generan las vistas)
        bx, by, bz = self.BasisX, self.BasisY, self.BasisZ
        ix = XYZ(bx.X, by.X, bz.X)
        iy = XYZ(bx.Y, by.Y, bz.Y)
        iz = XYZ(bx.Z, by.Z, bz.Z)
        o = self.Origin
        io = XYZ(-o.DotProduct(bx), -o.DotProduct(by), -o.DotProduct(bz))
        return Transform(io, ix, iy, iz)

    def OfVector(self, v):
        return self.BasisX.Multiply(v.X).Add(self.BasisY.Multiply(v.Y)).Add(self.BasisZ.Multiply(v.Z))

    def OfPoint(self, p):
        return self.Origin.Add(self.OfVector(p))


Transform.Identity = Transform()


class BoundingBoxXYZ(object):
    def __init__(self):
        self.Min = XYZ.Zero
        self.Max = XYZ.Zero
        self.Transform = Transform()
        self.Enabled = True


# -----------------------------------------------------------------------------
#  Identificadores, categorías, parámetros
# -----------------------------------------------------------------------------

class ElementId(object):
    """Igualdad por identidad (no por valor) para obligar a comparar enteros."""

    def __init__(self, valor):
        self._v = int(valor)

    @property
    def Value(self):
        return self._v

    @property
    def IntegerValue(self):
        return self._v

    def __repr__(self):
        return "ElementId(%d)" % self._v


ElementId.InvalidElementId = ElementId(-1)


class Category(object):
    def __init__(self, bic, nombre, valor):
        self.BuiltInCategory = bic
        self.Name = nombre
        self.Id = ElementId(valor)

    @staticmethod
    def GetCategory(doc, bic):
        return doc._categorias.get(bic.nombre)


class Parameter(object):
    def __init__(self, valor):
        self._valor = valor

    def AsString(self):
        return self._valor


class _TipoNet(object):
    def __init__(self, nombre):
        self.Name = nombre


class _PropiedadNombre(object):
    """Element.Name: en tipos no se lee directo (trampa de pythonnet)."""

    def __get__(self, obj, cls):
        if obj is None:
            return self
        if isinstance(obj, ElementType):
            raise AttributeError("'%s' no expone Name en pythonnet: usa Element.Name.GetValue(tipo) "
                                 "o SYMBOL_NAME_PARAM" % type(obj).__name__)
        return obj._nombre

    def __set__(self, obj, valor):
        obj._fijar_nombre(valor)

    def GetValue(self, obj):
        return obj._nombre


# -----------------------------------------------------------------------------
#  Elementos
# -----------------------------------------------------------------------------

class Element(object):
    Name = _PropiedadNombre()

    def __init__(self, doc, valor_id, nombre="", categoria=None, tipo_id=None, cajas=None,
                 ocultable=True):
        object.__setattr__(self, "_doc", doc)
        object.__setattr__(self, "_id", ElementId(valor_id))
        object.__setattr__(self, "_nombre", nombre)
        object.__setattr__(self, "_categoria", categoria)
        object.__setattr__(self, "_tipo_id", tipo_id)
        object.__setattr__(self, "_cajas", list(cajas or []))  # [((x0,y0,z0),(x1,y1,z1)), ...] en pies
        object.__setattr__(self, "_ocultable", ocultable)

    # Los elementos del modelo son de solo lectura
    def __setattr__(self, nombre, valor):
        simulador.estado.modificaciones_modelo.append((self._id.Value, nombre))
        raise ErrorRevit("El nodo intentó modificar el elemento %d (%s)" % (self._id.Value, nombre))

    def _fijar_nombre(self, valor):
        simulador.estado.modificaciones_modelo.append((self._id.Value, "Name"))
        raise ErrorRevit("El nodo intentó renombrar el elemento %d" % self._id.Value)

    @property
    def Id(self):
        return self._id

    @property
    def Category(self):
        return self._categoria

    @property
    def Document(self):
        return self._doc

    def GetTypeId(self):
        return self._tipo_id if self._tipo_id is not None else ElementId.InvalidElementId

    def GetType(self):
        return _TipoNet(type(self).__name__)

    def get_BoundingBox(self, vista):
        if not self._cajas:
            return None
        bb = BoundingBoxXYZ()
        bb.Min = XYZ(min(c[0][0] for c in self._cajas), min(c[0][1] for c in self._cajas),
                     min(c[0][2] for c in self._cajas))
        bb.Max = XYZ(max(c[1][0] for c in self._cajas), max(c[1][1] for c in self._cajas),
                     max(c[1][2] for c in self._cajas))
        return bb

    def get_Parameter(self, bip):
        return None

    def CanBeHidden(self, vista):
        return self._ocultable

    def IsHidden(self, vista):
        return self._id.Value in vista._ocultos


class ElementType(Element):
    def get_Parameter(self, bip):
        if bip is BuiltInParameter.SYMBOL_NAME_PARAM or bip is BuiltInParameter.ALL_MODEL_TYPE_NAME:
            return Parameter(self._nombre)
        return None


class FamilySymbol(ElementType):
    pass


class WallType(ElementType):
    pass


class FloorType(ElementType):
    pass


class WallFoundationType(ElementType):
    pass


class StairsType(ElementType):
    pass


class RebarBarType(ElementType):
    pass


class FamilyInstance(Element):
    pass


class Wall(Element):
    pass


class Floor(Element):
    pass


class WallFoundation(Element):
    pass


class Stairs(Element):
    pass


class Toposolid(Element):
    pass


class _AceroBase(Element):
    """Acero de refuerzo: ajustes gráficos por vista (no cambian geometría)."""

    def __init__(self, *args, **kw):
        anfitrion = kw.pop("anfitrion", None)
        Element.__init__(self, *args, **kw)
        object.__setattr__(self, "_anfitrion", anfitrion)
        object.__setattr__(self, "_sin_obstruccion", set())
        object.__setattr__(self, "_solido", set())

    def _ajuste(self, vista, conjunto, valor, que):
        if not self._doc._transaccion:
            raise ErrorRevit("Modificación fuera de transacción: %s" % que)
        if valor:
            conjunto.add(vista.Id.Value)
        else:
            conjunto.discard(vista.Id.Value)
        simulador.estado.ajustes_acero.append((self._id.Value, vista.Id.Value, que, valor))

    def SetUnobscuredInView(self, vista, valor):
        self._ajuste(vista, self._sin_obstruccion, valor, "SetUnobscuredInView")

    def IsUnobscuredInView(self, vista):
        return vista.Id.Value in self._sin_obstruccion

    def SetSolidInView(self, vista, valor):
        if not isinstance(vista, View3D):
            raise TypeError("SetSolidInView espera View3D")
        self._ajuste(vista, self._solido, valor, "SetSolidInView")

    def IsSolidInView(self, vista):
        return vista.Id.Value in self._solido


class Rebar(_AceroBase):
    def GetHostId(self):
        return ElementId(self._anfitrion) if self._anfitrion else ElementId.InvalidElementId


class RebarInSystem(Rebar):
    """Barras de un refuerzo de área o de camino (categoría Armadura estructural)."""


class FabricSheet(_AceroBase):
    """Hoja de malla electrosoldada: el anfitrión se lee con la propiedad HostId."""

    @property
    def HostId(self):
        return ElementId(self._anfitrion) if self._anfitrion else ElementId.InvalidElementId


class Level(Element):
    def __init__(self, doc, valor_id, nombre, elevacion):
        Element.__init__(self, doc, valor_id, nombre)
        object.__setattr__(self, "_elev", float(elevacion))

    @property
    def Elevation(self):
        return self._elev

    @property
    def ProjectElevation(self):
        return self._elev


class ViewOrientation3D(object):
    def __init__(self, ojo, arriba, adelante):
        for v in (ojo, arriba, adelante):
            if not isinstance(v, XYZ):
                raise TypeError("ViewOrientation3D espera XYZ")
        if abs(arriba.GetLength() - 1) > 1e-6 or abs(adelante.GetLength() - 1) > 1e-6:
            raise ErrorRevit("ViewOrientation3D: vectores no unitarios")
        if abs(arriba.DotProduct(adelante)) > 1e-6:
            raise ErrorRevit("ViewOrientation3D: 'arriba' no es perpendicular a 'adelante'")
        self.EyePosition = ojo
        self.UpDirection = arriba
        self.ForwardDirection = adelante


class View3D(Element):
    """Vista 3D. Sus propiedades sí se pueden cambiar, pero solo dentro de transacción."""

    def __init__(self, doc, valor_id, nombre, perspectiva=False, plantilla=False):
        Element.__init__(self, doc, valor_id, nombre)
        s = object.__setattr__
        s(self, "_perspectiva", perspectiva)
        s(self, "_plantilla", plantilla)
        s(self, "_bloqueada", False)
        s(self, "_ocultos", set())
        s(self, "_cats_ocultas", set())
        s(self, "_orient", _orientacion_valida(XYZ(50, -50, 40), XYZ(0, 0, 0)))
        s(self, "_crop_min", XYZ(-10, -10, -100))
        s(self, "_crop_max", XYZ(10, 10, 100))
        s(self, "_crop_activa", False)
        s(self, "_crop_visible", True)
        s(self, "_caja_seccion", False)
        s(self, "_detalle", ViewDetailLevel.Medium)

    def _exigir_transaccion(self, que):
        if not self._doc._transaccion:
            raise ErrorRevit("Modificación fuera de transacción: %s" % que)

    def __setattr__(self, nombre, valor):
        props = {"CropBox", "CropBoxActive", "CropBoxVisible", "DetailLevel"}
        if nombre == "Name":
            self._fijar_nombre(valor)
        elif nombre in props:
            self._exigir_transaccion(nombre)
            getattr(type(self), nombre).fset(self, valor)
        else:
            Element.__setattr__(self, nombre, valor)

    def _fijar_nombre(self, valor):
        self._exigir_transaccion("Name")
        for v in self._doc._elementos.values():
            if isinstance(v, View3D) and v is not self and v._nombre == valor:
                raise ErrorRevit("Ya existe una vista llamada '%s'" % valor)
        object.__setattr__(self, "_nombre", valor)

    IsTemplate = property(lambda s: s._plantilla)
    IsPerspective = property(lambda s: s._perspectiva)
    IsLocked = property(lambda s: s._bloqueada)
    IsSectionBoxActive = property(lambda s: s._caja_seccion)
    DetailLevel = property(lambda s: s._detalle,
                           lambda s, v: object.__setattr__(s, "_detalle", v))

    def Unlock(self):
        self._exigir_transaccion("Unlock")
        object.__setattr__(self, "_bloqueada", False)

    def Duplicate(self, opcion):
        self._exigir_transaccion("Duplicate")
        if not isinstance(opcion, _Miembro) or opcion.enum != "ViewDuplicateOption":
            raise TypeError("Duplicate espera ViewDuplicateOption")
        doc = self._doc
        nueva = View3D(doc, doc._siguiente_id(), self._nombre + " Copia 1", self._perspectiva)
        s = object.__setattr__
        s(nueva, "_ocultos", set(self._ocultos))
        s(nueva, "_cats_ocultas", set(self._cats_ocultas))
        s(nueva, "_orient", self._orient)
        s(nueva, "_crop_min", self._crop_min)
        s(nueva, "_crop_max", self._crop_max)
        s(nueva, "_crop_activa", self._crop_activa)
        s(nueva, "_crop_visible", self._crop_visible)
        doc._agregar(nueva)
        simulador.estado.vistas_creadas.append(nueva._id.Value)
        return nueva.Id

    def GetOrientation(self):
        return self._orient

    def SetOrientation(self, orientacion):
        self._exigir_transaccion("SetOrientation")
        if self._bloqueada:
            raise ErrorRevit("La vista está bloqueada")
        if not isinstance(orientacion, ViewOrientation3D):
            raise TypeError("SetOrientation espera ViewOrientation3D")
        object.__setattr__(self, "_orient", orientacion)

    def _transformacion(self):
        o = self._orient
        f, u = o.ForwardDirection, o.UpDirection
        r = f.CrossProduct(u)
        return Transform(o.EyePosition, r, u, f.Negate())

    def _get_crop(self):
        bb = BoundingBoxXYZ()
        bb.Transform = self._transformacion()
        bb.Min, bb.Max = self._crop_min, self._crop_max
        return bb

    def _set_crop(self, bb):
        t, actual = bb.Transform, self._transformacion()
        for a, b in ((t.Origin, actual.Origin), (t.BasisX, actual.BasisX),
                     (t.BasisY, actual.BasisY), (t.BasisZ, actual.BasisZ)):
            if not a.IsAlmostEqualTo(b, 1e-6):
                raise ErrorRevit("CropBox con Transform que no corresponde a la orientación actual")
        if not (bb.Min.X < bb.Max.X and bb.Min.Y < bb.Max.Y and bb.Min.Z < bb.Max.Z):
            raise ErrorRevit("CropBox con Min >= Max")
        object.__setattr__(self, "_crop_min", bb.Min)
        object.__setattr__(self, "_crop_max", bb.Max)

    CropBox = property(_get_crop, _set_crop)
    CropBoxActive = property(lambda s: s._crop_activa,
                             lambda s, v: object.__setattr__(s, "_crop_activa", bool(v)))
    CropBoxVisible = property(lambda s: s._crop_visible,
                              lambda s, v: object.__setattr__(s, "_crop_visible", bool(v)))

    def _ids_de(self, lista, que):
        self._exigir_transaccion(que)
        if not isinstance(lista, ListaNet):
            raise TypeError("%s espera ICollection<ElementId> (List[ElementId]), no %s"
                            % (que, type(lista).__name__))
        if lista.Count == 0:
            raise ErrorRevit("%s: la colección está vacía" % que)
        return [i.Value for i in lista]

    def HideElements(self, lista):
        ids = self._ids_de(lista, "HideElements")
        for i in ids:
            e = self._doc._elementos.get(i)
            if e is None or not e.CanBeHidden(self):
                raise ErrorRevit("HideElements: el elemento %d no se puede ocultar" % i)
        self._ocultos.update(ids)
        simulador.estado.registro.append(("HideElements", self._id.Value, len(ids)))

    def UnhideElements(self, lista):
        ids = self._ids_de(lista, "UnhideElements")
        self._ocultos.difference_update(ids)
        simulador.estado.registro.append(("UnhideElements", self._id.Value, len(ids)))

    def SetCategoryHidden(self, cat_id, oculto):
        self._exigir_transaccion("SetCategoryHidden")
        if oculto:
            self._cats_ocultas.add(cat_id.Value)
        else:
            self._cats_ocultas.discard(cat_id.Value)

    def GetCategoryHidden(self, cat_id):
        return cat_id.Value in self._cats_ocultas

    def _es_visible(self, e):
        if e._id.Value in self._ocultos:
            return False
        if e._categoria is not None and e._categoria.Id.Value in self._cats_ocultas:
            return False
        return True


def _orientacion_valida(ojo, objetivo):
    f = objetivo.Subtract(ojo).Normalize()
    r = f.CrossProduct(XYZ.BasisZ).Normalize()
    u = r.CrossProduct(f).Normalize()
    return ViewOrientation3D(ojo, u, f)


# -----------------------------------------------------------------------------
#  Colector
# -----------------------------------------------------------------------------

class FilteredElementCollector(object):
    def __init__(self, doc, vista_id=None):
        self._doc = doc
        elementos = list(doc._elementos.values())
        if vista_id is not None:
            vista = doc.GetElement(vista_id)
            elementos = [e for e in elementos
                         if not isinstance(e, (View3D, Level, ElementType)) and e._cajas
                         and vista._es_visible(e)]
        self._elementos = elementos

    def _filtrar(self, cond):
        self._elementos = [e for e in self._elementos if cond(e)]
        return self

    def OfClass(self, cls):
        return self._filtrar(lambda e: isinstance(e, cls))

    def OfCategory(self, bic):
        return self._filtrar(lambda e: e._categoria is not None and e._categoria.BuiltInCategory is bic)

    def WhereElementIsNotElementType(self):
        return self._filtrar(lambda e: not isinstance(e, ElementType))

    def WhereElementIsElementType(self):
        return self._filtrar(lambda e: isinstance(e, ElementType))

    def ToElements(self):
        return list(self._elementos)

    def ToElementIds(self):
        return [e.Id for e in self._elementos]

    def FirstElement(self):
        return self._elementos[0] if self._elementos else None

    def GetElementCount(self):
        return len(self._elementos)

    def __iter__(self):
        return iter(list(self._elementos))


# -----------------------------------------------------------------------------
#  Exportación de imagen
# -----------------------------------------------------------------------------

class ImageExportOptions(object):
    def __init__(self):
        self.ExportRange = ExportRange.CurrentView
        self.FilePath = ""
        self.HLRandWFViewsFileType = ImageFileType.JPEGLossless
        self.ShadowViewsFileType = ImageFileType.JPEGLossless
        self.ImageResolution = ImageResolution.DPI_72
        self.ZoomType = ZoomFitType.Zoom
        self.FitDirection = FitDirectionType.Horizontal
        self.PixelSize = 512
        self._vistas = None

    def SetViewsAndSheets(self, lista):
        if not isinstance(lista, ListaNet):
            raise TypeError("SetViewsAndSheets espera IList<ElementId> (List[ElementId])")
        self._vistas = [i.Value for i in lista]

    def GetViewsAndSheets(self):
        return list(self._vistas or [])


# -----------------------------------------------------------------------------
#  Documento
# -----------------------------------------------------------------------------

class Document(object):
    def __init__(self, titulo="Modelo sintético"):
        self.Title = titulo
        self.PathName = ""
        self._elementos = {}
        self._categorias = {}
        self._contador = 1000
        self._transaccion = False

    def _siguiente_id(self):
        self._contador += 1
        return self._contador

    def _agregar(self, e):
        self._elementos[e.Id.Value] = e
        return e

    @property
    def IsModifiable(self):
        return self._transaccion

    def GetElement(self, eid):
        if not isinstance(eid, ElementId):
            raise TypeError("GetElement espera ElementId")
        return self._elementos.get(eid.Value)

    def Regenerate(self):
        if not self._transaccion:
            raise ErrorRevit("Regenerate fuera de transacción")
        simulador.estado.registro.append(("Regenerate",))

    def Delete(self, *args):
        simulador.estado.modificaciones_modelo.append(("Delete", args))
        raise ErrorRevit("El nodo intentó borrar elementos")

    def ExportImage(self, op):
        est = simulador.estado
        if self._transaccion:
            raise ErrorRevit("ExportImage con transacción abierta")
        if op.ExportRange is not ExportRange.SetOfViews or not op._vistas:
            raise ErrorRevit("ExportImage: se esperaba ExportRange.SetOfViews con vistas")
        if op.HLRandWFViewsFileType is not ImageFileType.PNG or op.ShadowViewsFileType is not ImageFileType.PNG:
            raise ErrorRevit("ExportImage: se esperaba PNG")
        if op.ZoomType is not ZoomFitType.FitToPage or op.FitDirection is not FitDirectionType.Vertical:
            raise ErrorRevit("ExportImage: se esperaba FitToPage + Vertical")
        carpeta = os.path.dirname(op.FilePath)
        if not os.path.isdir(carpeta):
            raise ErrorRevit("ExportImage: no existe la carpeta %s" % carpeta)
        est.contador_export += 1
        falla = est.fallos.get(est.contador_export)
        if falla == "caida":
            raise simulador.CaidaDeRevit("Revit se cerró en la exportación %d" % est.contador_export)
        if falla == "error":
            raise ErrorRevit("Error simulado en la exportación %d" % est.contador_export)
        for vid in op._vistas:
            vista = self._elementos[vid]
            ancho_v = vista._crop_max.X - vista._crop_min.X
            alto_v = vista._crop_max.Y - vista._crop_min.Y
            alto = int(op.PixelSize)
            ancho = int(round(alto * ancho_v / alto_v))
            # Revit agrega " - <tipo de vista> - <nombre>" al nombre del archivo
            ruta = "%s - Vista 3D - %s.png" % (op.FilePath, vista._nombre)
            est.exportes.append({
                "ruta": ruta,
                "vista": vid,
                "ancho": ancho,
                "alto": alto,
                "visibles": sorted(e for e in self._elementos
                                   if not isinstance(self._elementos[e], (View3D, Level, ElementType))
                                   and self._elementos[e]._cajas
                                   and vista._es_visible(self._elementos[e])),
                "orientacion": vista._orient,
                "crop": (vista._crop_min, vista._crop_max),
                "crop_activa": vista._crop_activa,
                "sin_obstruccion": sorted(k for k, e in self._elementos.items()
                                          if isinstance(e, _AceroBase) and e.IsUnobscuredInView(vista)),
            })
            est.exportador(self, vista, ruta, ancho, alto)
