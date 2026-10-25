# Video de obra para redes desde Revit (Dynamo + Python)

Video vertical de unos 30 s (1080x1920, 30 fps, H.264) para Instagram, TikTok o Facebook. El
modelo **estructural** de Revit 2025 se va "construyendo" por etapas de obra mientras la cámara
gira. No usa Twinmotion, Enscape, Lumion ni pyRevit:

1. **Revit + Dynamo** (`Video_Obra.dyn`) exporta los cuadros PNG desde una vista 3D.
2. **Python en Windows** (`armar_video.py`) une los PNG en el MP4 con rótulos y tarjeta final.

El repositorio no contiene datos de ningún proyecto ni cliente: el modelo de prueba es una casa
sintética generada por código (`mock/modelo_sintetico.py`).

## Contenido

| Archivo | Qué es |
|---|---|
| `nodo_video.py` | Código del nodo Python de Dynamo (Revit 2025, CPython3, pythonnet 2.5). |
| `Video_Obra.dyn` | Grafo de Dynamo con el nodo y sus 6 entradas editables. Se genera con `generar_dyn.py`. |
| `armar_video.py` | Une los PNG en un MP4 1080x1920, 30 fps, H.264 yuv420p, con rótulos y tarjeta final. |
| `previa.py` | Previa sin Revit: corre el mismo nodo contra el simulador y dibuja cajas con matplotlib. |
| `probar.py` | Pruebas de punta a punta contra el simulador. |
| `mock/` | Simulador mínimo de la API de Revit y modelo sintético. |
| `generar_dyn.py` | Vuelve a generar `Video_Obra.dyn` con el código actual de `nodo_video.py`. |
| `requirements.txt` | Paquetes de Python para armar el video y la previa. |

## Preparación (una sola vez)

En Windows, con Python 3.10 o más reciente:

```
pip install -r requirements.txt
```

`imageio-ffmpeg` trae su propio ffmpeg, así que no hace falta instalarlo aparte.

## Paso a paso

### 1. Ver la previa (opcional, sin Revit)

```
python previa.py
```

Genera `salida_previa/previa.mp4` (540x960) con la misma secuencia, el mismo guion y la misma cámara
que el nodo, sobre el modelo sintético. Agrega `--gif` para tener también un GIF, o cambia los
parámetros con `--grados 360`, `--duracion 20` o `--sin-acero`. Con el armado tarda unos 4 minutos
(medido en Linux).

### 2. Preparar la vista 3D base en Revit

- Usa una vista 3D **isométrica** (no una cámara en perspectiva), por ejemplo `{3D}`.
- Elige el estilo visual que quieras en el video: Sombreado, Colores coherentes o Realista, con o sin
  aristas. La vista de video lo hereda.
- Recomendado: fondo blanco, sombras apagadas (exporta más rápido), sin caja de sección y sin
  plantilla de vista que controle Visibilidad/Gráficos.
- Si el terreno tapa la cimentación, haz la excavación en el toposólido o dale transparencia al
  terreno en esa vista. Si no, los cimientos y su armado quedan ocultos bajo el terreno.
- El acero no hay que prepararlo: el nodo activa "Ver sin obstrucciones" y "Ver como sólido" solo en
  la vista `VIDEO OBRA` y le pone nivel de detalle Alto (ver "El armado" más abajo).

### 3. Abrir y ejecutar el grafo

1. En Revit: **Gestionar → Dynamo**. Abre `Video_Obra.dyn`.
2. Edita los nodos de entrada (a la izquierda):

| Entrada | Por defecto | Qué hace |
|---|---|---|
| Carpeta de salida | `C:\VIDEO_OBRA\cuadros` | Dónde se guardan los PNG, el guion y el informe. Se crea si no existe. |
| Vista 3D base | `{3D}` | Nombre exacto de la vista isométrica base. |
| FPS de exportación | 15 | 15 × 30 s = 450 cuadros. Con 10 tarda menos; con 30 se ve más fluido. |
| Duración (s) | 30 | Duración total del video. |
| Grados de giro | 180 | Giro total de la cámara. |
| Incluir acero | True | Agrega el armado: varillas, barras de refuerzo de área o de camino, mallas y acopladores. |

3. Comprueba que el nodo Python diga **CPython3** en su motor. El grafo viene en modo **Manual**:
   pulsa **Ejecutar**.
4. Revit se queda "congelado" mientras exporta. Para ver el avance, cuenta los PNG que van
   apareciendo en la carpeta.
5. Al terminar, la salida del nodo es la ruta de `informe_video.txt`. Ábrelo y revisa la sección
   **ERRORES**.

**Cuánto tarda:** no lo he medido en Revit. `ExportImage` de una imagen de 1920 px suele tardar entre
1 y 4 s según el modelo y el estilo visual, así que 450 cuadros serían aproximadamente de 8 a 30 min.
Después de la primera corrida, el informe trae el tiempo real por cuadro (promedio, mínimo y máximo).

**Si Revit se cierra a media exportación:** vuelve a abrir el modelo y ejecuta el grafo otra vez. Los
cuadros que ya existen se saltan y solo se exportan los que faltan. Si no habías guardado, la vista
`VIDEO OBRA` se vuelve a crear; si existe, se reutiliza.

### 4. Armar el MP4

```
python armar_video.py C:\VIDEO_OBRA\cuadros --marca "TU MARCA"
```

Genera `C:\VIDEO_OBRA\cuadros\video_obra.mp4`. Para 900 cuadros tarda alrededor de 1.5 min (medido en
Linux; en Windows no lo he medido). Opciones:

- `--salida ruta.mp4` para guardar el video en otro lugar.
- `--subtexto "Estructura · 2 niveles"` agrega una segunda línea a la tarjeta.
- `--modo duplicar` repite cuadros en vez de mezclarlos (por defecto se mezclan).
- `--sin-rotulos` y `--sin-tarjeta` quitan los textos.

Revit agrega el nombre de la vista a cada archivo (`frame_00001 - Vista 3D - VIDEO OBRA.png`).
`armar_video.py` ordena los cuadros por su número sin depender de ese texto y los renombra a
`frame_00001.png`. Si falta algún cuadro, repite el anterior y avisa.

## Qué hace el nodo

- **Vista:** duplica la vista base como `VIDEO OBRA` para heredar fase, estilo visual y filtros. Si
  ya existe, la reutiliza. Nunca modifica la geometría ni borra elementos del modelo: solo los oculta
  o muestra en esa vista, cambia su orientación, su caja de recorte y su nivel de detalle. La única
  excepción es un ajuste gráfico del acero que se guarda en cada varilla, pero solo para esta vista
  (ver "El armado"). También oculta en esa vista las categorías que no forman parte de la secuencia:
  puertas, ventanas, cubiertas, barandales, niveles, rejillas, contornos de refuerzo de área, etc. (la
  lista completa está en `CATEGORIAS_OCULTAS_SIEMPRE`). Si no se incluye el acero, también oculta
  sus categorías.
- **Elementos de la secuencia:** Cimentación estructural, Pilares estructurales, Armazón estructural,
  Muros, Suelos, Escaleras y el acero (Armadura estructural, Malla electrosoldada y Acopladores). Toma
  solo los visibles en la vista base y respeta los que ahí estén ocultos. Los modelos genéricos y el terreno no se tocan: quedan
  siempre visibles como base.
- **Orden de obra:** agrupa los elementos por nivel, según la Z inferior de su BoundingBox (se asigna
  al nivel de Revit más cercano por debajo). Dentro de cada nivel el orden es: cimentación corrida →
  dados → cadena de desplante (vigas en la Z más baja) → columnas y castillos → muros → trabes y
  cadenas → losas → escaleras. Dentro de cada etapa ordena por Z y luego con un barrido en planta
  (diagonal a 45°), para que la casa se vea crecer. Cada etapa empieza con su armado (ver abajo).
- **Tiempo mínimo por grupo:** cada grupo (un nivel y una etapa, armado o concreto) dura al menos
  0.7 s (`MIN_SEG_GRUPO`), aunque tenga pocos elementos, para que una losa o una malla se alcance a
  ver aunque el modelo tenga miles de varillas en otras etapas.
- **Guion (30 s):** de 0 a 1.5 s solo se ve el terreno; de 1.5 a 24 s avanza la construcción; de
  24 a 30 s se ve la estructura completa mientras termina el giro. Los tiempos son fracciones de la
  duración, así que se escalan si cambias la duración.
- **Cámara:** isométrica a 30° de elevación. Gira alrededor del centro de la BoundingBox total con
  `SetOrientation`, con arranque y final suaves. La caja de recorte es 9:16, de tamaño fijo (sin
  zoom durante el giro) y con 8 % de margen. Exporta PNG de 1920 px de alto (1080 de ancho).
- **El armado:** dentro de cada etapa aparece primero **todo** su acero y después todo su concreto.
  Por ejemplo: parrillas de cimientos → cimientos; armado de castillos y columnas → castillos y
  columnas; armado de trabes y cadenas → trabes y cadenas; armado o malla de losa → losa. El acero
  toma la etapa de su anfitrión: `GetHostId()` en varillas y barras de refuerzo de área o de camino,
  `HostId` en mallas. Si una varilla no tiene anfitrión, se asigna al concreto que la contiene; si
  tampoco hay, queda en una etapa "acero" antes de las columnas. El armado de cada etapa dura el 80 %
  de lo que dura su concreto (`PESO_ARMADO_RELATIVO`), sin importar cuántas varillas tenga. Para que
  el acero se vea en 3D, el nodo activa "Ver sin obstrucciones" y "Ver como sólido" en cada pieza,
  **solo en la vista `VIDEO OBRA`**. Es un ajuste gráfico por vista que Revit guarda en la varilla; no
  cambia su geometría ni cómo se ve en otras vistas o planos. "Sin obstrucciones" dibuja el acero
  encima del concreto, así que el armado sigue viéndose después del colado, hasta el final.
  Si el acero está modelado **dentro de una familia** (por ejemplo, castillos prefabricados con el
  armado incluido), aparece junto con su concreto: el nodo no lo puede separar.
- **Salidas en la carpeta:** `frame_NNNNN*.png`, `guion_video.json` (etapa y nivel de cada cuadro,
  que `armar_video.py` usa para los rótulos) e `informe_video.txt` (elementos por categoría y etapa,
  cuadros exportados y saltados, tiempo por cuadro y errores con traceback).

## Qué editar

### En `nodo_video.py` (bloque "PARÁMETROS EDITABLES", al inicio)

- `REGLAS_ETAPA`: la tabla del orden de obra. Cada fila tiene orden, etapa, categoría y condición.
  Las filas se evalúan de arriba abajo y la primera que se cumple define la etapa del elemento.
  La columna `orden` decide qué etapa aparece primero en el video.
- `PALABRAS_AISLADO` / `PALABRAS_CORRIDO`: palabras del nombre del tipo que distinguen un dado o
  zapata aislada de un cimiento corrido.
- `PESOS_CATEGORIA`: tiempo relativo de cada elemento de concreto. Las losas pesan 4 y las escaleras 2.
- Armado: `PESO_ARMADO_RELATIVO`, `MIN_SEG_GRUPO`, `VER_ACERO_SIN_OBSTRUCCION`,
  `VER_ACERO_COMO_SOLIDO`, `NIVEL_DETALLE_ALTO` y `CATEGORIAS_ACERO`.
- Cámara: `ELEVACION_GRADOS`, `AZIMUT_INICIAL_GRADOS`, `SUAVIZAR_GIRO`, `MARGEN_ENCUADRE` (bájalo,
  o ponlo negativo, para acercar la cámara).
- Guion: `FRACCION_INICIO_OBRA` y `FRACCION_FIN_OBRA`.
- `CATEGORIAS_OCULTAS_SIEMPRE`.

**Después de editar `nodo_video.py`**, ejecuta `python generar_dyn.py` para regenerar el `.dyn`, o
copia el código directamente dentro del nodo Python en Dynamo.

### En `armar_video.py` (bloque "PARÁMETROS EDITABLES")

- `ROTULOS_ETAPA`: texto de cada etapa ("Cimentación", "Castillos y columnas", "Muros",
  "Trabes y cadenas", "Losa"). En los niveles superiores el rótulo es `ROTULO_PLANTA_ALTA`, y la
  losa más alta y lo que está encima de ella usan `ROTULO_AZOTEA`.
- `ROTULOS_ARMADO`: texto mientras aparece el acero ("Armado de cimentación", "Armado de castillos y
  columnas", "Armado de trabes y cadenas", "Armado de losa"...). En niveles superiores:
  `ROTULO_ARMADO_PLANTA_ALTA` y `ROTULO_ARMADO_AZOTEA`.
- Posición y tamaño del rótulo: `ROTULO_Y` y `ROTULO_TAM`. Tarjeta final: `TARJETA_TEXTO`,
  `TARJETA_SEG`, colores y tamaño.
- Tipografías: `FUENTES_NORMAL` y `FUENTES_NEGRITA`. En Windows usa Segoe UI y, si no está, Arial.
- Calidad: `CRF` (18 por defecto) y `MODO_INTERPOLACION`.

## Pruebas

```
python probar.py              # todo, incluido armar un MP4 real (~1.5 min)
python probar.py --sin-video  # sin el MP4 (~15 s)
```

`probar.py` ejecuta `nodo_video.py` completo, igual que Dynamo (variable `IN` y salida `OUT`), contra
el simulador de `mock/` con el modelo sintético: cimientos corridos, dados, cadenas de desplante,
columnas, castillos, muros, trabes y cadenas, y losas en 2 niveles más azotea, además de escalera,
pretiles, terreno con excavación, una puerta y un muro oculto en la vista base. El acero del modelo
incluye varillas y estribos en columnas, castillos, cadenas y trabes; parrillas en cimientos y dados;
refuerzo de área (barras `RebarInSystem`) en la losa de planta baja y malla electrosoldada
(`FabricSheet`) en la de azotea. Además hay una varilla sin anfitrión dentro de una columna y otra
fuera de todo concreto.

### Qué está probado (en el simulador, en Linux)

- El nodo corre de punta a punta, exporta 450 cuadros y devuelve la ruta del informe sin errores.
- No cambia la geometría ni borra ningún elemento del modelo. Solo crea una vista nueva y deja
  intacta la vista base (elementos ocultos, orientación y recorte). Los únicos ajustes sobre
  elementos son los gráficos del acero, y solo en la vista de video.
- Antes de 1.5 s solo se ven el terreno y los modelos genéricos. Desde 24 s se ve toda la estructura.
  La obra nunca "se deshace". Puertas, varillas (sin la opción de acero) y el muro oculto en la vista
  base no aparecen nunca.
- El orden de las etapas se respeta en los dos niveles y la azotea, y cada etapa crece en varios
  cuadros (no aparece de golpe).
- La cámara está a 30° de elevación, empieza en -45°, gira 180° siempre en el mismo sentido y queda
  centrada en la estructura. El recorte es 9:16, de tamaño fijo, y la estructura completa cabe en
  todos los cuadros. Los PNG simulados son de 1080x1920.
- Transacciones: el simulador falla si se cambia la vista sin transacción abierta o si se llama a
  `ExportImage` con la transacción abierta. Las dos reglas se cumplen.
- Trampas de pythonnet: el simulador no tiene operadores en `XYZ`, falla con `tipo.Name` y exige
  `List[ElementId]`. El nodo funciona con esas restricciones.
- Armado (varillas, barras de refuerzo de área y mallas):
  - el acero de cada etapa aparece después de terminar el concreto de la etapa anterior y antes de
    cualquier concreto de su propia etapa, y la varilla sin anfitrión se ubica por la columna que la
    contiene;
  - todo el acero queda "sin obstrucciones" y "como sólido" solo en la vista de video: ningún ajuste
    toca la vista base;
  - una vez colocado, el acero sigue visible hasta el final;
  - si después se corre sin acero sobre la misma vista, sus categorías vuelven a ocultarse.
- Reanudación: después de una caída simulada de Revit en el cuadro 120, una segunda corrida salta
  los 119 cuadros hechos y exporta los 331 restantes. Los cuadros reanudados son idénticos byte a
  byte a los de una corrida sin cortes. Una tercera corrida reutiliza la vista y no exporta nada.
- Un error en un cuadro queda en el informe con su traceback, y la siguiente corrida lo completa.
- Una vista base inexistente o en perspectiva produce un informe con el error, sin exportar nada.
- `Video_Obra.dyn` es JSON válido. Su nodo Python tiene `"Engine": "CPython3"`, un código idéntico a
  `nodo_video.py` y 6 entradas conectadas del tipo correcto, con el acero activado por defecto.
- `armar_video.py` genera un MP4 H.264 yuv420p de 1080x1920, 30 fps, 900 cuadros y 30.0 s. También
  ordena y renombra los PNG sin depender del sufijo de Revit. Los rótulos salen en orden. Sin acero:
  Cimentación → Castillos y columnas → Muros → Trabes y cadenas → Losa → Planta alta → Azotea. Con
  acero, cada etapa que tiene armado muestra antes su rótulo de armado (por ejemplo, "Armado de losa"
  → "Losa").
- `previa.py` genera la previa en MP4 y GIF.

### Qué no está probado

Nada de esto se ha ejecutado en Revit ni en Dynamo. El simulador imita la API, pero no garantiza
cómo se comportan en Revit 2025 las siguientes llamadas:

- `clr.AddReference("RevitAPI")`, `clr.AddReference("RevitServices")` y las importaciones dentro del
  motor CPython3 de Dynamo.
- `List[ElementId]()` y `.Add()` en pythonnet 2.5.
- `FilteredElementCollector(doc).OfClass(View3D)` y `.OfClass(Level)`; y
  `FilteredElementCollector(doc, vista.Id).OfCategory(...).WhereElementIsNotElementType().ToElements()`:
  falta comprobar que el colector por vista devuelva exactamente los elementos visibles.
- `View3D.IsTemplate`, `.Name` (leer y asignar), `.IsPerspective`, `.IsLocked`, `.Unlock()` y
  `.IsSectionBoxActive`.
- `Level.ProjectElevation` frente a `Level.Elevation`, y que su referencia coincida con las
  coordenadas de `get_BoundingBox`.
- `Element.get_BoundingBox(None)`, `GetTypeId()`, `GetType().Name` (para reconocer `WallFoundation` y
  `Floor`), `IsHidden(vista)` y `CanBeHidden(vista)`.
- `Element.Name.GetValue(tipo)` en pythonnet 2.5, y la alternativa
  `get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()`.
- `ElementId.Value` (con `IntegerValue` como alternativa).
- `GetHostId()` en `Rebar` y `RebarInSystem`, y `HostId` en `FabricSheet`.
- `SetUnobscuredInView(vista, True)` y `SetSolidInView(vista, True)` en `Rebar`, `RebarInSystem`,
  `FabricSheet` y acopladores. Falta comprobar tres cosas:
  - si pythonnet expone esos métodos cuando el colector devuelve el elemento como `Element` (si no,
    el informe lo anota en "Acero con ajuste de vista fallido");
  - si en Revit 2025 "Ver como sólido" sigue existiendo o ya lo sustituye el nivel de detalle Alto;
  - cómo se ve en la imagen exportada.
- `View.DetailLevel = ViewDetailLevel.Fine` con una plantilla de vista asignada.
- Que el colector por vista devuelva el acero aunque en la vista base esté oculto por el concreto
  ("obstruido"). Que `BuiltInCategory.OST_FabricReinforcement` y `OST_Coupler` traigan los elementos
  esperados.
- `View3D.Duplicate(ViewDuplicateOption.Duplicate)`: falta comprobar qué copia exactamente (elementos
  ocultos, recorte, plantilla).
- `View3D.CropBoxActive` y `.CropBoxVisible`.
- `Category.GetCategory(doc, BuiltInCategory)` y `View.SetCategoryHidden(id, bool)`, sobre todo con
  una plantilla de vista asignada. Algunas `BuiltInCategory` de la lista pueden no existir.
- `View.HideElements(...)` y `View.UnhideElements(...)` con colecciones grandes.
- `ViewOrientation3D(ojo, arriba, adelante)` y `View3D.SetOrientation(...)`.
- `View3D.CropBox` (leer y asignar): el simulador supone que su `Transform` sigue a la cámara
  (X derecha, Y arriba, Z hacia el observador, origen en el ojo) y que Revit respeta el `Min`/`Max`
  asignado en una vista 3D ortográfica después de `SetOrientation`, incluido el rango en Z.
- `doc.Regenerate()` dentro de la transacción de Dynamo.
- `TransactionManager.Instance.EnsureInTransaction`, `TransactionTaskDone` y
  `ForceCloseTransaction`: falta comprobar que de verdad confirmen y cierren antes de cada exportación.
- `ImageExportOptions` (`ExportRange.SetOfViews`, `SetViewsAndSheets`, `HLRandWFViewsFileType`,
  `ShadowViewsFileType`, `ImageResolution`, `ZoomType`, `FitDirection`, `PixelSize`, `FilePath`) y
  `doc.ExportImage`. Faltan por comprobar:
  - el texto exacto que Revit agrega al nombre del archivo;
  - el tamaño exacto (1080 o 1079 px de ancho);
  - la exportación de una vista que no está abierta;
  - el tiempo real por cuadro.
- Que Dynamo 3.x de Revit 2025 abra `Video_Obra.dyn` sin advertencias. El JSON sigue el formato
  de Dynamo, pero no se ha abierto en Dynamo.
- Cómo se ve en Revit el terreno sobre la cimentación.
- `armar_video.py` y `previa.py` en Windows (se probaron en Linux), incluidas las fuentes Segoe UI y
  Arial.

Si algo falla en Revit, el informe guarda el traceback completo de cada error. Con eso se puede
corregir la llamada exacta.
