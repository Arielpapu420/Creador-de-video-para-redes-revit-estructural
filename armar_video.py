# -*- coding: utf-8 -*-
"""Une los PNG exportados por el nodo de Dynamo en un MP4 vertical para redes.

    python armar_video.py C:\\VIDEO_OBRA\\cuadros
    python armar_video.py C:\\VIDEO_OBRA\\cuadros --marca "MI ESTUDIO" --salida C:\\VIDEO_OBRA\\obra.mp4

Salida: H.264, yuv420p, 1080x1920, 30 fps, sin audio. Usa imageio + imageio-ffmpeg
(que trae su propio ffmpeg) y Pillow para los textos.

- Ordena los cuadros por su número (frame_00001...) sin depender del texto que
  Revit agrega al nombre, y los renombra a frame_00001.png.
- Pasa de FPS de exportación (15) a 30 fps duplicando o mezclando cuadros.
- Rótulo de etapa discreto abajo (lee guion_video.json que escribe el nodo).
- Tarjeta final con texto de marca.
"""
import argparse
import json
import math
import os
import re
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# =============================================================================
#  PARÁMETROS EDITABLES
# =============================================================================

ANCHO, ALTO = 1080, 1920
FPS_SALIDA = 30
FPS_ENTRADA_DEFECTO = 15          # si no hay guion_video.json
MODO_INTERPOLACION = "mezclar"    # "mezclar" (fundido entre cuadros) o "duplicar"
COLOR_FONDO = (255, 255, 255)     # relleno si el PNG no es exactamente 9:16
CRF = 18                          # calidad H.264 (menor = mejor; 18-23 es lo usual)
PREFIJO = "frame_"
NOMBRE_SALIDA = "video_obra.mp4"

# Rótulos de etapa (la clave es la "etapa" del nodo)
ROTULOS = True
ROTULOS_ETAPA = {
    "cimentacion": "Cimentación",
    "dados": "Cimentación",
    "desplante": "Cimentación",
    "acero": "Acero de refuerzo",
    "columnas": "Castillos y columnas",
    "muros": "Muros",
    "trabes": "Trabes y cadenas",
    "losas": "Losa",
    "escaleras": "Losa",
    "otros": "",
}
ROTULO_PLANTA_ALTA = "Planta alta"   # cualquier etapa en niveles superiores
ROTULO_AZOTEA = "Azotea"             # losa más alta y lo que esté encima
ROTULO_FINAL = ""                    # texto durante el remate (vacío = sin rótulo)
ROTULO_MIN_S = 0.8                   # un rótulo dura al menos esto (evita parpadeos)
ROTULO_FUNDIDO_S = 0.3
ROTULO_Y = 0.80                      # centro vertical (fracción del alto), fuera de la zona de botones
ROTULO_TAM = 0.024                   # tamaño de letra (fracción del alto: 46 px en 1920)
ROTULO_COLOR_FONDO = (20, 22, 26, 150)
ROTULO_COLOR_TEXTO = (255, 255, 255, 255)

# Tarjeta final (sustituye los últimos segundos del video)
TARJETA = True
TARJETA_TEXTO = "TU MARCA"
TARJETA_SUBTEXTO = ""
TARJETA_SEG = 1.5
TARJETA_FUNDIDO_S = 0.4
TARJETA_TAM = 0.060                  # tamaño del texto principal (fracción del alto)
TARJETA_COLOR_FONDO = (18, 20, 24)
TARJETA_COLOR_TEXTO = (255, 255, 255)

# Tipografías (se usa la primera que exista)
FUENTES_NORMAL = [
    "C:/Windows/Fonts/seguisb.ttf",     # Segoe UI Semibold
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "DejaVuSans.ttf",
]
FUENTES_NEGRITA = [
    "C:/Windows/Fonts/segoeuib.ttf",    # Segoe UI Bold
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/opentype/inter/Inter-Bold.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
]


# =============================================================================
#  CUADROS DE ENTRADA
# =============================================================================

def ordenar_y_renombrar(carpeta, prefijo=PREFIJO, renombrar=True):
    """Devuelve {número: ruta} de los PNG frame_NNNNN*.png.

    Revit agrega " - <tipo de vista> - <nombre de vista>" al nombre: aquí solo
    importa el número. Si hay dos archivos del mismo número, gana el más reciente.
    Con renombrar=True deja cada cuadro como frame_NNNNN.png.
    """
    patron = re.compile(r"^" + re.escape(prefijo) + r"(\d{5})(?:\D.*)?\.png$", re.IGNORECASE)
    por_numero = {}
    for nombre in os.listdir(carpeta):
        m = patron.match(nombre)
        if not m:
            continue
        ruta = os.path.join(carpeta, nombre)
        if os.path.getsize(ruta) == 0:
            continue
        n = int(m.group(1))
        if n not in por_numero or os.path.getmtime(ruta) > os.path.getmtime(por_numero[n]):
            por_numero[n] = ruta
    if renombrar:
        for n, ruta in list(por_numero.items()):
            limpia = os.path.join(carpeta, "%s%05d.png" % (prefijo, n))
            if os.path.normcase(os.path.abspath(ruta)) != os.path.normcase(os.path.abspath(limpia)):
                os.replace(ruta, limpia)
                por_numero[n] = limpia
    return dict(sorted(por_numero.items()))


def leer_guion(carpeta):
    ruta = os.path.join(carpeta, "guion_video.json")
    if not os.path.isfile(ruta):
        return None
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def _cargar(ruta, tam):
    """PNG -> arreglo RGB del tamaño final, sin deformar (rellena con COLOR_FONDO)."""
    img = Image.open(ruta)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        fondo = Image.new("RGBA", img.size, COLOR_FONDO + (255,))
        img = Image.alpha_composite(fondo, img)
    img = img.convert("RGB")
    if img.size != tam:
        k = min(tam[0] / float(img.size[0]), tam[1] / float(img.size[1]))
        nuevo = (max(1, int(round(img.size[0] * k))), max(1, int(round(img.size[1] * k))))
        img = img.resize(nuevo, Image.LANCZOS)
        lienzo = Image.new("RGB", tam, COLOR_FONDO)
        lienzo.paste(img, ((tam[0] - nuevo[0]) // 2, (tam[1] - nuevo[1]) // 2))
        img = lienzo
    return np.asarray(img, dtype=np.uint8)


# =============================================================================
#  TEXTOS
# =============================================================================

def fuente(tam_px, negrita=False):
    for ruta in (FUENTES_NEGRITA if negrita else FUENTES_NORMAL):
        try:
            return ImageFont.truetype(ruta, int(tam_px))
        except (OSError, IOError):
            continue
    try:
        return ImageFont.load_default(size=int(tam_px))
    except TypeError:
        return ImageFont.load_default()


def rotulos_por_cuadro(guion, n_entrada):
    """Texto del rótulo para cada cuadro de entrada (lista de str)."""
    if not guion or not ROTULOS:
        return [""] * n_entrada
    cuadros = guion["cuadros"]
    niveles_losa = [c["nivel"] for c in cuadros if c.get("etapa") == "losas" and c.get("nivel") is not None]
    nivel_azotea = max(niveles_losa) if niveles_losa else None

    def texto(c):
        if c["fase"] == "terreno":
            return ""
        if c["fase"] == "final":
            return ROTULO_FINAL
        etapa, nivel = c.get("etapa"), c.get("nivel")
        if etapa is None:
            return ""
        if nivel is None or nivel == 0:
            return ROTULOS_ETAPA.get(etapa, "")
        if nivel_azotea is not None and nivel_azotea > 0 and (
                nivel > nivel_azotea or (nivel == nivel_azotea and etapa == "losas")):
            return ROTULO_AZOTEA
        return ROTULO_PLANTA_ALTA

    textos = [texto(c) for c in cuadros[:n_entrada]]
    textos += [""] * (n_entrada - len(textos))

    # Tramos demasiado cortos toman el rótulo del tramo anterior
    fps = float(guion.get("fps", FPS_ENTRADA_DEFECTO))
    minimo = max(1, int(round(ROTULO_MIN_S * fps)))
    i = 0
    while i < len(textos):
        j = i
        while j < len(textos) and textos[j] == textos[i]:
            j += 1
        if textos[i] and j - i < minimo and i > 0 and textos[i - 1]:
            for k in range(i, j):
                textos[k] = textos[i - 1]
        i = j
    return textos


class Rotulador(object):
    """Pastilla semitransparente con el texto de la etapa, centrada abajo."""

    def __init__(self, tam):
        self.tam = tam
        self.fuente = fuente(ROTULO_TAM * tam[1])
        self._cache = {}

    def _parche(self, texto):
        if texto not in self._cache:
            d = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
            x0, y0, x1, y1 = d.textbbox((0, 0), texto, font=self.fuente)
            alto_txt = ROTULO_TAM * self.tam[1]
            px, py = int(alto_txt * 0.9), int(alto_txt * 0.45)
            w, h = (x1 - x0) + 2 * px, int(alto_txt * 1.25) + 2 * py
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=ROTULO_COLOR_FONDO)
            d.text((w / 2.0, h / 2.0), texto, font=self.fuente, fill=ROTULO_COLOR_TEXTO, anchor="mm")
            arr = np.asarray(img, dtype=np.float32)
            self._cache[texto] = (arr[:, :, :3], arr[:, :, 3:4] / 255.0)
        return self._cache[texto]

    def aplicar(self, cuadro, texto, opacidad):
        if not texto or opacidad <= 0:
            return cuadro
        rgb, alfa = self._parche(texto)
        h, w = alfa.shape[:2]
        x = (self.tam[0] - w) // 2
        y = int(ROTULO_Y * self.tam[1] - h / 2.0)
        x, y = max(0, x), max(0, min(self.tam[1] - h, y))
        w, h = min(w, self.tam[0] - x), min(h, self.tam[1] - y)
        a = alfa[:h, :w] * opacidad
        zona = cuadro[y:y + h, x:x + w].astype(np.float32)
        cuadro = cuadro.copy()
        cuadro[y:y + h, x:x + w] = (zona * (1 - a) + rgb[:h, :w] * a).astype(np.uint8)
        return cuadro


def imagen_tarjeta(tam, texto, subtexto):
    img = Image.new("RGB", tam, TARJETA_COLOR_FONDO)
    d = ImageDraw.Draw(img)
    tam_txt = TARJETA_TAM * tam[1]
    f = fuente(tam_txt, negrita=True)
    # Reduce el texto si no cabe en el 86 % del ancho
    while d.textlength(texto, font=f) > 0.86 * tam[0] and tam_txt > 10:
        tam_txt *= 0.92
        f = fuente(tam_txt, negrita=True)
    cy = tam[1] * (0.47 if subtexto else 0.5)
    d.text((tam[0] / 2.0, cy), texto, font=f, fill=TARJETA_COLOR_TEXTO, anchor="mm")
    if subtexto:
        fs = fuente(tam_txt * 0.4)
        d.text((tam[0] / 2.0, cy + tam_txt * 1.0), subtexto, font=fs,
               fill=tuple(int(c * 0.75) for c in TARJETA_COLOR_TEXTO), anchor="mm")
    return np.asarray(img, dtype=np.uint8)


# =============================================================================
#  ARMADO
# =============================================================================

def armar(carpeta, salida=None, fps_entrada=None, marca=TARJETA_TEXTO, subtexto=TARJETA_SUBTEXTO,
          modo=MODO_INTERPOLACION, tam=(ANCHO, ALTO), fps_salida=FPS_SALIDA, rotulos=True,
          tarjeta=TARJETA, renombrar=True, gif=None, gif_fps=10, progreso=True):
    """Arma el video. Devuelve un dict con el resumen."""
    import imageio.v2 as imageio

    if modo not in ("mezclar", "duplicar"):
        raise ValueError("modo debe ser 'mezclar' o 'duplicar'")
    tam = (int(tam[0]), int(tam[1]))
    if tam[0] % 2 or tam[1] % 2:
        raise ValueError("H.264 yuv420p necesita ancho y alto pares")
    salida = salida or os.path.join(carpeta, NOMBRE_SALIDA)
    cuadros = ordenar_y_renombrar(carpeta, renombrar=renombrar)
    if not cuadros:
        raise SystemExit("No hay cuadros %s*.png en %s" % (PREFIJO, carpeta))
    guion = leer_guion(carpeta)
    if fps_entrada is None:
        fps_entrada = guion["fps"] if guion else FPS_ENTRADA_DEFECTO
    n_entrada = guion["cuadros_total"] if guion else max(cuadros)

    # Cuadros faltantes: se repite el último disponible
    faltan = [n for n in range(1, n_entrada + 1) if n not in cuadros]
    rutas, ultima = [], cuadros[min(cuadros)]
    for n in range(1, n_entrada + 1):
        ultima = cuadros.get(n, ultima)
        rutas.append(ultima)

    textos = rotulos_por_cuadro(guion, n_entrada) if rotulos else [""] * n_entrada
    rotulador = Rotulador(tam)
    duracion = n_entrada / float(fps_entrada)
    n_salida = int(round(duracion * fps_salida))
    t_tarjeta = duracion - TARJETA_SEG
    img_tarjeta = imagen_tarjeta(tam, marca, subtexto) if tarjeta else None

    cache = {}

    def cuadro_entrada(i):
        if i not in cache:
            if len(cache) > 4:
                cache.pop(min(cache))
            cache[i] = _cargar(rutas[i], tam)
        return cache[i]

    escritor = imageio.get_writer(
        salida, format="FFMPEG", mode="I", fps=fps_salida, codec="libx264",
        pixelformat="yuv420p", quality=None, macro_block_size=2,
        ffmpeg_params=["-crf", str(CRF), "-preset", "medium", "-movflags", "+faststart"])
    cuadros_gif = []
    texto_actual, t_cambio = None, 0.0
    inicio = time.time()
    try:
        for j in range(n_salida):
            t = j / float(fps_salida)
            s = j * fps_entrada / float(fps_salida)
            i0 = min(int(math.floor(s + 1e-9)), n_entrada - 1)
            i1 = min(i0 + 1, n_entrada - 1)
            a = s - i0 if modo == "mezclar" else 0.0
            f = cuadro_entrada(i0)
            if a > 1e-6 and i1 != i0:
                f = (f.astype(np.float32) * (1 - a) + cuadro_entrada(i1).astype(np.float32) * a
                     + 0.5).astype(np.uint8)

            texto = textos[i0]
            if texto != texto_actual:
                texto_actual, t_cambio = texto, t
            opacidad = min(1.0, (t - t_cambio) / ROTULO_FUNDIDO_S) if ROTULO_FUNDIDO_S > 0 else 1.0
            f = rotulador.aplicar(f, texto_actual, opacidad)

            if img_tarjeta is not None and t >= t_tarjeta:
                k = min(1.0, (t - t_tarjeta) / TARJETA_FUNDIDO_S) if TARJETA_FUNDIDO_S > 0 else 1.0
                f = (f.astype(np.float32) * (1 - k) + img_tarjeta.astype(np.float32) * k
                     + 0.5).astype(np.uint8)

            escritor.append_data(f)
            if gif and j % max(1, int(round(fps_salida / float(gif_fps)))) == 0:
                cuadros_gif.append(Image.fromarray(f).resize((tam[0] // 2, tam[1] // 2), Image.LANCZOS))
            if progreso and (j % 60 == 0 or j == n_salida - 1):
                print("  cuadro %d/%d" % (j + 1, n_salida))
    finally:
        escritor.close()

    if gif and cuadros_gif:
        cuadros_gif[0].save(gif, save_all=True, append_images=cuadros_gif[1:], loop=0,
                            duration=int(1000 / gif_fps), optimize=True)

    resumen = {"salida": salida, "cuadros_entrada": n_entrada, "cuadros_salida": n_salida,
               "fps_entrada": fps_entrada, "fps_salida": fps_salida, "duracion_s": duracion,
               "faltantes": faltan, "segundos": round(time.time() - inicio, 1), "gif": gif}
    return resumen


def main(argv=None):
    ap = argparse.ArgumentParser(description="Une los cuadros PNG de Revit en un MP4 vertical 1080x1920.")
    ap.add_argument("carpeta", help="Carpeta con frame_00001*.png y guion_video.json")
    ap.add_argument("--salida", help="Ruta del MP4 (por defecto <carpeta>/%s)" % NOMBRE_SALIDA)
    ap.add_argument("--fps-entrada", type=float, help="FPS de exportación si no hay guion_video.json")
    ap.add_argument("--marca", default=TARJETA_TEXTO, help="Texto de la tarjeta final")
    ap.add_argument("--subtexto", default=TARJETA_SUBTEXTO, help="Segunda línea de la tarjeta final")
    ap.add_argument("--modo", choices=["mezclar", "duplicar"], default=MODO_INTERPOLACION)
    ap.add_argument("--sin-rotulos", action="store_true")
    ap.add_argument("--sin-tarjeta", action="store_true")
    ap.add_argument("--no-renombrar", action="store_true", help="No renombrar los PNG")
    args = ap.parse_args(argv)

    r = armar(args.carpeta, salida=args.salida, fps_entrada=args.fps_entrada, marca=args.marca,
              subtexto=args.subtexto, modo=args.modo, rotulos=not args.sin_rotulos,
              tarjeta=not args.sin_tarjeta, renombrar=not args.no_renombrar)
    print("Video: %s" % r["salida"])
    print("Cuadros: %d de entrada a %g fps -> %d de salida a %d fps (%.1f s), en %.1f s"
          % (r["cuadros_entrada"], r["fps_entrada"], r["cuadros_salida"], r["fps_salida"],
             r["duracion_s"], r["segundos"]))
    if r["faltantes"]:
        print("AVISO: faltan %d cuadros (se repitió el anterior): %s"
              % (len(r["faltantes"]), r["faltantes"][:20]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
