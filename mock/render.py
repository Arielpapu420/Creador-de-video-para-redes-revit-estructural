# -*- coding: utf-8 -*-
"""Dibujo de las cajas visibles de una vista simulada, con la misma cámara que Revit.

Proyección ortográfica con la Transform de la caja de recorte de la vista
(X derecha, Y arriba, Z hacia el observador) y algoritmo del pintor por cara.
Dos salidas: matplotlib (previa) y Pillow (rápido, para pruebas).
"""
import math

COLORES = {
    "OST_StructuralFoundation": (150, 140, 128),
    "OST_StructuralColumns": (120, 124, 130),
    "OST_StructuralFraming": (140, 146, 156),
    "OST_Walls": (206, 196, 180),
    "OST_Floors": (178, 182, 188),
    "OST_Stairs": (160, 150, 140),
    "OST_Rebar": (196, 70, 50),
    "OST_GenericModel": (196, 196, 190),
    "OST_Toposolid": (150, 170, 120),
    "OST_Doors": (130, 90, 60),
}
COLOR_OTRO = (180, 180, 180)
FONDO = (255, 255, 255)
LUZ = (0.35, -0.55, 0.76)  # dirección hacia el sol, fija en el mundo

_CARAS = [  # (índices de esquinas, normal)
    ((0, 1, 3, 2), (-1, 0, 0)), ((4, 6, 7, 5), (1, 0, 0)),
    ((0, 4, 5, 1), (0, -1, 0)), ((2, 3, 7, 6), (0, 1, 0)),
    ((0, 2, 6, 4), (0, 0, -1)), ((1, 5, 7, 3), (0, 0, 1)),
]


def _poligonos(doc, vista):
    """Lista de (profundidad, puntos 2D, color RGB 0-255) de las caras visibles."""
    from Autodesk.Revit.DB import ElementType, Level, View3D
    t = vista._transformacion()
    o, bx, by, bz = t.Origin, t.BasisX, t.BasisY, t.BasisZ
    ln = math.sqrt(sum(c * c for c in LUZ))
    luz = [c / ln for c in LUZ]
    hacia_ojo = (bz.X, bz.Y, bz.Z)
    caras = []
    for e in doc._elementos.values():
        if isinstance(e, (View3D, Level, ElementType)) or not e._cajas or not vista._es_visible(e):
            continue
        clave = e.Category.BuiltInCategory.nombre if e.Category is not None else ""
        base = COLORES.get(clave, COLOR_OTRO)
        for (x0, y0, z0), (x1, y1, z1) in e._cajas:
            esquinas = []
            for x in (x0, x1):
                for y in (y0, y1):
                    for z in (z0, z1):
                        dx, dy, dz = x - o.X, y - o.Y, z - o.Z
                        esquinas.append((dx * bx.X + dy * bx.Y + dz * bx.Z,
                                         dx * by.X + dy * by.Y + dz * by.Z,
                                         dx * bz.X + dy * bz.Y + dz * bz.Z))
            # Orden por caja (centro) y, dentro de la caja, solo caras de frente
            prof = sum(c[2] for c in esquinas) / 8.0
            for idx, n in _CARAS:
                if n[0] * hacia_ojo[0] + n[1] * hacia_ojo[1] + n[2] * hacia_ojo[2] <= 1e-9:
                    continue  # cara de espaldas
                k = 0.62 + 0.38 * max(0.0, n[0] * luz[0] + n[1] * luz[1] + n[2] * luz[2])
                color = tuple(min(255, int(c * k)) for c in base)
                pts = [(esquinas[i][0], esquinas[i][1]) for i in idx]
                caras.append((prof, pts, color))
    caras.sort(key=lambda c: c[0])  # de lejos (Z menor) a cerca; sort estable
    return caras


def _limites(vista):
    return vista._crop_min.X, vista._crop_max.X, vista._crop_min.Y, vista._crop_max.Y


def dibujar_pillow(doc, vista, ruta, ancho, alto, escala=1.0):
    from PIL import Image, ImageDraw
    w, h = max(2, int(round(ancho * escala))), max(2, int(round(alto * escala)))
    x0, x1, y0, y1 = _limites(vista)
    img = Image.new("RGB", (w, h), FONDO)
    d = ImageDraw.Draw(img)
    for _, pts, color in _poligonos(doc, vista):
        px = [((x - x0) / (x1 - x0) * w, (y1 - y) / (y1 - y0) * h) for x, y in pts]
        d.polygon(px, fill=color, outline=tuple(int(c * 0.55) for c in color))
    img.save(ruta)


_FIGURA = {}


def dibujar_matplotlib(doc, vista, ruta, ancho, alto, escala=1.0):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    w, h = max(2, int(round(ancho * escala))), max(2, int(round(alto * escala)))
    clave = (w, h)
    if clave not in _FIGURA:
        fig = plt.figure(figsize=(w / 100.0, h / 100.0), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        _FIGURA[clave] = (fig, ax)
    fig, ax = _FIGURA[clave]
    ax.clear()
    ax.set_axis_off()
    fig.patch.set_facecolor([c / 255.0 for c in FONDO])
    x0, x1, y0, y1 = _limites(vista)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    caras = _poligonos(doc, vista)
    if caras:
        colores = [[c / 255.0 for c in col] for _, _, col in caras]
        bordes = [[c / 255.0 * 0.55 for c in col] for _, _, col in caras]
        ax.add_collection(PolyCollection([pts for _, pts, _ in caras], facecolors=colores,
                                         edgecolors=bordes, linewidths=0.4 * escala + 0.2))
    fig.savefig(ruta, dpi=100, facecolor=fig.get_facecolor())
