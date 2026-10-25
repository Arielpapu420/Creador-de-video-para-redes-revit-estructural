# Video de obra para redes desde Revit (Dynamo + Python)

Video vertical de unos 60 s (1080x1920, 30 fps, H.264) para Instagram, TikTok o Facebook. El
modelo **estructural** de Revit 2025 se va "construyendo" por etapas de obra mientras la cámara
gira, con el armado, las piedras de la mampostería y los blocks colocándose hilada por hilada.
No usa Twinmotion, Enscape, Lumion ni pyRevit:

1. **Revit + Dynamo** (`Piezas_Obra.dyn`, opcional) crea los blocks y las piedras en una **copia**
   del modelo.
2. **Revit + Dynamo** (`Video_Obra.dyn`) exporta los cuadros PNG desde una vista 3D.
3. **Python en Windows** (`armar_video.py`) une los PNG en el MP4 con texto gancho, rótulos y
   tarjeta final.

El repositorio no contiene datos de ningún proyecto ni cliente: el modelo de prueba es una casa
sintética generada por código (`mock/modelo_sintetico.py`).

## Contenido

| Archivo | Qué es |
|---|---|
| `nodo_video.py` | Código del nodo Python de Dynamo (Revit 2025, CPython3, pythonnet 2.5). |
| `Video_Obra.dyn` | Grafo de Dynamo con el nodo y sus 6 entradas editables. Se genera con `generar_dyn.py`. |
| `nodo_piezas.py` | Nodo Python de Dynamo que crea blocks y piedras (DirectShape) en la copia `...VIDEO...` del modelo. |
| `Piezas_Obra.dyn` | Grafo de Dynamo con `nodo_piezas.py` y sus 6 entradas (medidas del block, junta, piedras, borrar). |
| `armar_video.py` | Une los PNG en un MP4 1080x1920, 30 fps, H.264 yuv420p, con rótulos y tarjeta final. |
| `previa.py` | Previa sin Revit: corre el mismo nodo contra el simulador y dibuja cajas con matplotlib. |
| `probar.py` | Pruebas de punta a punta contra el simulador. |
| `mock/` | Simulador mínimo de la API de Revit y modelo sintético. |
| `generar_dyn.py` | Vuelve a generar los dos `.dyn` con el código actual de los nodos. |
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
parámetros con `--grados 360`, `--duracion 30`, `--sin-acero` o `--sin-piezas`. Primero corre
`nodo_piezas.py` sobre el modelo sintético, así que la previa muestra los blocks y las piedras.
Con piezas y armado tarda alrededor de 8 minutos (medido en Linux).

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

### 3. Crear los blocks y las piedras (en una copia del modelo)

En Revit un muro es un solo sólido. Para ver cómo se colocan los blocks y las piedras, hay que
crearlos como piezas:

1. **Guarda una copia** del modelo con "VIDEO" en el nombre, por ejemplo `MODELO_VIDEO.rvt`. El nodo
   se niega a trabajar en un archivo sin "VIDEO" en el nombre, para no tocar tu modelo original.
2. En la copia: **Gestionar → Dynamo** y abre `Piezas_Obra.dyn`. Revisa las entradas:

| Entrada | Por defecto | Qué hace |
|---|---|---|
| Largo del block (cm) | 40 | Medida nominal con junta: se dibuja de 39 cm. |
| Alto del block (cm) | 20 | Medida nominal con junta: se dibuja de 19 cm. |
| Espesor del block (cm) | 12 | Espesor del block, centrado en el muro. |
| Junta (cm) | 1 | Junta de mortero entre blocks. |
| Piedras en mampostería | True | Convierte los cimientos de piedra en piedras sobre camas de mortero. |
| Solo borrar piezas | False | True: borra las piezas creadas antes y no crea nuevas. |

3. Pulsa **Ejecutar**. La salida es un resumen: piezas por muro y muros omitidos (por ejemplo,
   los curvos).

**Qué muros convierte:** los que tienen "block", "bloque", "tabique", "tabicón" o "ladrillo" en el
tipo, la familia o el material se convierten en blocks. Los de "piedra", "roca", "mampostería" o
"braza" se convierten en piedras. Los de concreto o cisterna no se tocan. Las hiladas van
cuatrapeadas y se cortan donde hay castillos, columnas, dalas, cerramientos, puertas o ventanas.
Las piedras son de tamaño variable (25 a 45 cm de largo, 20 a 30 cm de alto), dos en el espesor y
siempre con la misma semilla, así que cada corrida da las mismas piedras.

Volver a ejecutarlo borra las piezas anteriores y las crea de nuevo; no se duplican. Cada pieza es
un DirectShape (Modelo genérico) con `ApplicationId = "VIDEO_OBRA"`. Así el nodo de video las
reconoce y el nodo de piezas solo borra las suyas. Una casa de dos niveles da del orden de 5000
piezas; crearlas en Revit puede tardar unos minutos (no lo he medido).

### 4. Abrir y ejecutar el grafo del video

1. En Revit (en la copia, si creaste piezas): **Gestionar → Dynamo**. Abre `Video_Obra.dyn`.
2. Edita los nodos de entrada (a la izquierda):

| Entrada | Por defecto | Qué hace |
|---|---|---|
| Carpeta de salida | `C:\VIDEO_OBRA\cuadros` | Dónde se guardan los PNG, el guion y el informe. Se crea si no existe. |
| Vista 3D base | `{3D}` | Nombre exacto de la vista isométrica base. |
| FPS de exportación | 15 | 15 × 60 s = 900 cuadros. Con 10 tarda menos; con 30 se ve más fluido. |
| Duración (s) | 60 | Duración total del video. |
| Grados de giro | 180 | Giro total de la cámara. |
| Incluir acero | True | Agrega el armado: varillas, barras de refuerzo de área o de camino, mallas y acopladores. |

3. Comprueba que el nodo Python diga **CPython3** en su motor. El grafo viene en modo **Manual**:
   pulsa **Ejecutar**.
4. Revit se queda "congelado" mientras exporta. Para ver el avance, cuenta los PNG que van
   apareciendo en la carpeta.
5. Al terminar, la salida del nodo es la ruta de `informe_video.txt`. Ábrelo y revisa la sección
   **ERRORES**.

**Cuánto tarda:** no lo he medido en Revit. `ExportImage` de una imagen de 1920 px suele tardar entre
1 y 4 s según el modelo y el estilo visual (con miles de piezas y varillas, más). Así que 900 cuadros
serían aproximadamente de 15 a 60 min.
Después de la primera corrida, el informe trae el tiempo real por cuadro (promedio, mínimo y máximo).

**Si Revit se cierra a media exportación:** vuelve a abrir el modelo y ejecuta el grafo otra vez. Los
cuadros que ya existen se saltan y solo se exportan los que faltan. Si no habías guardado, la vista
`VIDEO OBRA` se vuelve a crear; si existe, se reutiliza.

### 5. Armar el MP4

```
python armar_video.py C:\VIDEO_OBRA\cuadros --marca "TU MARCA"
```

Genera `C:\VIDEO_OBRA\cuadros\video_obra.mp4`. Para 900 cuadros tarda alrededor de 1.5 min (medido en
Linux; en Windows no lo he medido). Opciones:

- `--salida ruta.mp4` para guardar el video en otro lugar.
- `--subtexto "Estructura · 2 niveles"` agrega una segunda línea a la tarjeta.
- `--modo duplicar` repite cuadros en vez de mezclarlos (por defecto se mezclan).
- `--gancho "Así se construye una casa"` cambia el texto del inicio (`--gancho ""` lo quita).
- `--sin-rotulos` y `--sin-tarjeta` quitan los textos.

**Para que funcione en redes:** el texto gancho aparece desde el primer cuadro (en los primeros 2-3 s
se decide si la gente se queda) y la tarjeta final cierra con tu marca. El video sale sin música:
agrégala en Instagram o TikTok con un audio en tendencia, que esas apps priorizan.

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
  Muros, Suelos, Cubiertas, Escaleras, Rampas, los Modelos genéricos que reconozca alguna regla
  (bovedillas, tinaco, cisterna, banqueta) y el acero (Armadura estructural, Malla electrosoldada y
  Acopladores). Toma solo los visibles en la vista base y respeta los que ahí estén ocultos. El
  terreno y los modelos genéricos sin regla (árboles, autos, etc.) no se tocan: quedan siempre
  visibles como base.
- **Orden de obra:** agrupa los elementos por nivel, según la Z inferior de su BoundingBox (se asigna
  al nivel de Revit más cercano por debajo). Dentro de cada nivel el orden es:

  | Orden | Etapa | Cómo se reconoce |
  |---|---|---|
  | 10 | Cimiento corrido | Cimentación estructural de tipo corrido (o `WallFoundation`). |
  | 20 | Dados | El resto de la Cimentación estructural. |
  | 25 | Cimiento de mampostería | Muro o cimentación con **material** (o tipo) de piedra, roca, mampostería o braza, y enterrado. Un muro de piedra sobre el terreno va con los muros. |
  | 27 | Cisterna | "cisterna" o "aljibe" en el tipo, la familia o el material, en cualquier categoría. |
  | 30 | Cadena de desplante | Viga en la Z más baja del nivel. |
  | 35 | Firme | Suelo cuya cara superior está en su propio nivel (apoyado en el terreno). |
  | 40 | Castillos y columnas | Pilares estructurales. |
  | 50 | Muros | Muros (incluye pretiles, en el nivel de azotea). |
  | 60 | Trabes, dalas, cerramientos y cadenas | El resto del Armazón estructural; dentro de la etapa, primero lo más bajo. |
  | 64 | Viguetas | "vigueta" en el nombre, o viga de 13 cm de ancho y 20 cm de peralte como máximo (las "mini trabes"). |
  | 66 | Bovedillas | "bovedilla", "casetón" o "poliestireno", en cualquier categoría. |
  | 70 | Losas | Suelos y cubiertas: losa maciza, volados, firme de compresión. |
  | 80 | Escaleras | |
  | 96 | Tinaco | "tinaco" en el nombre (base y tinaco). |
  | al final | Exteriores | "banqueta", "andador", "pavimento" o "estacionamiento", o un suelo, rampa o escalera a nivel de terreno fuera de la huella de la casa. Se construyen después del último nivel. |

  Dentro de cada etapa ordena por Z y luego con un barrido en planta (diagonal a 45°), para que la
  casa se vea crecer. Cada etapa empieza con su armado (ver abajo). En una losa de vigueta y
  bovedilla, la secuencia queda: viguetas → bovedillas → malla → firme de compresión.
- **Tiempo de cada grupo:** cada pieza aparece al inicio de su intervalo de tiempo. Cada grupo (un
  nivel y una etapa, armado o concreto) dura al menos 0.7 s (`MIN_SEG_GRUPO`) aunque tenga pocos
  elementos. Si hay muchos grupos, ese mínimo baja para que todo quepa en el tiempo de obra.
- **Guion (60 s):** de 0 a 1.5 s solo se ve el terreno (con el texto gancho encima); de 1.5 a 54 s
  avanza la construcción; los últimos 6 s muestran la estructura completa mientras termina el giro, y
  en el último segundo y medio entra la tarjeta final. Los tiempos están en segundos
  (`SEG_SOLO_TERRENO`, `SEG_REMATE`); en videos muy cortos se limitan al 5 % y al 20 % de la duración.
- **Blocks y piedras:** si la copia tiene piezas de `nodo_piezas.py`, el muro sólido queda oculto
  todo el video y en su lugar se colocan sus piezas, en la etapa del muro. Todas las hiladas de los
  muros del nivel suben juntas, como en obra: primero la hilada 1 de todos los muros, luego la 2, y
  así. En la mampostería, la cama de mortero de cada hilada va antes que sus piedras. Un muro en
  piezas dura como 4 elementos normales (`PESO_MURO_EN_PIEZAS`). Las piezas de un muro que no está
  en la secuencia (por ejemplo, oculto en la vista base) quedan ocultas.
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
  cambia su geometría ni cómo se ve en otras vistas o planos. **Al colar**, en el cuadro en que
  aparece un concreto, el nodo le quita "sin obstrucciones" a su armado y el concreto lo tapa
  (`ACERO_SE_TAPA_AL_COLAR`). Solo queda a la vista el acero que sobresale, como las varillas de
  espera de los castillos.
  Si el acero está modelado **dentro de una familia** (por ejemplo, castillos prefabricados con el
  armado incluido), aparece junto con su concreto: el nodo no lo puede separar.
- **Salidas en la carpeta:** `frame_NNNNN*.png`, `guion_video.json` (etapa y nivel de cada cuadro,
  que `armar_video.py` usa para los rótulos) e `informe_video.txt`. El informe trae los elementos por
  categoría y etapa, los cuadros exportados y saltados, el tiempo por cuadro y los errores con
  traceback. También trae la sección **TIPOS DE REVIT POR ETAPA**: cada tipo, con sus materiales, en
  la etapa en que cayó. Revísala en la primera corrida para confirmar que la mampostería, las
  viguetas, las bovedillas y el resto quedaron donde deben.

## Qué editar

### En `nodo_video.py` (bloque "PARÁMETROS EDITABLES", al inicio)

- `REGLAS_ETAPA`: la tabla del orden de obra. Cada fila tiene orden, etapa, categoría y condición.
  Las filas se evalúan de arriba abajo y la primera que se cumple define la etapa del elemento.
  La columna `orden` decide qué etapa aparece primero en el video.
- Palabras clave: dentro de `REGLAS_ETAPA` (`"palabras:cisterna|aljibe"`, etc.), `PALABRAS_AISLADO` /
  `PALABRAS_CORRIDO` (dado o cimiento corrido) y `PALABRAS_PIEDRA` (mampostería). Se buscan en el
  nombre del tipo, de la familia y de los materiales, sin importar mayúsculas ni acentos.
- Criterios geométricos en metros: `VIGUETA_ANCHO_MAX_M`, `VIGUETA_PERALTE_MAX_M`,
  `ENTERRADO_TOL_M`, `FIRME_TOL_M`, `EXTERIOR_ALTURA_MAX_M` y `HUELLA_MARGEN_M`.
- `PESOS_CATEGORIA`: tiempo relativo de cada elemento de concreto. Las losas pesan 4 y las escaleras 2.
- Armado: `PESO_ARMADO_RELATIVO`, `MIN_SEG_GRUPO`, `VER_ACERO_SIN_OBSTRUCCION`,
  `ACERO_SE_TAPA_AL_COLAR`, `VER_ACERO_COMO_SOLIDO`, `NIVEL_DETALLE_ALTO` y `CATEGORIAS_ACERO`.
- Cámara: `ELEVACION_GRADOS`, `AZIMUT_INICIAL_GRADOS`, `SUAVIZAR_GIRO`, `MARGEN_ENCUADRE` (bájalo,
  o ponlo negativo, para acercar la cámara).
- Guion: `SEG_SOLO_TERRENO` y `SEG_REMATE`. Piezas: `PESO_MURO_EN_PIEZAS`.

### En `nodo_piezas.py` (bloque "PARÁMETROS EDITABLES")

- `PALABRAS_BLOCK`, `PALABRAS_PIEDRA` y `PALABRAS_EXCLUIR`: qué muros se convierten.
- `CATEGORIAS_OBSTACULO`: lo que corta las hiladas.
- Piedra: `PIEDRA_ALTO`, `PIEDRA_LARGO`, `PIEDRA_JUNTA`, `PIEDRAS_A_LO_ANCHO`, `MORTERO_RETIRO`,
  `MORTERO_ALTO` (la cama de mortero llega al 60 % de la hilada para que las piedras sobresalgan) y
  `SEMILLA`.
- `CATEGORIAS_OCULTAS_SIEMPRE`.

**Después de editar `nodo_video.py`**, ejecuta `python generar_dyn.py` para regenerar el `.dyn`, o
copia el código directamente dentro del nodo Python en Dynamo.

### En `armar_video.py` (bloque "PARÁMETROS EDITABLES")

- `ROTULOS_ETAPA`: texto de cada etapa ("Cimentación", "Cimiento de mampostería", "Cisterna",
  "Firme", "Castillos y columnas", "Muros", "Trabes y cadenas", "Vigueta y bovedilla", "Losa",
  "Tinaco", "Exteriores"). En los niveles superiores el rótulo es `ROTULO_PLANTA_ALTA`; la losa más
  alta (incluida su vigueta y bovedilla) y lo que está encima usan `ROTULO_AZOTEA`. Las etapas de
  `ETAPAS_ROTULO_PROPIO` (cisterna, tinaco, exteriores) muestran siempre su propio rótulo.
- `ROTULOS_ARMADO`: texto mientras aparece el acero ("Armado de cimentación", "Armado de castillos y
  columnas", "Armado de trabes y cadenas", "Armado de losa"...). En niveles superiores:
  `ROTULO_ARMADO_PLANTA_ALTA` y `ROTULO_ARMADO_AZOTEA`.
- Posición y tamaño del rótulo: `ROTULO_Y` y `ROTULO_TAM`. Texto gancho: `TEXTO_GANCHO`,
  `GANCHO_SEG`, `GANCHO_Y` y `GANCHO_TAM`. Tarjeta final: `TARJETA_TEXTO`, `TARJETA_SEG`, colores y
  tamaño.
- Tipografías: `FUENTES_NORMAL` y `FUENTES_NEGRITA`. En Windows usa Segoe UI y, si no está, Arial.
- Calidad: `CRF` (18 por defecto) y `MODO_INTERPOLACION`.

## Pruebas

```
python probar.py              # todo, incluido armar un MP4 real (~1.5 min)
python probar.py --sin-video  # sin el MP4 (~15 s)
```

`probar.py` ejecuta `nodo_video.py` completo, igual que Dynamo (variable `IN` y salida `OUT`), contra
el simulador de `mock/`. El modelo sintético es una casa de 2 niveles más azotea, con:

- **Cimentación:** cimiento de mampostería (muros cuyo tipo no dice piedra, pero cuyo material es
  "Piedra braza"), cimientos corridos de concreto, dados, cisterna, cadenas de desplante y firme.
- **Estructura:** columnas, castillos, muros de block, dala de repartición, cerramiento de puerta y
  cadenas.
- **Losas:**
  - losa maciza con volado;
  - losa de vigueta y bovedilla: las viguetas son "mini trabes" cuyo tipo no dice vigueta, las
    bovedillas son modelos genéricos y el firme de compresión lleva malla;
  - losa de azotea.
- **Azotea y exteriores:** pretiles, base de tinaco y tinaco, banqueta y patio exterior.
- **Otros:** escalera, terreno con excavación, una puerta y un muro oculto en la vista base.
- **Piezas:** las pruebas que las usan corren antes `nodo_piezas.py` sobre el modelo (cuyo nombre
  lleva "VIDEO"): unos 4100 blocks, 560 piedras y 22 camas de mortero.
- **Acero:**
  - varillas y estribos en columnas, castillos, cadenas y trabes;
  - parrillas en cimientos y dados;
  - varillas en los muros de la cisterna;
  - refuerzo de área (`RebarInSystem`) en las losas macizas;
  - mallas (`FabricSheet`) en el firme de compresión y en la azotea;
  - una varilla sin anfitrión dentro de una columna y otra fuera de todo concreto.

### Qué está probado (en el simulador, en Linux)

- El nodo corre de punta a punta (en las pruebas, 30 s a 15 fps: 450 cuadros) y devuelve la ruta del
  informe sin errores.
- No cambia la geometría ni borra ningún elemento del modelo. Solo crea una vista nueva y deja
  intacta la vista base (elementos ocultos, orientación y recorte). Los únicos ajustes sobre
  elementos son los gráficos del acero, y solo en la vista de video.
- Antes de 1.5 s solo se ven el terreno y los modelos genéricos. Desde 24 s se ve toda la estructura.
  La obra nunca "se deshace". Puertas, varillas (sin la opción de acero) y el muro oculto en la vista
  base no aparecen nunca.
- El orden de las 20 etapas se respeta en los dos niveles, la azotea y los exteriores, y cada etapa
  crece en varios cuadros (no aparece de golpe).
- Clasificación:
  - cada elemento cae en su etapa, incluidas mampostería y cisterna;
  - la piedra se reconoce por el material y las viguetas por su tamaño, aunque sus tipos no lo digan;
  - la banqueta entra por palabra clave y el patio por estar fuera de la huella;
  - los modelos genéricos sin regla quedan como base;
  - el informe lista los tipos por etapa.
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
  - el acero se ve ("sin obstrucciones") mientras su concreto no aparece, y en cada cuadro en que su
    concreto ya está visible queda tapado; al final solo queda libre el acero sin concreto;
  - todos los ajustes del acero se hacen solo en la vista de video: ninguno toca la vista base;
  - al reanudar tras una caída, el estado visible/tapado del acero en cada cuadro es idéntico al de
    una corrida sin cortes;
  - si después se corre sin acero sobre la misma vista, sus categorías vuelven a ocultarse.
- Reanudación: después de una caída simulada de Revit en el cuadro 120, una segunda corrida salta
  los 119 cuadros hechos y exporta los 331 restantes. Los cuadros reanudados son idénticos byte a
  byte a los de una corrida sin cortes. Una tercera corrida reutiliza la vista y no exporta nada.
- Un error en un cuadro queda en el informe con su traceback, y la siguiente corrida lo completa.
- Piezas (`nodo_piezas.py`):
  - no hace nada si el archivo no tiene "VIDEO" en el nombre;
  - convierte los muros de block y de piedra (la piedra la reconoce por el material) y no toca la
    cisterna ni el concreto;
  - los blocks miden 39 x 19 x 12 cm y van 13 hiladas en un muro de 2.6 m;
  - las hiladas van cuatrapeadas, y la que ocupa la dala no lleva blocks;
  - ninguna pieza invade castillos, columnas, dalas, cerramientos ni la puerta, y las piezas no se
    enciman entre sí;
  - no modifica ningún elemento existente;
  - volver a correrlo no duplica, y "Solo borrar" deja cero piezas.
- Video con piezas:
  - ningún muro sólido sustituido ni pieza huérfana se ve en ningún cuadro;
  - en planta baja, planta alta y mampostería, cada hilada termina antes de que empiece la
    siguiente, y el mortero de cada hilada va antes que sus piedras;
  - los blocks aparecen después de los castillos y antes de las trabes, y las piedras después de
    los dados y antes de la cisterna.
- Una vista base inexistente o en perspectiva produce un informe con el error, sin exportar nada.
- `Video_Obra.dyn` y `Piezas_Obra.dyn` son JSON válido. Su nodo Python tiene `"Engine": "CPython3"`,
  un código idéntico a su `.py` y 6 entradas conectadas del tipo correcto. Por defecto, el video
  dura 60 s con el acero activado, y las piezas son block 40x20x12 con junta de 1 cm.
- `armar_video.py` genera un MP4 H.264 yuv420p de 1080x1920, 30 fps, 900 cuadros y 30.0 s. También
  ordena y renombra los PNG sin depender del sufijo de Revit. Los rótulos salen en orden. Sin acero:
  Cimentación → Cimiento de mampostería → Cisterna → Cimentación → Firme → Castillos y columnas →
  Muros → Trabes y cadenas → Vigueta y bovedilla → Losa → Planta alta → Azotea → Tinaco → Exteriores.
  Con acero, cada etapa que tiene armado muestra antes su rótulo de armado (por ejemplo, "Armado de
  losa" → "Losa").
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
- `Element.GetMaterialIds(False)` y el nombre de cada `Material`: que en tus muros de piedra devuelva
  el material "piedra"/"roca". Si no, agrega una palabra del nombre del tipo a `PALABRAS_PIEDRA`.
- `ElementType.FamilyName`.
- Recoger `OST_GenericModel`, `OST_Roofs` y `OST_Ramps` con el colector por vista.
- `SetUnobscuredInView(vista, True)` al inicio y `SetUnobscuredInView(vista, False)` al colar, y
  `SetSolidInView(vista, True)`, en `Rebar`, `RebarInSystem`, `FabricSheet` y acopladores. Falta
  comprobar tres cosas:
  - si pythonnet expone esos métodos cuando el colector devuelve el elemento como `Element` (si no,
    el informe lo anota en "Acero con ajuste de vista fallido");
  - si en Revit 2025 "Ver como sólido" sigue existiendo o ya lo sustituye el nivel de detalle Alto;
  - cómo se ve en la imagen exportada: que el concreto tape de verdad al acero obstruido, y cuánto
    tarda cada exportación con muchas varillas.
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
- Piezas, todo `nodo_piezas.py` en Revit:
  - `DirectShape.CreateElement(doc, ElementId(BuiltInCategory.OST_GenericModel))`;
  - asignar y leer `ApplicationId` y `ApplicationDataId`. Al leerlos, pythonnet 2.5 debe entregar
    el elemento como `DirectShape`;
  - `SetShape(List[GeometryObject])`;
  - `CurveLoop.Append`, `Line.CreateBound` y
    `GeometryCreationUtilities.CreateExtrusionGeometry(..., SolidOptions(material, ...))`;
  - `Wall.Location.Curve`, `Wall.Width` y `doc.Delete(List[ElementId])`;
  - `FilteredElementCollector(doc).OfClass(DirectShape)`;
  - `doc.Title` y `doc.PathName` para la revisión de "VIDEO";
  - cuánto tarda Revit en crear unas 5000 piezas y en exportar cuadros con ellas;
  - que las piezas tomen el material del muro en la imagen;
  - que en muros con uniones en esquina, en "L" o en "T", o con otro eje de ubicación, los blocks
    no se encimen. En el simulador los muros son cajas rectas.
- Que tus viguetas midan como máximo 13 cm de ancho y 20 cm de peralte (o que su nombre diga
  "vigueta"), y que ninguna cadena o dala sea tan chica (si no, se tomaría por vigueta). La sección
  TIPOS DE REVIT POR ETAPA del informe lo muestra.
- `armar_video.py` y `previa.py` en Windows (se probaron en Linux), incluidas las fuentes Segoe UI y
  Arial.

Si algo falla en Revit, el informe guarda el traceback completo de cada error. Con eso se puede
corregir la llamada exacta.
