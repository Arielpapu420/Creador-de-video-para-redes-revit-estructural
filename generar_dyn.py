# -*- coding: utf-8 -*-
"""Genera Video_Obra.dyn (Dynamo 3.x para Revit 2025) con el código de nodo_video.py incrustado.

Si editas nodo_video.py, vuelve a correr:   python generar_dyn.py
Así el código del grafo queda idéntico al del archivo (probar.py lo comprueba).
"""
import json
import os
import uuid

AQUI = os.path.dirname(os.path.abspath(__file__))
RUTA_NODO = os.path.join(AQUI, "nodo_video.py")
RUTA_DYN = os.path.join(AQUI, "Video_Obra.dyn")
VERSION_DYNAMO = "3.0.3.7597"

# Entradas editables: (nombre visible, tipo, valor por defecto, descripción)
ENTRADAS = [
    ("Carpeta de salida", "texto", r"C:\VIDEO_OBRA\cuadros", "Carpeta donde se guardan los PNG y el informe"),
    ("Vista 3D base", "texto", "{3D}", "Nombre exacto de la vista 3D isométrica base"),
    ("FPS de exportación", "numero", 15.0, "Cuadros por segundo que exporta Revit (15 = 450 cuadros en 30 s)"),
    ("Duración (s)", "numero", 30.0, "Duración del video en segundos"),
    ("Grados de giro", "numero", 180.0, "Giro total de la cámara alrededor de la estructura"),
    ("Incluir acero", "booleano", True,
     "Incluir el acero: varillas, barras de refuerzo de área/camino y mallas (armado antes del concreto)"),
]


def _gid(texto):
    """GUID estable (sin guiones, como los escribe Dynamo)."""
    return uuid.uuid5(uuid.NAMESPACE_URL, "video-obra/" + texto).hex


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


def generar():
    with open(RUTA_NODO, encoding="utf-8") as f:
        codigo = f.read()

    nodos, conectores, jugador, vistas = [], [], [], []
    py_id = _gid("python")
    py_entradas = []
    for i, (nombre, tipo, valor, desc) in enumerate(ENTRADAS):
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
    vistas.append({"Id": py_id, "Name": "VIDEO DE OBRA (exporta cuadros)", "IsSetAsInput": False,
                   "IsSetAsOutput": True, "Excluded": False, "ShowGeometry": True,
                   "X": 520.0, "Y": 300.0})

    grafo = {
        "Uuid": _gid("grafo"),
        "IsCustomNode": False,
        "Description": "Exporta cuadros PNG de la obra por etapas con giro de cámara, para un video vertical.",
        "Name": "Video_Obra",
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
    with open(RUTA_DYN, "w", encoding="utf-8", newline="\n") as f:
        json.dump(grafo, f, ensure_ascii=False, indent=2)
    return RUTA_DYN


if __name__ == "__main__":
    print("Generado:", generar())
