# -*- coding: utf-8 -*-
"""Pruebas de punta a punta de nodo_video.py contra el simulador de la API (mock/),
de Video_Obra.dyn y de armar_video.py.

    python probar.py              -> todas las pruebas (incluye armar el MP4, ~1-2 min)
    python probar.py --sin-video  -> omite la prueba del MP4
    python probar.py --conservar  -> no borra la carpeta temporal (para revisar cuadros)

Sale con código 0 si todo pasa.
"""
import argparse
import json
import math
import os
import shutil
import sys
import tempfile
import time
import traceback

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "mock"))

import simulador          # noqa: E402
import modelo_sintetico   # noqa: E402
from Autodesk.Revit.DB import XYZ, DirectShape, Element, ElementType, View3D, ErrorRevit  # noqa: E402
from System.Collections.Generic import List  # noqa: E402

RUTA_NODO = os.path.join(AQUI, "nodo_video.py")
RUTA_DYN = os.path.join(AQUI, "Video_Obra.dyn")
RUTA_PIEZAS = os.path.join(AQUI, "nodo_piezas.py")
RUTA_DYN_PIEZAS = os.path.join(AQUI, "Piezas_Obra.dyn")

RESULTADOS = []


def prueba(fn):
    def envoltura(*a, **kw):
        t0 = time.time()
        try:
            fn(*a, **kw)
            RESULTADOS.append((fn.__name__, True, "", time.time() - t0))
            print("  OK    %s (%.1f s)" % (fn.__name__, time.time() - t0))
        except Exception:
            RESULTADOS.append((fn.__name__, False, traceback.format_exc(), time.time() - t0))
            print("  FALLA %s\n%s" % (fn.__name__, traceback.format_exc()))
    envoltura.__name__ = fn.__name__
    return envoltura


# -----------------------------------------------------------------------------
#  Utilidades
# -----------------------------------------------------------------------------

ROLES_ACERO = {"varillas", "varillas_area", "mallas", "varillas_contenidas", "varillas_sueltas"}
ROLES_NO_ESTRUCTURA = {"terreno", "genericos", "puertas", "muro_oculto_base", "tipos", "materiales"} | ROLES_ACERO
CADENA_ORDEN = [
    ["corridos"], ["dados"], ["mamposteria"], ["cisterna"], ["desplante"], ["firme"],
    ["columnas_pb", "castillos_pb"], ["muros_pb"], ["trabes_pb"], ["viguetas"], ["bovedillas"],
    ["losas_compresion"], ["escaleras"], ["columnas_pa", "castillos_pa"], ["muros_pa"],
    ["trabes_pa"], ["viguetas_pa"], ["bovedillas_pa"], ["losas_pa"], ["pretiles"], ["tinaco"], ["exteriores"],
]
# Etapa que debe asignar el nodo a cada rol del modelo sintético
ETAPA_ESPERADA = {
    "corridos": "cimentacion", "dados": "dados", "mamposteria": "mamposteria", "cisterna": "cisterna",
    "desplante": "desplante", "firme": "firme", "columnas_pb": "columnas", "castillos_pb": "columnas",
    "muros_pb": "muros", "trabes_pb": "trabes", "viguetas": "viguetas", "bovedillas": "bovedillas",
    "losas_compresion": "compresion", "escaleras": "escaleras",
    "columnas_pa": "columnas", "castillos_pa": "columnas", "muros_pa": "muros", "trabes_pa": "trabes",
    "viguetas_pa": "viguetas", "bovedillas_pa": "bovedillas", "losas_pa": "compresion", "pretiles": "muros", "tinaco": "tinaco", "exteriores": "exteriores",
}


def correr(carpeta, doc=None, acero=False, fps=15, duracion=30, grados=180, fallos=None,
           exportador=None, vista="{3D}", zoom=1.0):
    doc = doc or modelo_sintetico.crear_documento()
    simulador.reiniciar(doc, exportador=exportador or simulador.exportador_rapido, escala=0.125,
                        fallos=fallos)
    out, espacio = simulador.ejecutar_nodo(RUTA_NODO, [carpeta, vista, fps, duracion, grados, acero, zoom],
                                           devolver_espacio=True)
    return doc, out, espacio


def numero_cuadro(ruta):
    return int(os.path.basename(ruta)[6:11])


def ids_rol(doc, *roles):
    s = set()
    for r in roles:
        s.update(doc._ids_por_rol.get(r, []))
    return s


def estructura(doc):
    return set().union(*[set(v) for k, v in doc._ids_por_rol.items() if k not in ROLES_NO_ESTRUCTURA])


def primera_aparicion(exportes):
    primera = {}
    for ex in sorted(exportes, key=lambda e: numero_cuadro(e["ruta"])):
        n = numero_cuadro(ex["ruta"])
        for i in ex["visibles"]:
            primera.setdefault(i, n)
    return primera


def foto_vista(v):
    o = v._orient
    return (frozenset(v._ocultos), frozenset(v._cats_ocultas), repr(o.EyePosition), repr(o.ForwardDirection),
            repr(v._crop_min), repr(v._crop_max), v._crop_activa, v._nombre)


def leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return f.read()


# -----------------------------------------------------------------------------
#  Pruebas
# -----------------------------------------------------------------------------

@prueba
def trampas_pythonnet_en_simulador():
    """El simulador reproduce las trampas: si el nodo cayera en ellas, fallaría."""
    a, b = XYZ(1, 2, 3), XYZ(1, 1, 1)
    for op in (lambda: a + b, lambda: a - b, lambda: a * 2):
        try:
            op()
            raise AssertionError("XYZ no debería tener operadores")
        except TypeError:
            pass
    assert a.Add(b).X == 2 and a.CrossProduct(b).GetLength() > 0
    doc = modelo_sintetico.crear_documento()
    tipo = next(e for e in doc._elementos.values() if isinstance(e, ElementType))
    try:
        tipo.Name
        raise AssertionError("tipo.Name debería fallar")
    except AttributeError:
        pass
    assert Element.Name.GetValue(tipo) == tipo._nombre
    vista = next(e for e in doc._elementos.values() if isinstance(e, View3D) and e._nombre == "{3D}")
    doc._transaccion = True
    try:
        vista.HideElements([vista.Id])
        raise AssertionError("HideElements no debería aceptar listas de Python")
    except TypeError:
        pass
    doc._transaccion = False
    try:
        vista.HideElements(List[ElementType]())
        raise AssertionError("Cambiar la vista fuera de transacción debería fallar")
    except ErrorRevit:
        pass


@prueba
def corrida_completa_sin_acero(tmp):
    carpeta = os.path.join(tmp, "sin_acero")
    doc, out, esp = correr(carpeta)
    est = simulador.estado
    assert out == os.path.join(carpeta, "informe_video.txt"), out
    inf = leer(out)
    assert "ERRORES (0)" in inf, inf[-3000:]
    assert "Exportados en esta corrida: 450" in inf
    assert len(est.exportes) == 450
    assert est.modificaciones_modelo == [], est.modificaciones_modelo
    pngs = sorted(f for f in os.listdir(carpeta) if f.endswith(".png"))
    assert len(pngs) == 450 and pngs[0] == "frame_00001 - Vista 3D - VIDEO OBRA.png", pngs[:2]
    guion = json.load(open(os.path.join(carpeta, "guion_video.json"), encoding="utf-8"))
    assert guion["cuadros_total"] == 450 and len(guion["cuadros"]) == 450
    # Lectura del nombre de tipo sin tipo.Name
    dado = doc._elementos[doc._ids_por_rol["dados"][0]]
    assert esp["nombre_tipo"](doc, dado) == "Dado 60x60x60"
    # Tamaño de imagen 1080x1920 (9:16 con PixelSize 1920 vertical)
    assert all(e["alto"] == 1920 and e["ancho"] == 1080 for e in est.exportes)
    assert all(e["crop_activa"] for e in est.exportes)


@prueba
def no_toca_modelo_ni_vista_base(tmp):
    doc = modelo_sintetico.crear_documento()
    base = next(e for e in doc._elementos.values() if isinstance(e, View3D) and e._nombre == "{3D}")
    antes_ids = set(doc._elementos)
    antes_base = foto_vista(base)
    antes_cajas = {k: list(e._cajas) for k, e in doc._elementos.items()}
    correr(os.path.join(tmp, "intacto"), doc=doc, fps=5, duracion=6)
    nuevos = set(doc._elementos) - antes_ids
    assert len(nuevos) == 1 and isinstance(doc._elementos[nuevos.pop()], View3D)
    assert set(doc._elementos) >= antes_ids, "se borraron elementos"
    assert foto_vista(base) == antes_base, "cambió la vista base"
    assert all(doc._elementos[k]._cajas == v for k, v in antes_cajas.items())
    assert simulador.estado.modificaciones_modelo == []
    videos = [e for e in doc._elementos.values() if isinstance(e, View3D) and e._nombre == "VIDEO OBRA"]
    assert len(videos) == 1


@prueba
def secuencia_de_obra(tmp):
    doc, out, _ = correr(os.path.join(tmp, "secuencia"))
    ex = sorted(simulador.estado.exportes, key=lambda e: numero_cuadro(e["ruta"]))
    est = estructura(doc)
    base = ids_rol(doc, "genericos")
    nunca = ids_rol(doc, "puertas", "muro_oculto_base", "terreno", *ROLES_ACERO)
    previo = set()
    for e in ex:
        n, vis = numero_cuadro(e["ruta"]), set(e["visibles"])
        t = (n - 1) / 15.0
        assert base <= vis, "los genéricos sin regla deben verse siempre (cuadro %d)" % n
        assert not (vis & nunca), "cuadro %d muestra elementos que deben quedar ocultos" % n
        obra = vis & est
        if t < 1.5:
            assert not obra, "antes de 1.5 s no debe verse obra (cuadro %d)" % n
        if t >= 24.0:
            assert obra == est, "desde 24 s debe verse toda la estructura (cuadro %d)" % n
        assert previo <= obra, "la obra no puede 'desconstruirse' (cuadro %d)" % n
        previo = obra
    assert any(0 < len(set(e["visibles"]) & est) < len(est) for e in ex)

    primera = primera_aparicion(ex)
    for a, b in zip(CADENA_ORDEN[:-1], CADENA_ORDEN[1:]):
        fa = [primera[i] for i in ids_rol(doc, *a)]
        fb = [primera[i] for i in ids_rol(doc, *b)]
        assert max(fa) <= min(fb), "%s debe terminar antes de que empiece %s" % (a, b)
    # Crecimiento gradual, no de golpe
    for rol in ("dados", "muros_pb", "muros_pa", "trabes_pb", "viguetas"):
        cuadros = set(primera[i] for i in ids_rol(doc, rol))
        assert len(cuadros) >= 4, "%s aparece de golpe (%d cuadros distintos)" % (rol, len(cuadros))


@prueba
def camara_y_encuadre(tmp):
    doc, out, _ = correr(os.path.join(tmp, "camara"), acero=True, exportador=simulador.exportador_vacio)
    ex = sorted(simulador.estado.exportes, key=lambda e: numero_cuadro(e["ruta"]))
    # El encuadre incluye el acero y deja fuera los exteriores (banqueta, patio)
    est = (estructura(doc) | ids_rol(doc, *ROLES_ACERO)) - ids_rol(doc, "exteriores")
    cajas = [c for i in est for c in doc._elementos[i]._cajas]
    xs = [c[k][0] for c in cajas for k in (0, 1)]
    ys = [c[k][1] for c in cajas for k in (0, 1)]
    zs = [c[k][2] for c in cajas for k in (0, 1)]
    centro = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)
    esquinas = [(x, y, z) for x in (min(xs), max(xs)) for y in (min(ys), max(ys)) for z in (min(zs), max(zs))]
    azs, tam = [], None
    for e in ex:
        o = e["orientacion"]
        f, u, ojo = o.ForwardDirection, o.UpDirection, o.EyePosition
        r = f.CrossProduct(u)
        assert abs(f.DotProduct(u)) < 1e-9
        assert abs(math.degrees(math.asin(-f.Z)) - 30.0) < 1e-6, "elevación isométrica de 30°"
        assert abs(u.Z) > 0.5, "la vertical de la imagen debe ser la Z del modelo"
        azs.append(math.degrees(math.atan2(-f.Y, -f.X)))
        cmin, cmax = e["crop"]
        w, h = cmax.X - cmin.X, cmax.Y - cmin.Y
        assert abs(w / h - 9 / 16.0) < 1e-9, "caja de recorte 9:16"
        tam = tam or (w, h)
        assert abs(w - tam[0]) < 1e-6 and abs(h - tam[1]) < 1e-6, "el encuadre no debe hacer zoom"
        for p in esquinas:
            d = (p[0] - ojo.X, p[1] - ojo.Y, p[2] - ojo.Z)
            x = d[0] * r.X + d[1] * r.Y + d[2] * r.Z
            y = d[0] * u.X + d[1] * u.Y + d[2] * u.Z
            assert cmin.X < x < cmax.X and cmin.Y < y < cmax.Y, "la estructura se sale del cuadro"
        # El centro de la estructura queda al centro del cuadro
        d = (centro[0] - ojo.X, centro[1] - ojo.Y, centro[2] - ojo.Z)
        cx = d[0] * r.X + d[1] * r.Y + d[2] * r.Z
        cy = d[0] * u.X + d[1] * u.Y + d[2] * u.Z
        assert abs(cx - (cmin.X + cmax.X) / 2) < 1e-6 and abs(cy - (cmin.Y + cmax.Y) / 2) < 1e-6
    giro = [azs[0]]
    for a in azs[1:]:
        while a - giro[-1] > 180:
            a -= 360
        while a - giro[-1] < -180:
            a += 360
        giro.append(a)
    assert abs(giro[0] - (-45.0)) < 1e-6 and abs(giro[-1] - giro[0] - 180.0) < 1e-6, (giro[0], giro[-1])
    assert all(b >= a - 1e-9 for a, b in zip(giro, giro[1:])), "el giro debe ser continuo en un sentido"
    # Zoom 2: misma cámara y mismo centro, caja de recorte de la mitad
    correr(os.path.join(tmp, "camara_zoom"), acero=True, zoom=2.0, exportador=simulador.exportador_vacio)
    cmin, cmax = simulador.estado.exportes[0]["crop"]
    assert abs((cmax.X - cmin.X) - tam[0] / 2.0) < 1e-6 and abs((cmax.Y - cmin.Y) - tam[1] / 2.0) < 1e-6


@prueba
def transacciones(tmp):
    correr(os.path.join(tmp, "trans"), fps=5, duracion=4)
    reg = [r[0] for r in simulador.estado.registro]
    # El simulador lanza error si ExportImage ocurre con transacción abierta;
    # aquí además se comprueba el patrón Ensure -> Regenerate -> TaskDone -> ForceClose
    assert reg.count("EnsureInTransaction") == 1 + 20
    assert reg.count("TransactionTaskDone") == reg.count("EnsureInTransaction")
    assert reg.count("ForceCloseTransaction") >= reg.count("EnsureInTransaction")
    assert "Regenerate" in reg


@prueba
def clasificacion_de_detalles(tmp):
    """Cada rol del modelo cae en su etapa: piedra por material, viguetas por tamaño, etc."""
    doc, out, esp = correr(os.path.join(tmp, "clasificacion"), acero=True, fps=2, duracion=4,
                           exportador=simulador.exportador_vacio)
    base = next(e for e in doc._elementos.values() if isinstance(e, View3D) and e._nombre == "{3D}")
    inf = esp["Informe"]()
    niveles = esp["leer_niveles"](doc)
    piezas, _ = esp["ordenar_piezas"](esp["recoger_piezas"](doc, base, True, inf), niveles, inf)
    etapa = {p.clave: (p.etapa, p.nivel) for p in piezas}
    for rol, esperada in ETAPA_ESPERADA.items():
        for i in doc._ids_por_rol[rol]:
            assert i in etapa, "%s (%d) no entró a la secuencia" % (rol, i)
            assert etapa[i][0] == esperada, "%s cayó en %s, se esperaba %s" % (rol, etapa[i][0], esperada)
    assert all(etapa[i][1] == len(niveles) for i in ids_rol(doc, "exteriores")), "exteriores al final"
    assert not (ids_rol(doc, "genericos") & set(etapa)), "los genéricos sin regla quedan como base"
    assert not [p for p in piezas if p.etapa == "otros"]
    # El tipo de la mampostería NO dice piedra: se reconoció por el material
    muro = next(p for p in piezas if p.clave == doc._ids_por_rol["mamposteria"][0])
    assert "piedra" not in muro.tipo.lower() and "Piedra braza" in muro.materiales
    # Las viguetas tampoco dicen vigueta: se reconocieron por tamaño
    vig = next(p for p in piezas if p.clave == doc._ids_por_rol["viguetas"][0])
    assert "vigueta" not in vig.texto
    # La capa de compresión de azotea no dice "compresión": se reconoció por estar sobre viguetas
    capa = next(p for p in piezas if p.clave == doc._ids_por_rol["losas_pa"][0])
    assert "compresion" not in capa.texto
    rep = leer(out)
    assert "TIPOS DE REVIT POR ETAPA" in rep and "Muro estructural 50 cm  · materiales: Piedra braza" in rep


@prueba
def armado_antes_del_concreto(tmp):
    doc, out, _ = correr(os.path.join(tmp, "acero"), acero=True, exportador=simulador.exportador_vacio)
    est = simulador.estado
    inf = leer(out)
    assert "ERRORES (0)" in inf, inf[-3000:]
    assert "Armadura estructural" in inf and "Malla electrosoldada" in inf
    assert est.modificaciones_modelo == [], "el acero solo admite ajustes gráficos de vista"
    ex = sorted(est.exportes, key=lambda e: numero_cuadro(e["ruta"]))
    primera = primera_aparicion(ex)
    acero = ids_rol(doc, *ROLES_ACERO)
    assert acero <= set(primera), "todo el acero debe aparecer"

    # Etapa (índice en CADENA_ORDEN) de cada rol de concreto
    etapa_de_rol = {r: k for k, grupo in enumerate(CADENA_ORDEN) for r in grupo}
    rol_de = {i: r for r, ids in doc._ids_por_rol.items() for i in ids}

    def rango_concreto(k):
        fs = [primera[i] for i in ids_rol(doc, *CADENA_ORDEN[k])]
        return min(fs), max(fs)

    con_anfitrion = ids_rol(doc, "varillas", "varillas_area", "mallas")
    assert ids_rol(doc, "varillas_area") and ids_rol(doc, "mallas")
    for i in con_anfitrion:
        k = etapa_de_rol[rol_de[doc._elementos[i]._anfitrion]]
        ini_k, _ = rango_concreto(k)
        assert primera[i] <= ini_k, "el acero %d debe aparecer antes que el concreto de su etapa" % i
        if k > 0:
            assert primera[i] >= rango_concreto(k - 1)[1], \
                "el acero %d no debe aparecer antes de terminar la etapa anterior" % i
    # Varilla sin anfitrión dentro de una columna: se ubica en el armado de columnas
    k = etapa_de_rol["columnas_pb"]
    for i in ids_rol(doc, "varillas_contenidas"):
        assert rango_concreto(k - 1)[1] <= primera[i] <= rango_concreto(k)[0]

    # El acero queda "sin obstrucciones" y "como sólido" SOLO en la vista de video,
    # y vuelve a quedar obstruido (tapado) cuando aparece su concreto
    vista_video = ex[0]["vista"]
    assert {a[1] for a in est.ajustes_acero} == {vista_video}
    assert {a[2] for a in est.ajustes_acero} == {"SetUnobscuredInView", "SetSolidInView"}
    contenida = ids_rol(doc, "varillas_contenidas")
    cubre = {i: doc._elementos[i]._anfitrion for i in acero if doc._elementos[i]._anfitrion}
    for i in contenida:
        cubre[i] = doc._ids_por_rol["columnas_pb"][4]
    tapados = 0
    for e in ex:
        vis, libres = set(e["visibles"]), set(e["sin_obstruccion"])
        for i in acero & vis:
            concreto = cubre.get(i)
            if concreto is not None and concreto in vis:
                assert i not in libres, "el acero %d debe quedar tapado por su concreto" % i
                tapados += 1
            else:
                assert i in libres, "el acero %d debe verse mientras su concreto no aparece" % i
    assert tapados > 0
    final = ex[-1]
    assert set(final["sin_obstruccion"]) == ids_rol(doc, "varillas_sueltas"), "solo el acero sin concreto queda libre"
    # Una vez colocado, el armado sigue visible hasta el final
    previo = set()
    for e in ex:
        actual = set(e["visibles"]) & acero
        assert previo <= actual
        previo = actual
    assert previo == acero

    # Reanudar con acero: el estado tapado/destapado es el mismo que sin cortes
    ref = {numero_cuadro(e["ruta"]): (e["visibles"], e["sin_obstruccion"]) for e in ex}
    carpeta_r = os.path.join(tmp, "acero_reanudar")
    try:
        correr(carpeta_r, acero=True, fallos={200: "caida"}, exportador=simulador.exportador_vacio)
        raise AssertionError("la caída simulada debería interrumpir el nodo")
    except simulador.CaidaDeRevit:
        pass
    correr(carpeta_r, acero=True, exportador=simulador.exportador_vacio)
    reanudados = {numero_cuadro(e["ruta"]): (e["visibles"], e["sin_obstruccion"])
                  for e in simulador.estado.exportes}
    assert min(reanudados) == 200 and len(reanudados) == 251
    for n, estado_cuadro in reanudados.items():
        assert estado_cuadro == ref[n], "el cuadro %d reanudado difiere en acero visible/tapado" % n

    # Una segunda corrida sin acero sobre la misma vista vuelve a ocultar sus categorías
    correr(os.path.join(tmp, "acero_luego_sin"), doc=doc, acero=False, fps=5, duracion=6)
    ult = simulador.estado.exportes[-1]
    assert not (set(ult["visibles"]) & acero)


@prueba
def reanudable_tras_cierre_de_revit(tmp):
    carpeta = os.path.join(tmp, "reanudar")
    doc = modelo_sintetico.crear_documento()
    try:
        correr(carpeta, doc=doc, fallos={120: "caida"})
        raise AssertionError("la caída simulada debería interrumpir el nodo")
    except simulador.CaidaDeRevit:
        pass
    hechos = [f for f in os.listdir(carpeta) if f.endswith(".png")]
    assert len(hechos) == 119, len(hechos)
    # Revit se reabre sin guardar: documento nuevo (la vista se vuelve a crear)
    doc2, out, _ = correr(carpeta, doc=modelo_sintetico.crear_documento())
    inf = leer(out)
    assert "Ya existían (saltados):     119" in inf and "Exportados en esta corrida: 331" in inf, inf[:2500]
    assert len([f for f in os.listdir(carpeta) if f.endswith(".png")]) == 450
    # Tercera corrida con la vista ya existente: la reutiliza y no exporta nada
    n_vistas = sum(1 for e in doc2._elementos.values() if isinstance(e, View3D))
    _, out, _ = correr(carpeta, doc=doc2)
    assert sum(1 for e in doc2._elementos.values() if isinstance(e, View3D)) == n_vistas
    inf = leer(out)
    assert "ya existía: se reutiliza" in inf and "Exportados en esta corrida: 0" in inf
    # Los cuadros reanudados son idénticos a los de una corrida sin cortes
    ref = os.path.join(tmp, "sin_cortes")
    correr(ref)
    for n in (1, 119, 120, 121, 300, 450):
        nombre = "frame_%05d - Vista 3D - VIDEO OBRA.png" % n
        with open(os.path.join(carpeta, nombre), "rb") as fa, open(os.path.join(ref, nombre), "rb") as fb:
            assert fa.read() == fb.read(), "el cuadro %d reanudado difiere del de referencia" % n


@prueba
def error_en_un_cuadro_queda_en_informe(tmp):
    carpeta = os.path.join(tmp, "error")
    _, out, _ = correr(carpeta, fps=5, duracion=6, fallos={7: "error"})
    inf = leer(out)
    assert "Con error:                  1" in inf and "Traceback" in inf and "Cuadro 7" in inf, inf
    _, out, _ = correr(carpeta, fps=5, duracion=6)
    inf = leer(out)
    assert "Exportados en esta corrida: 1" in inf and "ERRORES (0)" in inf


@prueba
def entradas_invalidas_dan_informe(tmp):
    _, out, _ = correr(os.path.join(tmp, "sin_vista"), vista="No existe")
    inf = leer(out)
    assert "No existe la vista 3D 'No existe'" in inf and "{3D}" in inf
    _, out, _ = correr(os.path.join(tmp, "perspectiva"), vista="Cámara exterior")
    assert "perspectiva" in leer(out)
    assert simulador.estado.exportes == []


@prueba
def piezas_solo_en_copia_video():
    doc = modelo_sintetico.crear_documento("Casa original")
    simulador.reiniciar(doc)
    antes = len(doc._elementos)
    out = simulador.ejecutar_nodo(RUTA_PIEZAS, [])
    assert out.startswith("NO SE HIZO NADA") and len(doc._elementos) == antes
    assert simulador.estado.piezas_creadas == 0
    # Una CARPETA llamada VIDEO no habilita el modelo original: solo cuenta el nombre del archivo
    doc = modelo_sintetico.crear_documento("Casa original")
    doc.PathName = "C:\\Proyectos\\VIDEO\\Casa original.rvt"
    simulador.reiniciar(doc)
    out = simulador.ejecutar_nodo(RUTA_PIEZAS, [])
    assert out.startswith("NO SE HIZO NADA") and len(doc._elementos) == antes, out[:200]
    # La copia en esa misma carpeta sí trabaja
    doc = modelo_sintetico.crear_documento("Casa original_VIDEO")
    doc.PathName = "C:\\Proyectos\\VIDEO\\Casa original_VIDEO.rvt"
    simulador.reiniciar(doc)
    out = simulador.ejecutar_nodo(RUTA_PIEZAS, [])
    assert not out.startswith("NO SE HIZO NADA") and simulador.estado.piezas_creadas > 0, out[:200]


def piezas_de(doc):
    """{clave pieza: (tipo, muro, hilada)} de las DirectShape VIDEO_OBRA."""
    res = {}
    for k, e in doc._elementos.items():
        if isinstance(e, DirectShape) and e.ApplicationId == "VIDEO_OBRA":
            _, tipo, muro, hilada, _ = e.ApplicationDataId.split("|")
            res[k] = (tipo, int(muro), int(hilada))
    return res


def _cruce(a, b, tol=0.002 * modelo_sintetico.M):
    """True si dos cajas se traslapan más que la tolerancia en los tres ejes."""
    return all(min(a[1][i], b[1][i]) - max(a[0][i], b[0][i]) > tol for i in range(3))


@prueba
def piezas_block_y_piedra():
    M = modelo_sintetico.M
    doc = modelo_sintetico.crear_documento()
    originales = {k: list(e._cajas) for k, e in doc._elementos.items()}
    simulador.reiniciar(doc)
    out = simulador.ejecutar_nodo(RUTA_PIEZAS, [40, 20, 12, 1, True, False])
    assert "ERROR" not in out and "omitidos" not in out, out
    assert simulador.estado.modificaciones_modelo == []
    assert all(doc._elementos[k]._cajas == v for k, v in originales.items()), "cambió un elemento original"
    piezas = piezas_de(doc)
    por_muro = {}
    for k, (tipo, muro, hilada) in piezas.items():
        por_muro.setdefault(muro, []).append((k, tipo, hilada))
    for rol in ("muros_pb", "muros_pa", "pretiles"):
        for m in doc._ids_por_rol[rol]:
            assert m in por_muro and {t for _, t, _ in por_muro[m]} == {"block"}, rol
    for m in doc._ids_por_rol["mamposteria"]:
        assert {t for _, t, _ in por_muro[m]} == {"piedra", "mortero"}
    assert not (ids_rol(doc, "cisterna", "corridos") & set(por_muro)), "la cisterna y el concreto no se convierten"
    # Blocks de 39 x 19 cm (12x20x40 con junta de 1 cm), 13 hiladas en un muro de 2.6 m;
    # en el muro con dala de repartición, la hilada que ocupa la dala no lleva blocks
    dala = next(iter(ids_rol(doc, "trabes_pb") & {i for i in doc._ids_por_rol["trabes_pb"]
                                                  if doc._elementos[i]._cajas[0][1][2] < 1.5 * M}))
    for m in doc._ids_por_rol["muros_pb"]:
        hiladas = {h for _, _, h in por_muro[m]}
        assert max(hiladas) == 12, max(hiladas)  # 13 hiladas (la dala ocupa una en su muro)
        (mx0, my0, _), (mx1, my1, _) = doc._elementos[m]._cajas[0]
        en_x = (mx1 - mx0) >= (my1 - my0)  # el muro corre en X
        for k, _, _ in por_muro[m]:
            (x0, y0, z0), (x1, y1, z1) = doc._elementos[k]._cajas[0]
            largo, espesor = (x1 - x0, y1 - y0) if en_x else (y1 - y0, x1 - x0)
            assert 0.05 * M - 1e-6 <= largo <= 0.39 * M + 1e-6 and z1 - z0 <= 0.19 * M + 1e-6
            assert abs(espesor - 0.12 * M) < 1e-6
    muro_dala = next(m for m in doc._ids_por_rol["muros_pb"]
                     if _cruce(doc._elementos[m]._cajas[0], doc._elementos[dala]._cajas[0]))
    assert len({h for _, _, h in por_muro[muro_dala]}) == 12
    # Cuatrapeado: las juntas verticales de dos hiladas seguidas no coinciden
    m = doc._ids_por_rol["muros_pb"][0]
    juntas = {}
    for k, _, h in por_muro[m]:
        (x0, _, _), (x1, _, _) = doc._elementos[k]._cajas[0]
        juntas.setdefault(h, set()).add(round(x1 / M, 3))
    assert len(juntas[0] & juntas[1]) <= 1
    # Ninguna pieza invade castillos, columnas, dalas, cerramientos o la puerta
    obst = [doc._elementos[i]._cajas[0] for i in
            ids_rol(doc, "columnas_pb", "castillos_pb", "columnas_pa", "castillos_pa", "trabes_pb", "puertas")]
    for k in piezas:
        c = doc._elementos[k]._cajas[0]
        assert not any(_cruce(c, o) for o in obst), "la pieza %d invade un obstáculo" % k
    # Las piezas no se encimen entre sí (el mortero va dentro de la hilada de piedra)
    for muro, lista in por_muro.items():
        cajas = [(doc._elementos[k]._cajas[0], t) for k, t, _ in lista if t != "mortero"]
        for i in range(len(cajas)):
            for j in range(i + 1, len(cajas)):
                assert not _cruce(cajas[i][0], cajas[j][0]), "piezas encimadas en el muro %d" % muro
    # Volver a correr reemplaza las piezas; "solo borrar" las quita todas
    n = len(piezas)
    simulador.ejecutar_nodo(RUTA_PIEZAS, [40, 20, 12, 1, True, False])
    assert len(piezas_de(doc)) == n
    out = simulador.ejecutar_nodo(RUTA_PIEZAS, [40, 20, 12, 1, True, True])
    assert "borradas: %d" % n in out and not piezas_de(doc)
    assert simulador.estado.modificaciones_modelo == []


@prueba
def video_con_piezas_hilada_por_hilada(tmp):
    doc = modelo_sintetico.crear_documento()
    simulador.reiniciar(doc)
    simulador.ejecutar_nodo(RUTA_PIEZAS, [])
    piezas = piezas_de(doc)
    _, out, _ = correr(os.path.join(tmp, "piezas"), doc=doc, acero=True, exportador=simulador.exportador_vacio)
    inf = leer(out)
    assert "ERRORES (0)" in inf and "Muros sustituidos por piezas" in inf, inf[-3000:]
    ex = sorted(simulador.estado.exportes, key=lambda e: numero_cuadro(e["ruta"]))
    primera = primera_aparicion(ex)
    muros = ids_rol(doc, "muros_pb", "muros_pa", "pretiles", "mamposteria")
    huerfanas = {k for k, (_, m, _) in piezas.items() if m in ids_rol(doc, "muro_oculto_base")}
    for e in ex:
        assert not (set(e["visibles"]) & (muros | huerfanas)), "un muro sólido o una pieza huérfana se ve"
    assert set(piezas) - huerfanas <= set(primera), "todas las piezas se colocan"

    def hiladas(rol):
        res = {}
        for k, (tipo, m, h) in piezas.items():
            if m in ids_rol(doc, rol):
                res.setdefault(h, []).append((primera[k], tipo))
        return res

    for rol in ("muros_pb", "muros_pa", "mamposteria"):
        hs = hiladas(rol)
        for h in range(max(hs)):
            assert max(f for f, _ in hs[h]) <= min(f for f, _ in hs[h + 1]), \
                "%s: la hilada %d debe terminar antes de empezar la %d" % (rol, h, h + 1)
    for h, lista in hiladas("mamposteria").items():
        assert min(f for f, t in lista if t == "mortero") <= min(f for f, t in lista if t == "piedra")
    # Las piezas van en la etapa de su muro: después de castillos y antes de trabes
    pb = [primera[k] for k, (_, m, _) in piezas.items() if m in ids_rol(doc, "muros_pb")]
    assert max(primera[i] for i in ids_rol(doc, "castillos_pb")) <= min(pb)
    assert max(pb) <= min(primera[i] for i in ids_rol(doc, "trabes_pb"))
    piedra = [primera[k] for k, (t, m, _) in piezas.items() if m in ids_rol(doc, "mamposteria")]
    assert max(primera[i] for i in ids_rol(doc, "dados")) <= min(piedra)
    assert max(piedra) <= min(primera[i] for i in ids_rol(doc, "cisterna"))


def _verificar_dyn(ruta_dyn, ruta_nodo, tipos_esperados):
    with open(ruta_dyn, encoding="utf-8") as f:
        g = json.load(f)
    with open(ruta_nodo, encoding="utf-8") as f:
        codigo = f.read()
    py = [n for n in g["Nodes"] if n["ConcreteType"].startswith("PythonNodeModels.PythonNode")]
    assert len(py) == 1
    py = py[0]
    assert py["Engine"] == "CPython3"
    assert py["Code"] == codigo, "el código de %s difiere de %s: corre generar_dyn.py" % (
        os.path.basename(ruta_dyn), os.path.basename(ruta_nodo))
    assert [p["Name"] for p in py["Inputs"]] == ["IN[%d]" % i for i in range(len(tipos_esperados))]
    salidas = {p["Id"]: n for n in g["Nodes"] for p in n["Outputs"]}
    entradas = {p["Id"] for p in py["Inputs"]}
    conectados = {c["End"]: salidas[c["Start"]] for c in g["Connectors"]}
    assert set(conectados) == entradas, "cada IN[i] debe tener su nodo de entrada"
    tipos = [conectados[p["Id"]]["ConcreteType"].split(",")[0].split(".")[-1] for p in py["Inputs"]]
    assert tipos == tipos_esperados, tipos
    ids_vista = {v["Id"] for v in g["View"]["NodeViews"]}
    assert ids_vista == {n["Id"] for n in g["Nodes"]}
    assert g["View"]["Dynamo"]["RunType"] == "Manual"
    assert len(g["Inputs"]) == len(tipos_esperados)
    return py, conectados


@prueba
def grafo_dyn_valido():
    py, conectados = _verificar_dyn(RUTA_DYN, RUTA_NODO, ["StringInput"] * 2 + ["DoubleInput"] * 3 + ["BoolSelector", "DoubleInput"])
    assert conectados[py["Inputs"][5]["Id"]]["InputValue"] is True, "el acero debe venir activado por defecto"
    assert conectados[py["Inputs"][3]["Id"]]["InputValue"] == 60.0, "duración por defecto: 60 s"
    py, conectados = _verificar_dyn(RUTA_DYN_PIEZAS, RUTA_PIEZAS, ["DoubleInput"] * 4 + ["BoolSelector"] * 2)
    assert [conectados[p["Id"]]["InputValue"] for p in py["Inputs"]] == [40.0, 20.0, 12.0, 1.0, True, False]


@prueba
def armar_video_mp4(tmp):
    import armar_video
    import imageio_ffmpeg
    carpeta = os.path.join(tmp, "video")
    correr(carpeta, acero=True, exportador=simulador.exportador_vacio)
    r = armar_video.armar(carpeta, progreso=False)
    assert not r["faltantes"]
    nombres = sorted(f for f in os.listdir(carpeta) if f.endswith(".png"))
    assert nombres[0] == "frame_00001.png" and nombres[-1] == "frame_00450.png", "renombrado"
    lector = imageio_ffmpeg.read_frames(r["salida"])
    meta = next(lector)
    lector.close()
    assert meta["codec"].startswith("h264"), meta["codec"]
    assert meta["pix_fmt"].startswith("yuv420p"), meta["pix_fmt"]
    assert tuple(meta["size"]) == (1080, 1920), meta["size"]
    assert abs(meta["fps"] - 30) < 1e-6
    n, seg = imageio_ffmpeg.count_frames_and_secs(r["salida"])
    assert n == 900 and abs(seg - 30.0) < 0.1, (n, seg)


@prueba
def rotulos_y_orden_de_archivos(tmp):
    import armar_video
    carpeta = os.path.join(tmp, "rotulos")
    correr(carpeta, exportador=simulador.exportador_vacio)
    guion = armar_video.leer_guion(carpeta)
    textos = armar_video.rotulos_por_cuadro(guion, 450)
    secuencia = []
    for t in textos:
        if t and (not secuencia or secuencia[-1] != t):
            secuencia.append(t)
    esperado = ["Cimentación", "Cimiento de mampostería", "Cisterna", "Cimentación", "Firme",
                "Castillos y columnas", "Muros", "Trabes y cadenas", "Vigueta y bovedilla",
                "Capa de compresión", "Escalera", "Planta alta", "Azotea", "Tinaco", "Exteriores"]
    assert secuencia == esperado, secuencia
    assert all(t == "" for t in textos[:22]) and all(t == "" for t in textos[361:])
    # Con acero: cada etapa con armado muestra primero su rótulo de armado
    carpeta = os.path.join(tmp, "rotulos_acero")
    correr(carpeta, acero=True, exportador=simulador.exportador_vacio)
    textos = armar_video.rotulos_por_cuadro(armar_video.leer_guion(carpeta), 450)
    secuencia = []
    for t in textos:
        if t and (not secuencia or secuencia[-1] != t):
            secuencia.append(t)
    esperado = ["Armado de cimentación", "Cimentación"] * 2 + [
        "Cimiento de mampostería", "Armado de cisterna", "Cisterna", "Armado de cimentación", "Cimentación",
        "Firme", "Armado de castillos y columnas", "Castillos y columnas", "Muros", "Armado de trabes y cadenas",
        "Trabes y cadenas", "Vigueta y bovedilla", "Malla de compresión", "Capa de compresión", "Escalera",
        "Armado planta alta",
        "Planta alta", "Armado planta alta", "Planta alta", "Azotea", "Armado de azotea", "Azotea", "Tinaco",
        "Exteriores"]
    assert secuencia == esperado, secuencia
    # Orden numérico sin depender del sufijo de Revit, con un duplicado más reciente
    d = os.path.join(tmp, "nombres")
    os.makedirs(d)
    for nombre in ("frame_00010 - 3D View - X.png", "frame_00002 - Vista 3D - Y.png", "frame_00001.png",
                   "frame_00002.png", "otro.png", "frame_0003.png"):
        with open(os.path.join(d, nombre), "wb") as f:
            f.write(b"x")
        time.sleep(0.01)
    r = armar_video.ordenar_y_renombrar(d)
    assert list(r) == [1, 2, 10]
    assert [os.path.basename(v) for v in r.values()] == ["frame_00001.png", "frame_00002.png",
                                                         "frame_00010.png"]
    # El duplicado más viejo no se borra: solo se ignora
    assert sorted(os.listdir(d)) == ["frame_00001.png", "frame_00002 - Vista 3D - Y.png", "frame_00002.png",
                                     "frame_00010.png", "frame_0003.png", "otro.png"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-video", action="store_true", help="Omitir la prueba que arma el MP4")
    ap.add_argument("--conservar", action="store_true", help="No borrar la carpeta temporal")
    args = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="prueba_video_obra_")
    print("Carpeta temporal: %s" % tmp)
    t0 = time.time()
    trampas_pythonnet_en_simulador()
    corrida_completa_sin_acero(tmp)
    no_toca_modelo_ni_vista_base(tmp)
    secuencia_de_obra(tmp)
    camara_y_encuadre(tmp)
    transacciones(tmp)
    clasificacion_de_detalles(tmp)
    armado_antes_del_concreto(tmp)
    reanudable_tras_cierre_de_revit(tmp)
    error_en_un_cuadro_queda_en_informe(tmp)
    entradas_invalidas_dan_informe(tmp)
    piezas_solo_en_copia_video()
    piezas_block_y_piedra()
    video_con_piezas_hilada_por_hilada(tmp)
    grafo_dyn_valido()
    rotulos_y_orden_de_archivos(tmp)
    if not args.sin_video:
        armar_video_mp4(tmp)

    fallas = [r for r in RESULTADOS if not r[1]]
    print("\n%d pruebas, %d fallas, %.1f s" % (len(RESULTADOS), len(fallas), time.time() - t0))
    if not args.conservar:
        shutil.rmtree(tmp, ignore_errors=True)
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
