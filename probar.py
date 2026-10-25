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
from Autodesk.Revit.DB import XYZ, Element, ElementType, View3D, ErrorRevit  # noqa: E402
from System.Collections.Generic import List  # noqa: E402

RUTA_NODO = os.path.join(AQUI, "nodo_video.py")
RUTA_DYN = os.path.join(AQUI, "Video_Obra.dyn")

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

ROLES_NO_ESTRUCTURA = {"terreno", "genericos", "puertas", "muro_oculto_base", "tipos",
                       "varillas", "varillas_sueltas"}
CADENA_ORDEN = [
    ["corridos"], ["dados"], ["desplante"], ["columnas_pb", "castillos_pb"], ["muros_pb"],
    ["trabes_pb"], ["losas_pb"], ["escaleras"], ["columnas_pa", "castillos_pa"], ["muros_pa"],
    ["trabes_pa"], ["losas_pa"], ["pretiles"],
]


def correr(carpeta, doc=None, acero=False, fps=15, duracion=30, grados=180, fallos=None,
           exportador=None, vista="{3D}"):
    doc = doc or modelo_sintetico.crear_documento()
    simulador.reiniciar(doc, exportador=exportador or simulador.exportador_rapido, escala=0.125,
                        fallos=fallos)
    out, espacio = simulador.ejecutar_nodo(RUTA_NODO, [carpeta, vista, fps, duracion, grados, acero],
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
    base = ids_rol(doc, "terreno", "genericos")
    nunca = ids_rol(doc, "puertas", "muro_oculto_base", "varillas", "varillas_sueltas")
    previo = set()
    for e in ex:
        n, vis = numero_cuadro(e["ruta"]), set(e["visibles"])
        t = (n - 1) / 15.0
        assert base <= vis, "el terreno y los genéricos deben verse siempre (cuadro %d)" % n
        assert not (vis & nunca), "cuadro %d muestra elementos que deben quedar ocultos" % n
        obra = vis & est
        if t < 1.5:
            assert not obra, "antes de 1.5 s solo debe verse el terreno (cuadro %d)" % n
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
    for rol in ("corridos", "muros_pb", "muros_pa", "trabes_pb"):
        cuadros = set(primera[i] for i in ids_rol(doc, rol))
        assert len(cuadros) >= 4, "%s aparece de golpe (%d cuadros distintos)" % (rol, len(cuadros))


@prueba
def camara_y_encuadre(tmp):
    doc, out, _ = correr(os.path.join(tmp, "camara"))
    ex = sorted(simulador.estado.exportes, key=lambda e: numero_cuadro(e["ruta"]))
    est = estructura(doc)
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
def con_acero(tmp):
    doc, out, _ = correr(os.path.join(tmp, "acero"), acero=True)
    inf = leer(out)
    assert "ERRORES (0)" in inf and "Armadura estructural" in inf
    primera = primera_aparicion(simulador.estado.exportes)
    for i in ids_rol(doc, "varillas"):
        anf = doc._elementos[i]._anfitrion
        assert primera[i] <= primera[anf], "la varilla %d debe aparecer antes que su anfitrión" % i
    assert ids_rol(doc, "varillas_sueltas") <= set(primera)
    # Una segunda corrida sin acero sobre la misma vista vuelve a ocultar la categoría
    carpeta2 = os.path.join(tmp, "acero_luego_sin")
    correr(carpeta2, doc=doc, acero=False, fps=5, duracion=6)
    ult = simulador.estado.exportes[-1]
    assert not (set(ult["visibles"]) & ids_rol(doc, "varillas"))


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
def grafo_dyn_valido():
    with open(RUTA_DYN, encoding="utf-8") as f:
        g = json.load(f)
    with open(RUTA_NODO, encoding="utf-8") as f:
        codigo = f.read()
    py = [n for n in g["Nodes"] if n["ConcreteType"].startswith("PythonNodeModels.PythonNode")]
    assert len(py) == 1
    py = py[0]
    assert py["Engine"] == "CPython3"
    assert py["Code"] == codigo, "el código del .dyn difiere de nodo_video.py: corre generar_dyn.py"
    assert [p["Name"] for p in py["Inputs"]] == ["IN[%d]" % i for i in range(6)]
    salidas = {p["Id"]: n for n in g["Nodes"] for p in n["Outputs"]}
    entradas = {p["Id"] for p in py["Inputs"]}
    conectados = {c["End"]: salidas[c["Start"]] for c in g["Connectors"]}
    assert set(conectados) == entradas, "cada IN[i] debe tener su nodo de entrada"
    tipos = [conectados[p["Id"]]["ConcreteType"].split(",")[0] for p in py["Inputs"]]
    assert tipos == ["CoreNodeModels.Input.StringInput"] * 2 + ["CoreNodeModels.Input.DoubleInput"] * 3 + \
        ["CoreNodeModels.Input.BoolSelector"], tipos
    ids_vista = {v["Id"] for v in g["View"]["NodeViews"]}
    assert ids_vista == {n["Id"] for n in g["Nodes"]}
    assert g["View"]["Dynamo"]["RunType"] == "Manual"
    assert len(g["Inputs"]) == 6


@prueba
def armar_video_mp4(tmp):
    import armar_video
    import imageio_ffmpeg
    carpeta = os.path.join(tmp, "video")
    correr(carpeta)
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
    esperado = ["Cimentación", "Castillos y columnas", "Muros", "Trabes y cadenas", "Losa",
                "Planta alta", "Azotea"]
    assert secuencia == esperado, secuencia
    assert all(t == "" for t in textos[:22]) and all(t == "" for t in textos[361:])
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
    con_acero(tmp)
    reanudable_tras_cierre_de_revit(tmp)
    error_en_un_cuadro_queda_en_informe(tmp)
    entradas_invalidas_dan_informe(tmp)
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
