# -*- coding: utf-8 -*-
"""Previa del video SIN Revit: corre nodo_video.py contra el simulador (mock/) con el
modelo sintético y dibuja cada cuadro con matplotlib (cajas). Como ejecuta el mismo
nodo, la secuencia de obra y la cámara son exactamente las del video real.

    python previa.py                 -> salida_previa/previa.mp4 (540x960)
    python previa.py --gif           -> además salida_previa/previa.gif
    python previa.py --grados 360 --sin-acero --duracion 20

Los cuadros quedan en salida_previa/cuadros (reanudable: si existen, se saltan;
usa --limpiar para empezar de cero).
"""
import argparse
import os
import shutil
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "mock"))

import simulador          # noqa: E402
import modelo_sintetico   # noqa: E402
import armar_video        # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Previa del video de obra con el modelo sintético.")
    ap.add_argument("--salida", default=os.path.join(AQUI, "salida_previa"))
    ap.add_argument("--fps", type=float, default=15, help="FPS de exportación (entrada IN[2])")
    ap.add_argument("--duracion", type=float, default=30, help="Duración en s (IN[3])")
    ap.add_argument("--grados", type=float, default=180, help="Grados de giro (IN[4])")
    ap.add_argument("--sin-acero", action="store_true", help="No incluir el acero (IN[5] = False)")
    ap.add_argument("--escala", type=float, default=0.5, help="Tamaño de cuadro: 0.5 = 540x960")
    ap.add_argument("--marca", default=armar_video.TARJETA_TEXTO)
    ap.add_argument("--gif", action="store_true", help="Generar también un GIF (mitad de tamaño, 10 fps)")
    ap.add_argument("--limpiar", action="store_true", help="Borrar cuadros previos de la previa")
    args = ap.parse_args(argv)

    carpeta = os.path.join(args.salida, "cuadros")
    if args.limpiar and os.path.isdir(carpeta):
        shutil.rmtree(carpeta)
    os.makedirs(carpeta, exist_ok=True)

    t0 = time.time()
    doc = modelo_sintetico.crear_documento()
    simulador.reiniciar(doc, exportador=simulador.exportador_matplotlib, escala=args.escala)
    informe = simulador.ejecutar_nodo(os.path.join(AQUI, "nodo_video.py"),
                                      [carpeta, "{3D}", args.fps, args.duracion, args.grados, not args.sin_acero])
    print("Cuadros dibujados en %.1f s. Informe: %s" % (time.time() - t0, informe))
    with open(informe, encoding="utf-8") as f:
        if "ERRORES (0)" not in f.read():
            print("AVISO: el informe tiene errores, revísalo.")

    alto = int(round(1920 * args.escala / 2.0)) * 2
    ancho = int(round(alto * 9 / 16.0 / 2.0)) * 2
    gif = os.path.join(args.salida, "previa.gif") if args.gif else None
    r = armar_video.armar(carpeta, salida=os.path.join(args.salida, "previa.mp4"), marca=args.marca,
                          tam=(ancho, alto), gif=gif, progreso=False)
    print("Previa: %s (%dx%d, %d cuadros, %.1f s)" % (r["salida"], ancho, alto, r["cuadros_salida"],
                                                     r["duracion_s"]))
    if gif:
        print("GIF:    %s" % gif)
    return 0


if __name__ == "__main__":
    sys.exit(main())
