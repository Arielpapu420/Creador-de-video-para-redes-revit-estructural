# -*- coding: utf-8 -*-
"""Modelo estructural SINTÉTICO de una casa genérica de muros de carga (2 niveles + azotea).

No corresponde a ningún proyecto real. Planta de 8 x 10 m con ejes a cada 4 y 5 m.
Las medidas se escriben en metros y se convierten a pies (unidades internas de Revit).

Contenido:
  - Terreno (Toposolid) con excavación y fondo de excavación (Modelo genérico), banqueta.
  - Cimientos corridos (WallFoundation) bajo cada tramo de muro.
  - Dados (FamilyInstance de Cimentación estructural) en cada cruce de ejes.
  - Cadenas de desplante (Armazón estructural en la Z más baja).
  - Columnas en cruces y castillos a media crujía (Pilares estructurales).
  - Muros de carga, trabes/cadenas de cerramiento y losas en planta baja y planta alta.
  - Escalera, pretiles de azotea, una puerta y un muro oculto en la vista base.
  - Varillas (Rebar) en columnas, cadenas y trabes, con su anfitrión.
"""
from Autodesk.Revit.DB import (
    BuiltInCategory, Category, Document, FamilyInstance, FamilySymbol, Floor, FloorType,
    Level, Rebar, RebarBarType, Stairs, StairsType, Toposolid, View3D, Wall, WallFoundation,
    WallFoundationType, WallType,
)

M = 1.0 / 0.3048  # metros -> pies

EJES_X = [0.0, 4.0, 8.0]
EJES_Y = [0.0, 5.0, 10.0]
NIVELES = [("Nivel 0 - Planta baja", 0.0), ("Nivel 1 - Planta alta", 3.0), ("Nivel 2 - Azotea", 6.0)]


def _caja(x0, y0, z0, x1, y1, z1):
    """Caja en metros -> tupla en pies."""
    return ((min(x0, x1) * M, min(y0, y1) * M, min(z0, z1) * M),
            (max(x0, x1) * M, max(y0, y1) * M, max(z0, z1) * M))


def _tramos():
    """Tramos de muro entre cruces de ejes: (x0, y0, x1, y1, es_perimetral)."""
    t = []
    for y in EJES_Y:
        for x0, x1 in zip(EJES_X[:-1], EJES_X[1:]):
            t.append((x0, y, x1, y, y in (EJES_Y[0], EJES_Y[-1])))
    for x in EJES_X:
        for y0, y1 in zip(EJES_Y[:-1], EJES_Y[1:]):
            t.append((x, y0, x, y1, x in (EJES_X[0], EJES_X[-1])))
    return t


def _caja_lineal(x0, y0, x1, y1, ancho, z0, z1, recorte=0.0):
    """Caja a lo largo de un tramo horizontal o vertical, centrada en el eje."""
    a = ancho / 2.0
    if y0 == y1:
        return _caja(x0 + recorte, y0 - a, z0, x1 - recorte, y0 + a, z1)
    return _caja(x0 - a, y0 + recorte, z0, x0 + a, y1 - recorte, z1)


class _Constructor(object):
    def __init__(self):
        self.doc = Document("Casa sintética de muros de carga")
        self.cats = {}
        self.ids = {}  # rol -> [ids]
        for i, (clave, nombre) in enumerate([
                ("OST_StructuralFoundation", "Cimentación estructural"),
                ("OST_StructuralColumns", "Pilares estructurales"),
                ("OST_StructuralFraming", "Armazón estructural"),
                ("OST_Walls", "Muros"), ("OST_Floors", "Suelos"), ("OST_Stairs", "Escaleras"),
                ("OST_Rebar", "Armadura estructural"), ("OST_GenericModel", "Modelos genéricos"),
                ("OST_Toposolid", "Toposólido"), ("OST_Doors", "Puertas"), ("OST_Windows", "Ventanas")]):
            cat = Category(getattr(BuiltInCategory, clave), nombre, -2000000 - i)
            self.cats[clave] = cat
            self.doc._categorias[clave] = cat

    def nuevo(self, clase, rol, nombre="", cat=None, tipo=None, cajas=None, **kw):
        e = clase(self.doc, self.doc._siguiente_id(), nombre, self.cats.get(cat),
                  tipo.Id if tipo is not None else None, cajas, **kw)
        self.doc._agregar(e)
        self.ids.setdefault(rol, []).append(e.Id.Value)
        return e

    def tipo(self, clase, nombre, cat):
        return self.nuevo(clase, "tipos", nombre, cat)


def crear_documento():
    b = _Constructor()
    doc = b.doc

    for nombre, elev in NIVELES:
        doc._agregar(Level(doc, doc._siguiente_id(), nombre, elev * M))

    # Tipos (nombres genéricos)
    t_corrido = b.tipo(WallFoundationType, "Cimiento corrido 60 cm", "OST_StructuralFoundation")
    t_dado = b.tipo(FamilySymbol, "Dado 60x60x60", "OST_StructuralFoundation")
    t_desplante = b.tipo(FamilySymbol, "Cadena de desplante 15x30", "OST_StructuralFraming")
    t_cerramiento = b.tipo(FamilySymbol, "Cadena de cerramiento 15x30", "OST_StructuralFraming")
    t_columna = b.tipo(FamilySymbol, "Columna 25x25", "OST_StructuralColumns")
    t_castillo = b.tipo(FamilySymbol, "Castillo 15x15", "OST_StructuralColumns")
    t_muro = b.tipo(WallType, "Muro de block 15 cm", "OST_Walls")
    t_pretil = b.tipo(WallType, "Pretil de block 12 cm", "OST_Walls")
    t_losa = b.tipo(FloorType, "Losa maciza 10 cm", "OST_Floors")
    t_escalera = b.tipo(StairsType, "Escalera de concreto", "OST_Stairs")
    t_varilla = b.tipo(RebarBarType, "Varilla 3/8", "OST_Rebar")
    t_generico = b.tipo(FamilySymbol, "Genérico", "OST_GenericModel")
    t_puerta = b.tipo(FamilySymbol, "Puerta 90x210", "OST_Doors")

    # Terreno con excavación (anillo alrededor de la huella) + fondo de excavación
    hx0, hy0, hx1, hy1 = -1.2, -1.2, 9.2, 11.2
    tx0, ty0, tx1, ty1 = -12.0, -12.0, 20.0, 22.0
    anillo = [_caja(tx0, ty0, -0.2, tx1, hy0, 0.0), _caja(tx0, hy1, -0.2, tx1, ty1, 0.0),
              _caja(tx0, hy0, -0.2, hx0, hy1, 0.0), _caja(hx1, hy0, -0.2, tx1, hy1, 0.0)]
    b.nuevo(Toposolid, "terreno", "Terreno", "OST_Toposolid", None, anillo)
    b.nuevo(FamilyInstance, "genericos", "Fondo de excavación", "OST_GenericModel", t_generico,
            [_caja(hx0, hy0, -1.25, hx1, hy1, -1.15)])
    b.nuevo(FamilyInstance, "genericos", "Banqueta", "OST_GenericModel", t_generico,
            [_caja(-1.2, -3.0, 0.0, 9.2, -1.8, 0.1)])

    tramos = _tramos()
    cruces = [(x, y) for x in EJES_X for y in EJES_Y]

    # Cimentación
    for x0, y0, x1, y1, _ in tramos:
        b.nuevo(WallFoundation, "corridos", "", "OST_StructuralFoundation", t_corrido,
                [_caja_lineal(x0, y0, x1, y1, 0.6, -0.8, -0.3)])
    for x, y in cruces:
        b.nuevo(FamilyInstance, "dados", "", "OST_StructuralFoundation", t_dado,
                [_caja(x - 0.3, y - 0.3, -1.1, x + 0.3, y + 0.3, -0.5)])

    columnas_pb, armazon = [], []
    for x0, y0, x1, y1, _ in tramos:
        e = b.nuevo(FamilyInstance, "desplante", "", "OST_StructuralFraming", t_desplante,
                    [_caja_lineal(x0, y0, x1, y1, 0.15, -0.3, 0.0)])
        armazon.append((e, x0, y0, x1, y1, -0.3, 0.0))

    def planta(rol, z0, z_trabe, z_losa, z_tope):
        cols = []
        for x, y in cruces:
            zc = -0.5 if z0 == 0.0 else z0
            cols.append(b.nuevo(FamilyInstance, "columnas_" + rol, "", "OST_StructuralColumns", t_columna,
                                [_caja(x - 0.125, y - 0.125, zc, x + 0.125, y + 0.125, z_trabe)]))
        for x0, y0, x1, y1, _ in tramos:
            xm, ym = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            cols.append(b.nuevo(FamilyInstance, "castillos_" + rol, "", "OST_StructuralColumns", t_castillo,
                                [_caja(xm - 0.075, ym - 0.075, z0, xm + 0.075, ym + 0.075, z_trabe)]))
        for x0, y0, x1, y1, _ in tramos:
            b.nuevo(Wall, "muros_" + rol, "", "OST_Walls", t_muro,
                    [_caja_lineal(x0, y0, x1, y1, 0.15, z0, z_trabe, recorte=0.125)])
        for x0, y0, x1, y1, _ in tramos:
            e = b.nuevo(FamilyInstance, "trabes_" + rol, "", "OST_StructuralFraming", t_cerramiento,
                        [_caja_lineal(x0, y0, x1, y1, 0.15, z_trabe, z_losa)])
            armazon.append((e, x0, y0, x1, y1, z_trabe, z_losa))
        for xa, xb in ((-0.1, 4.0), (4.0, 8.1)):
            b.nuevo(Floor, "losas_" + rol, "", "OST_Floors", t_losa,
                    [_caja(xa, -0.1, z_losa, xb, 10.1, z_tope)])
        return cols

    columnas_pb = planta("pb", 0.0, 2.6, 2.9, 3.0)
    columnas_pa = planta("pa", 3.0, 5.6, 5.9, 6.0)

    # Escalera de planta baja: 16 peraltes de 18 cm
    escalones = [_caja(6.6, 0.4 + i * 0.28, 0.0, 7.6, 0.4 + (i + 1) * 0.28, (i + 1) * 0.18)
                 for i in range(16)]
    b.nuevo(Stairs, "escaleras", "", "OST_Stairs", t_escalera, escalones)

    # Pretiles de azotea (solo perímetro)
    for x0, y0, x1, y1, perim in tramos:
        if perim:
            b.nuevo(Wall, "pretiles", "", "OST_Walls", t_pretil,
                    [_caja_lineal(x0, y0, x1, y1, 0.12, 6.0, 6.9)])

    # Una puerta (se oculta por categoría) y un muro provisional oculto en la vista base
    b.nuevo(FamilyInstance, "puertas", "", "OST_Doors", t_puerta, [_caja(1.55, -0.08, 0.0, 2.45, 0.08, 2.1)])
    oculto = b.nuevo(Wall, "muro_oculto_base", "Muro provisional", "OST_Walls", t_muro,
                     [_caja(10.0, 2.0, 0.0, 10.15, 6.0, 2.0)])

    # Varillas: 4 por columna, 2 por cadena/trabe
    def varillas_columna(col):
        (x0, y0, z0), (x1, y1, z1) = col._cajas[0]
        r, d = 0.04 * M, 0.012 * M
        cajas = [((x - d, y - d, z0), (x + d, y + d, z1))
                 for x in (x0 + r, x1 - r) for y in (y0 + r, y1 - r)]
        b.nuevo(Rebar, "varillas", "", "OST_Rebar", t_varilla, cajas, anfitrion=col.Id.Value)

    for col in columnas_pb + columnas_pa:
        if col.Id.Value in b.ids["columnas_pb"] + b.ids["columnas_pa"]:
            varillas_columna(col)
    for e, x0, y0, x1, y1, z0, z1 in armazon:
        cajas = [_caja_lineal(x0, y0, x1, y1, 0.02, z0 + 0.04, z0 + 0.06),
                 _caja_lineal(x0, y0, x1, y1, 0.02, z1 - 0.06, z1 - 0.04)]
        b.nuevo(Rebar, "varillas", "", "OST_Rebar", t_varilla, cajas, anfitrion=e.Id.Value)
    # Una varilla suelta, sin anfitrión
    b.nuevo(Rebar, "varillas_sueltas", "", "OST_Rebar", t_varilla, [_caja(9.0, 9.0, 0.0, 9.02, 9.02, 1.0)])

    # Vistas: base isométrica, una en perspectiva y una plantilla
    base = View3D(doc, doc._siguiente_id(), "{3D}")
    doc._agregar(base)
    base._ocultos.add(oculto.Id.Value)
    doc._agregar(View3D(doc, doc._siguiente_id(), "Cámara exterior", perspectiva=True))
    doc._agregar(View3D(doc, doc._siguiente_id(), "Plantilla 3D", plantilla=True))

    doc._ids_por_rol = b.ids
    return doc
