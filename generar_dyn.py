# -*- coding: utf-8 -*-
"""Genera los grafos de Dynamo 3.x para Revit 2025 con el código de cada nodo incrustado:

    Video_Obra.dyn   <- nodo_video.py   (exporta los cuadros del video)
    Piezas_Obra.dyn  <- nodo_piezas.py  (crea blocks y piedras en la copia del modelo)

Si editas un nodo, vuelve a correr:   python generar_dyn.py
Así el código de cada grafo queda idéntico al del archivo (probar.py lo comprueba).
"""
import json
import os
import uuid

AQUI = os.path.dirname(os.path.abspath(__file__))
VERSION_DYNAMO = "3.0.3.7597"

# Entradas editables de cada grafo: (nombre visible, tipo, valor por defecto, descripción)
GRAFOS = [
    {
        "prefijo": "video-obra/",
        "nodo": "nodo_video.py",
        "dyn": "Video_Obra.dyn",
        "nombre": "Video_Obra",
        "titulo_nodo": "VIDEO DE OBRA (exporta cuadros)",
        "descripcion": "Exporta cuadros PNG de la obra por etapas con giro de cámara, para un video vertical.",
        "entradas": [
            ("Carpeta de salida", "texto", r"C:\VIDEO_OBRA\cuadros", "Carpeta donde se guardan los PNG y el informe"),
            ("Vista 3D base", "texto", "{3D}", "Nombre exacto de la vista 3D isométrica base"),
            ("FPS de exportación", "numero", 15.0, "Cuadros por segundo que exporta Revit (15 = 900 cuadros en 60 s)"),
            ("Duración (s)", "numero", 60.0, "Duración del video en segundos"),
            ("Grados de giro", "numero", 180.0, "Giro total de la cámara alrededor de la estructura"),
            ("Incluir acero", "booleano", True,
             "Incluir el acero: varillas, barras de refuerzo de área/camino y mallas (armado antes del concreto)"),
            ("Zoom", "numero", 1.25, "1 = casa completa siempre en cuadro; más alto = más cerca (1.5, 2...)"),
        ],
    },
    {
        "prefijo": "piezas-obra/",
        "nodo": "nodo_piezas.py",
        "dyn": "Piezas_Obra.dyn",
        "nombre": "Piezas_Obra",
        "titulo_nodo": "PIEZAS DE OBRA (blocks y piedras, solo en copia VIDEO)",
        "descripcion": "Crea blocks y piedras como DirectShape para el video, solo en una copia del modelo "
                       "cuyo nombre contenga VIDEO.",
        "entradas": [
            ("Largo del block (cm)", "numero", 40.0, "Medida nominal, con junta"),
            ("Alto del block (cm)", "numero", 20.0, "Medida nominal, con junta"),
            ("Espesor del block (cm)", "numero", 12.0, "Espesor del block"),
            ("Junta (cm)", "numero", 1.0, "Junta de mortero entre blocks"),
            ("Piedras en mampostería", "booleano", True, "Convertir los cimientos de piedra en piedras"),
            ("Solo borrar piezas", "booleano", False, "True: borra las piezas creadas antes y no crea nuevas"),
        ],
    },
]

_PREFIJO = ["video-obra/"]


def _gid(texto):
    """GUID estable (sin guiones, como los escribe Dynamo)."""
    return uuid.uuid5(uuid.NAMESPACE_URL, _PREFIJO[0] + texto).hex


def _puerto(gid, nombre, descripcion):
    return {"Id": gid, "Name": nombre, "Description": descripcion, "UsingDefaultValue": False,
            "Level": 2, "UseLevels": False, "KeepListStructure": False}


def _nodo_entrada(i, nombre, tipo, valor, descripcion):
    nid = _gid("entrada-%d" % i)
    salida = _gid("entrada-%d-salida" % i)
    if tipo == "texto":
        nodo = {"ConcreteType": "CoreNodeModels.Input.StringInput, CoreNodeModels",
                "NodeType": "StringInputNode", "InputValue": valor,
                "Outputs": [_puerto(salida, "", "String")], "Description": "Creates a string."}
        jugador = ("string", valor)
    elif tipo == "numero":
        nodo = {"ConcreteType": "CoreNodeModels.Input.DoubleInput, CoreNodeModels",
                "NodeType": "NumberInputNode", "NumberType": "Double", "InputValue": valor,
                "Outputs": [_puerto(salida, "", "Double")], "Description": "Creates a number."}
        jugador = ("number", str(valor))
    else:
        nodo = {"ConcreteType": "CoreNodeModels.Input.BoolSelector, CoreNodeModels",
                "NodeType": "BooleanInputNode", "InputValue": valor,
                "Outputs": [_puerto(salida, "", "Boolean")],
                "Description": "Enables selection between True and False"}
        jugador = ("boolean", "true" if valor else "false")
    nodo.update({"Id": nid, "Inputs": [], "Replication": "Disabled"})
    entrada_jugador = {"Id": nid, "Name": nombre, "Type": jugador[0], "Type2": jugador[0],
                       "Value": jugador[1], "Description": descripcion, "SelectedIndex": 0}
    vista = {"Id": nid, "Name": nombre, "IsSetAsInput": True, "IsSetAsOutput": False,
             "Excluded": False, "ShowGeometry": True, "X": 0.0, "Y": 140.0 * i}
    return nodo, salida, entrada_jugador, vista


def generar_grafo(g):
    _PREFIJO[0] = g["prefijo"]
    with open(os.path.join(AQUI, g["nodo"]), encoding="utf-8") as f:
        codigo = f.read()

    nodos, conectores, jugador, vistas = [], [], [], []
    py_id = _gid("python")
    py_entradas = []
    for i, (nombre, tipo, valor, desc) in enumerate(g["entradas"]):
        nodo, salida, ent, vista = _nodo_entrada(i, nombre, tipo, valor, desc)
        nodos.append(nodo)
        jugador.append(ent)
        vistas.append(vista)
        puerto_py = _gid("python-in-%d" % i)
        py_entradas.append(_puerto(puerto_py, "IN[%d]" % i, "Input #%d" % i))
        conectores.append({"Start": salida, "End": puerto_py, "Id": _gid("conector-%d" % i),
                           "IsHidden": "False"})

    nodos.append({
        "ConcreteType": "PythonNodeModels.PythonNode, PythonNodeModels",
        "Code": codigo,
        "Engine": "CPython3",
        "EngineName": "CPython3",
        "VariableInputPorts": True,
        "NodeType": "PythonScriptNode",
        "Id": py_id,
        "Inputs": py_entradas,
        "Outputs": [_puerto(_gid("python-out"), "OUT", "Result of the python script")],
        "Replication": "Disabled",
        "Description": "Runs an embedded Python script.",
    })
    vistas.append({"Id": py_id, "Name": g["titulo_nodo"], "IsSetAsInput": False,
                   "IsSetAsOutput": True, "Excluded": False, "ShowGeometry": True,
                   "X": 520.0, "Y": 300.0})

    grafo = {
        "Uuid": _gid("grafo"),
        "IsCustomNode": False,
        "Description": g["descripcion"],
        "Name": g["nombre"],
        "ElementResolver": {"ResolutionMap": {}},
        "Inputs": jugador,
        "Outputs": [],
        "Nodes": nodos,
        "Connectors": conectores,
        "Dependencies": [],
        "NodeLibraryDependencies": [],
        "Thumbnail": "",
        "GraphDocumentationURL": None,
        "ExtensionWorkspaceData": [],
        "Author": "",
        "Linting": {"activeLinter": "None", "activeLinterId": "7b75fb44-43fd-4631-a878-29f4d5d8399a",
                    "warningCount": 0, "errorCount": 0},
        "Bindings": [],
        "View": {
            "Dynamo": {"ScaleFactor": 1.0, "HasRunWithoutCrash": False, "IsVisibleInDynamoLibrary": True,
                       "Version": VERSION_DYNAMO, "RunType": "Manual", "RunPeriod": "1000"},
            "Camera": {"Name": "_Background Preview", "EyeX": -17.0, "EyeY": 24.0, "EyeZ": 50.0,
                       "LookX": 12.0, "LookY": -13.0, "LookZ": -58.0, "UpX": 0.0, "UpY": 1.0, "UpZ": 0.0},
            "ConnectorPins": [],
            "NodeViews": vistas,
            "Annotations": [],
            "X": 60.0,
            "Y": 60.0,
            "Zoom": 0.9,
        },
    }
    ruta = os.path.join(AQUI, g["dyn"])
    with open(ruta, "w", encoding="utf-8", newline="\n") as f:
        json.dump(grafo, f, ensure_ascii=False, indent=2)
    return ruta


def generar():
    return [generar_grafo(g) for g in GRAFOS]


if __name__ == "__main__":
    for ruta in generar():
        print("Generado:", ruta)
