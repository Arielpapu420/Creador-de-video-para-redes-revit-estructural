# -*- coding: utf-8 -*-
"""Modelo estructural SINTÉTICO de una casa genérica de muros de carga (2 niveles + azotea).

No corresponde a ningún proyecto real. Planta de 8 x 10 m con ejes a cada 4 y 5 m.
Las medidas se escriben en metros y se convierten a pies (unidades internas de Revit).

Contenido:
  - Terreno (Toposolid) con excavación; fondo de excavación y guarnición (Modelos genéricos
    sin regla: quedan como base).
  - Cimiento de mampostería de piedra en el perímetro: Muros con material "Piedra braza" (el
    tipo NO dice piedra: se reconoce por el material). Cimientos corridos de concreto
    (WallFoundation) en los ejes interiores y dados en cada cruce de ejes.
  - Cisterna enterrada (muros, fondo y tapa, con "cisterna" en el tipo).
  - Cadenas de desplante y firme de concreto de planta baja.
  - Columnas en cruces y castillos a media crujía; muros de block; dala de repartición,
    cerramiento de puerta y cadenas de cerramiento.
  - Todas las losas son de vigueta y bovedilla, cada parte como elemento aparte: viguetas
    "mini trabes" (Armazón estructural de 12x13 cm cuyo tipo NO dice vigueta: se reconocen por
    tamaño), bovedillas como Modelo genérico y capa de compresión (Suelo) con malla. En planta
    baja la capa dice "compresión" en el tipo; en azotea no: se reconoce por estar sobre las
    viguetas. La planta baja lleva un volado (marquesina) con viguetas en voladizo.
  - Planta alta y azotea; pretiles; base de tinaco y tinaco.
  - Exteriores: banqueta (por palabra clave) y patio (por estar fuera de la huella).
  - Escalera, una puerta y un muro oculto en la vista base.
  - Acero con su anfitrión: varillas y estribos en columnas, castillos, cadenas y trabes;
    parrillas en cimientos corridos y dados; varillas en muros de cisterna; refuerzo de área
    (RebarInSystem) en fondo y tapa de la cisterna; mallas (FabricSheet) en las capas de compresión.
    Además, una varilla sin anfitrión dentro de una columna y otra fuera de todo concreto.
"""
import math

from Autodesk.Revit.DB import (
    BuiltInCategory, Category, Document, FamilyInstance, Material, FamilySymbol, Floor, FloorType,
    FabricSheet, Level, Rebar, RebarBarType, RebarInSystem, Stairs, StairsType, Toposolid, View3D, Wall,
    WallFoundation, WallFoundationType, WallType,
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
    def __init__(self, titulo):
        self.doc = Document(titulo)
        self.cats = {}
        self.ids = {}  # rol -> [ids]
        for i, (clave, nombre) in enumerate([
                ("OST_StructuralFoundation", "Cimentación estructural"),
                ("OST_StructuralColumns", "Pilares estructurales"),
                ("OST_StructuralFraming", "Armazón estructural"),
                ("OST_Walls", "Muros"), ("OST_Floors", "Suelos"), ("OST_Stairs", "Escaleras"),
                ("OST_Rebar", "Armadura estructural"), ("OST_GenericModel", "Modelos genéricos"),
                ("OST_FabricReinforcement", "Malla electrosoldada"),
                ("OST_Toposolid", "Toposólido"), ("OST_Doors", "Puertas"), ("OST_Windows", "Ventanas")]):
            bic = getattr(BuiltInCategory, clave)
            cat = Category(bic, nombre, bic.valor)
            self.cats[clave] = cat
            self.doc._categorias[clave] = cat

    def nuevo(self, clase, rol, nombre="", cat=None, tipo=None, cajas=None, **kw):
        e = clase(self.doc, self.doc._siguiente_id(), nombre, self.cats.get(cat),
                  tipo.Id if tipo is not None else None, cajas, **kw)
        self.doc._agregar(e)
        self.ids.setdefault(rol, []).append(e.Id.Value)
        return e

    def tipo(self, clase, nombre, cat, familia=""):
        t = self.nuevo(clase, "tipos", nombre, cat)
        object.__setattr__(t, "_familia", familia)
        return t

    def material(self, nombre):
        return self.nuevo(Material, "materiales", nombre).Id.Value


def crear_documento(titulo="CASA_SINTETICA_VIDEO"):
    """Documento sintético. El título lleva "VIDEO" para que nodo_piezas.py acepte trabajar."""
    b = _Constructor(titulo)
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
    t_escalera = b.tipo(StairsType, "Escalera de concreto", "OST_Stairs")
    t_varilla = b.tipo(RebarBarType, "Varilla 3/8", "OST_Rebar")
    t_malla = b.tipo(FamilySymbol, "Malla 6x6-10/10", "OST_FabricReinforcement")
    t_generico = b.tipo(FamilySymbol, "Genérico", "OST_GenericModel")
    t_mamposteria = b.tipo(WallType, "Muro estructural 50 cm", "OST_Walls")
    t_cisterna = b.tipo(WallType, "Muro de concreto cisterna 15 cm", "OST_Walls")
    t_losa_cisterna = b.tipo(FloorType, "Losa de cisterna 15 cm", "OST_Floors")
    t_firme = b.tipo(FloorType, "Firme de concreto 8 cm", "OST_Floors")
    t_vigueta = b.tipo(FamilySymbol, "VP 12-5", "OST_StructuralFraming", familia="Elemento prefabricado")
    t_bovedilla = b.tipo(FamilySymbol, "Bovedilla 15x25x56", "OST_GenericModel", familia="Bovedilla")
    t_compresion = b.tipo(FloorType, "Firme de compresión 5 cm", "OST_Floors")
    t_losa_azotea = b.tipo(FloorType, "Losa de azotea 5 cm", "OST_Floors")
    t_dala = b.tipo(FamilySymbol, "Dala de repartición 15x10", "OST_StructuralFraming")
    t_cerr_puerta = b.tipo(FamilySymbol, "Cerramiento 15x20", "OST_StructuralFraming")
    t_base_tinaco = b.tipo(FloorType, "Base de tinaco", "OST_Floors")
    t_tinaco = b.tipo(FamilySymbol, "Tinaco 1100 L", "OST_GenericModel", familia="Tinaco")
    t_banqueta = b.tipo(FloorType, "Banqueta de concreto 10 cm", "OST_Floors")
    t_patio = b.tipo(FloorType, "Concreto estampado 10 cm", "OST_Floors")
    m_piedra = b.material("Piedra braza")
    m_concreto = b.material("Concreto f'c=250")
    m_block = b.material("Block de concreto")
    t_puerta = b.tipo(FamilySymbol, "Puerta 90x210", "OST_Doors")

    # Terreno con excavación (anillo alrededor de la huella) + fondo de excavación
    hx0, hy0, hx1, hy1 = -1.2, -1.2, 12.0, 11.2
    tx0, ty0, tx1, ty1 = -12.0, -12.0, 20.0, 22.0
    anillo = [_caja(tx0, ty0, -0.2, tx1, hy0, 0.0), _caja(tx0, hy1, -0.2, tx1, ty1, 0.0),
              _caja(tx0, hy0, -0.2, hx0, hy1, 0.0), _caja(hx1, hy0, -0.2, tx1, hy1, 0.0)]
    b.nuevo(Toposolid, "terreno", "Terreno", "OST_Toposolid", None, anillo)
    b.nuevo(FamilyInstance, "genericos", "Fondo de excavación", "OST_GenericModel", t_generico,
            [_caja(hx0, hy0, -1.25, hx1, hy1, -1.15)])
    b.nuevo(FamilyInstance, "genericos", "Guarnición", "OST_GenericModel", t_generico,
            [_caja(-1.2, -3.3, 0.0, 12.0, -3.1, 0.15)])

    tramos = _tramos()
    cruces = [(x, y) for x in EJES_X for y in EJES_Y]

    # Cimentación: mampostería de piedra en el perímetro, concreto en los ejes interiores
    for x0, y0, x1, y1, perim in tramos:
        if perim:
            b.nuevo(Wall, "mamposteria", "", "OST_Walls", t_mamposteria,
                    [_caja_lineal(x0, y0, x1, y1, 0.5, -0.9, -0.3)], materiales=[m_piedra])
        else:
            b.nuevo(WallFoundation, "corridos", "", "OST_StructuralFoundation", t_corrido,
                    [_caja_lineal(x0, y0, x1, y1, 0.6, -0.8, -0.3)], materiales=[m_concreto])
    for x, y in cruces:
        b.nuevo(FamilyInstance, "dados", "", "OST_StructuralFoundation", t_dado,
                [_caja(x - 0.3, y - 0.3, -1.1, x + 0.3, y + 0.3, -0.5)])

    # Cisterna enterrada fuera de la casa: muros, fondo y tapa
    cx0, cy0, cx1, cy1 = 9.6, 1.0, 11.6, 3.0
    for x0, y0, x1, y1 in ((cx0, cy0, cx1, cy0), (cx0, cy1, cx1, cy1), (cx0, cy0, cx0, cy1), (cx1, cy0, cx1, cy1)):
        b.nuevo(Wall, "cisterna", "", "OST_Walls", t_cisterna,
                [_caja_lineal(x0, y0, x1, y1, 0.15, -2.0, 0.0)], materiales=[m_concreto])
    b.nuevo(Floor, "cisterna", "", "OST_Floors", t_losa_cisterna, [_caja(cx0, cy0, -2.15, cx1, cy1, -2.0)])
    b.nuevo(Floor, "cisterna", "", "OST_Floors", t_losa_cisterna, [_caja(cx0, cy0, 0.0, cx1, cy1, 0.12)])

    columnas_pb, armazon = [], []
    for x0, y0, x1, y1, _ in tramos:
        e = b.nuevo(FamilyInstance, "desplante", "", "OST_StructuralFraming", t_desplante,
                    [_caja_lineal(x0, y0, x1, y1, 0.15, -0.3, 0.0)])
        armazon.append((e, x0, y0, x1, y1, -0.3, 0.0))

    # Firme de planta baja (sobre el terreno, dentro de la casa)
    b.nuevo(Floor, "firme", "", "OST_Floors", t_firme, [_caja(0.075, 0.075, -0.08, 7.925, 9.925, 0.0)])

    def vigueta_bovedilla(sufijo, sentido, a0, a1, c0, c1, zv):
        """Viguetas a cada 70 cm paralelas a `sentido` ("x" o "y"), de a0 a a1, repartidas de c0
        a c1, y bovedillas de 56 cm entre ellas. Peralte 13 cm bajo la capa de compresión (zv)."""
        def caja(a_lo, a_hi, c_lo, c_hi):
            if sentido == "x":
                return _caja(a_lo, c_lo, zv - 0.13, a_hi, c_hi, zv)
            return _caja(c_lo, a_lo, zv - 0.13, c_hi, a_hi, zv)
        cs = [c0 + 0.6 + 0.7 * k for k in range(20) if c0 + 0.6 + 0.7 * k < c1 - 0.3]
        for c in cs:
            b.nuevo(FamilyInstance, "viguetas" + sufijo, "", "OST_StructuralFraming", t_vigueta,
                    [caja(a0, a1, c - 0.06, c + 0.06)])
        n = int(math.ceil((a1 - a0 - 0.15) / 0.6))
        for c_a, c_b in zip([c0 + 0.075] + [c + 0.06 for c in cs], [c - 0.06 for c in cs] + [c1 - 0.075]):
            b.nuevo(FamilyInstance, "bovedillas" + sufijo, "", "OST_GenericModel", t_bovedilla,
                    [caja(a0 + 0.075 + 0.6 * k, min(a0 + 0.075 + 0.6 * (k + 1) - 0.02, a1 - 0.075), c_a, c_b)
                     for k in range(n)])

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
                    [_caja_lineal(x0, y0, x1, y1, 0.15, z0, z_trabe, recorte=0.125)], materiales=[m_block])
        for x0, y0, x1, y1, _ in tramos:
            e = b.nuevo(FamilyInstance, "trabes_" + rol, "", "OST_StructuralFraming", t_cerramiento,
                        [_caja_lineal(x0, y0, x1, y1, 0.15, z_trabe, z_losa)])
            armazon.append((e, x0, y0, x1, y1, z_trabe, z_losa))
        # Losa de vigueta y bovedilla en las dos crujías (viguetas en el claro corto, de 4 m)
        zv = z_tope - 0.05
        sufijo = "" if rol == "pb" else "_pa"
        for xa in (0.0, 4.0):
            for ya, yb in ((0.0, 5.0), (5.0, 10.0)):
                vigueta_bovedilla(sufijo, "x", xa, xa + 4.0, ya, yb, zv)
        if rol == "pb":
            # Volado (marquesina): viguetas en voladizo, perpendiculares al muro
            vigueta_bovedilla(sufijo, "y", -1.2, 0.0, 0.0, 4.0, zv)
            b.nuevo(Floor, "losas_compresion", "", "OST_Floors", t_compresion,
                    [_caja(-0.1, -0.1, zv, 8.1, 10.1, z_tope), _caja(0.0, -1.2, zv, 4.0, -0.1, z_tope)])
        else:
            b.nuevo(Floor, "losas_pa", "", "OST_Floors", t_losa_azotea, [_caja(-0.1, -0.1, zv, 8.1, 10.1, z_tope)])
        return cols

    columnas_pb = planta("pb", 0.0, 2.6, 2.9, 3.0)
    # Dala de repartición y cerramiento de la puerta (planta baja)
    e = b.nuevo(FamilyInstance, "trabes_pb", "", "OST_StructuralFraming", t_dala,
                [_caja_lineal(0.0, 10.0, 4.0, 10.0, 0.15, 1.3, 1.4, recorte=0.125)])
    armazon.append((e, 0.125, 10.0, 3.875, 10.0, 1.3, 1.4))
    e = b.nuevo(FamilyInstance, "trabes_pb", "", "OST_StructuralFraming", t_cerr_puerta,
                [_caja_lineal(1.4, 0.0, 2.6, 0.0, 0.15, 2.1, 2.3)])
    armazon.append((e, 1.4, 0.0, 2.6, 0.0, 2.1, 2.3))
    columnas_pa = planta("pa", 3.0, 5.6, 5.9, 6.0)

    # Escalera de planta baja: 16 peraltes de 18 cm
    escalones = [_caja(6.6, 0.4 + i * 0.28, 0.0, 7.6, 0.4 + (i + 1) * 0.28, (i + 1) * 0.18)
                 for i in range(16)]
    b.nuevo(Stairs, "escaleras", "", "OST_Stairs", t_escalera, escalones)

    # Pretiles de azotea (solo perímetro)
    for x0, y0, x1, y1, perim in tramos:
        if perim:
            b.nuevo(Wall, "pretiles", "", "OST_Walls", t_pretil,
                    [_caja_lineal(x0, y0, x1, y1, 0.12, 6.0, 6.9)], materiales=[m_block])

    # Base de tinaco y tinaco en la azotea
    b.nuevo(Floor, "tinaco", "", "OST_Floors", t_base_tinaco, [_caja(6.3, 8.0, 6.0, 7.7, 9.4, 6.4)])
    b.nuevo(FamilyInstance, "tinaco", "", "OST_GenericModel", t_tinaco, [_caja(6.5, 8.2, 6.4, 7.5, 9.2, 7.6)])

    # Exteriores: banqueta (palabra clave) y patio (fuera de la huella, sin palabra clave)
    b.nuevo(Floor, "exteriores", "", "OST_Floors", t_banqueta, [_caja(-1.2, -3.0, 0.0, 12.0, -1.8, 0.1)])
    b.nuevo(Floor, "exteriores", "", "OST_Floors", t_patio, [_caja(8.8, 4.0, -0.1, 11.6, 7.0, 0.0)])

    # Una puerta (se oculta por categoría) y un muro provisional oculto en la vista base
    b.nuevo(FamilyInstance, "puertas", "", "OST_Doors", t_puerta, [_caja(1.55, -0.08, 0.0, 2.45, 0.08, 2.1)])
    oculto = b.nuevo(Wall, "muro_oculto_base", "Muro provisional", "OST_Walls", t_muro,
                     [_caja(10.0, 2.0, 0.0, 10.15, 6.0, 2.0)])

    # ---------------- Acero de refuerzo ----------------
    E = doc._elementos
    D = 0.006  # medio grueso de una varilla dibujada (m)

    def varilla_x(x0, x1, y, z):
        return _caja(x0, y - D, z - D, x1, y + D, z + D)

    def varilla_y(y0, y1, x, z):
        return _caja(x - D, y0, z - D, x + D, y1, z + D)

    def varilla_z(z0, z1, x, y):
        return _caja(x - D, y - D, z0, x + D, y + D, z1)

    def pasos(a, b_, sep):
        n = max(1, int(round((b_ - a) / sep)))
        return [a + (b_ - a) * k / float(n) for k in range(n + 1)]

    def en_m(i):
        (x0, y0, z0), (x1, y1, z1) = E[i]._cajas[0]
        return x0 / M, y0 / M, z0 / M, x1 / M, y1 / M, z1 / M

    def anillo(x0, y0, x1, y1, z):
        return [varilla_x(x0, x1, y0, z), varilla_x(x0, x1, y1, z),
                varilla_y(y0, y1, x0, z), varilla_y(y0, y1, x1, z)]

    def nueva_varilla(rol, cajas, anfitrion, clase=Rebar, cat="OST_Rebar", tipo=t_varilla):
        b.nuevo(clase, rol, "", cat, tipo, cajas, anfitrion=anfitrion)

    # Columnas y castillos: 4 longitudinales + estribos @ 20 cm
    for i in sum((b.ids[r] for r in ("columnas_pb", "castillos_pb", "columnas_pa", "castillos_pa")), []):
        x0, y0, z0, x1, y1, z1 = en_m(i)
        r = 0.035
        nueva_varilla("varillas", [varilla_z(z0, z1, x, y) for x in (x0 + r, x1 - r) for y in (y0 + r, y1 - r)], i)
        nueva_varilla("varillas", sum((anillo(x0 + r, y0 + r, x1 - r, y1 - r, z)
                                      for z in pasos(z0 + 0.1, z1 - 0.1, 0.2)), []), i)

    # Cadenas y trabes: 4 longitudinales + estribos @ 25 cm
    for e, x0, y0, x1, y1, z0, z1 in armazon:
        i, r = e.Id.Value, 0.035
        if y0 == y1:
            long_ = [varilla_x(x0, x1, y0 + s_, z) for s_ in (-0.075 + r, 0.075 - r) for z in (z0 + r, z1 - r)]
            estr = sum((anillo(x - D, y0 - 0.075 + r, x + D, y0 + 0.075 - r, z0 + r) +
                        [varilla_z(z0 + r, z1 - r, x, y0 + sg * (0.075 - r)) for sg in (-1, 1)]
                        for x in pasos(x0 + 0.1, x1 - 0.1, 0.25)), [])
        else:
            long_ = [varilla_y(y0, y1, x0 + s_, z) for s_ in (-0.075 + r, 0.075 - r) for z in (z0 + r, z1 - r)]
            estr = sum(([varilla_x(x0 - 0.075 + r, x0 + 0.075 - r, y, z0 + r),
                         varilla_x(x0 - 0.075 + r, x0 + 0.075 - r, y, z1 - r)] +
                        [varilla_z(z0 + r, z1 - r, x0 + sg * (0.075 - r), y) for sg in (-1, 1)]
                        for y in pasos(y0 + 0.1, y1 - 0.1, 0.25)), [])
        nueva_varilla("varillas", long_, i)
        nueva_varilla("varillas", estr, i)

    # Cimientos corridos: 3 longitudinales + transversales @ 25 cm en el lecho bajo
    for i in b.ids["corridos"]:
        x0, y0, z0, x1, y1, z1 = en_m(i)
        z = z0 + 0.06
        if (x1 - x0) > (y1 - y0):
            cajas = [varilla_x(x0, x1, y, z + 0.015) for y in pasos(y0 + 0.08, y1 - 0.08, 0.2)]
            cajas += [varilla_y(y0 + 0.05, y1 - 0.05, x, z) for x in pasos(x0 + 0.1, x1 - 0.1, 0.25)]
        else:
            cajas = [varilla_y(y0, y1, x, z + 0.015) for x in pasos(x0 + 0.08, x1 - 0.08, 0.2)]
            cajas += [varilla_x(x0 + 0.05, x1 - 0.05, y, z) for y in pasos(y0 + 0.1, y1 - 0.1, 0.25)]
        nueva_varilla("varillas", cajas, i)

    # Dados: parrilla inferior @ 15 cm en ambos sentidos
    for i in b.ids["dados"]:
        x0, y0, z0, x1, y1, z1 = en_m(i)
        z = z0 + 0.07
        cajas = [varilla_x(x0 + 0.05, x1 - 0.05, y, z) for y in pasos(y0 + 0.07, y1 - 0.07, 0.15)]
        cajas += [varilla_y(y0 + 0.05, y1 - 0.05, x, z + 0.015) for x in pasos(x0 + 0.07, x1 - 0.07, 0.15)]
        nueva_varilla("varillas", cajas, i)

    def refuerzo_area(i):
        x0, y0, z0, x1, y1, z1 = en_m(i)
        z = z0 + 0.03
        nueva_varilla("varillas_area", [varilla_x(x0 + 0.05, x1 - 0.05, y, z)
                                        for y in pasos(y0 + 0.1, y1 - 0.1, 0.3)], i, clase=RebarInSystem)
        nueva_varilla("varillas_area", [varilla_y(y0 + 0.05, y1 - 0.05, x, z + 0.015)
                                        for x in pasos(x0 + 0.1, x1 - 0.1, 0.3)], i, clase=RebarInSystem)

    def malla(i, sep):
        x0, y0, z0, x1, y1, z1 = en_m(i)
        z = z0 + 0.5 * (z1 - z0)
        cajas = [varilla_x(x0 + 0.05, x1 - 0.05, y, z) for y in pasos(y0 + 0.1, y1 - 0.1, sep)]
        cajas += [varilla_y(y0 + 0.05, y1 - 0.05, x, z + 0.012) for x in pasos(x0 + 0.1, x1 - 0.1, sep)]
        nueva_varilla("mallas", cajas, i, clase=FabricSheet, cat="OST_FabricReinforcement", tipo=t_malla)

    # Fondo y tapa de la cisterna: refuerzo de área @ 30 cm
    for i in b.ids["cisterna"]:
        if en_m(i)[5] - en_m(i)[2] < 1.0:
            refuerzo_area(i)
    # Capas de compresión de planta baja y azotea: malla
    for i in b.ids["losas_compresion"]:
        malla(i, 0.15)
    for i in b.ids["losas_pa"]:
        malla(i, 0.15)
    # Muros de cisterna: varillas verticales @ 25 cm
    for i in b.ids["cisterna"]:
        x0, y0, z0, x1, y1, z1 = en_m(i)
        if z1 - z0 < 1.0:
            continue  # fondo y tapa
        xc, yc = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        if (x1 - x0) > (y1 - y0):
            cajas = [varilla_z(z0 + 0.05, z1 - 0.05, x, yc) for x in pasos(x0 + 0.1, x1 - 0.1, 0.25)]
        else:
            cajas = [varilla_z(z0 + 0.05, z1 - 0.05, xc, y) for y in pasos(y0 + 0.1, y1 - 0.1, 0.25)]
        nueva_varilla("varillas", cajas, i)

    # Una varilla sin anfitrión DENTRO de una columna (se ubica por el concreto que la contiene)
    x0, y0, z0, x1, y1, z1 = en_m(b.ids["columnas_pb"][4])
    xc, yc = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    nueva_varilla("varillas_contenidas", [varilla_z(z0 + 0.2, z1 - 0.2, xc, yc)], None)
    # Y una fuera de todo concreto (queda como etapa "acero")
    nueva_varilla("varillas_sueltas", [_caja(9.0, 9.0, 0.0, 9.02, 9.02, 1.0)], None)

    # Vistas: base isométrica, una en perspectiva y una plantilla
    base = View3D(doc, doc._siguiente_id(), "{3D}")
    doc._agregar(base)
    base._ocultos.add(oculto.Id.Value)
    doc._agregar(View3D(doc, doc._siguiente_id(), "Cámara exterior", perspectiva=True))
    doc._agregar(View3D(doc, doc._siguiente_id(), "Plantilla 3D", plantilla=True))

    doc._ids_por_rol = b.ids
    return doc
