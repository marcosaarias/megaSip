import io
import pandas as pd
from flask import Flask, request, render_template, send_file, Blueprint
import re
import json
from datetime import datetime
from sistemas import login_requerido
import os
from dotenv import load_dotenv
from dbfread import DBF
promociones_bp = Blueprint("promociones", __name__, url_prefix="/promociones")

load_dotenv()

# ---------------------------------------------------
# OBTENER IP DESDE .ENV
# ---------------------------------------------------
def obtener_ip_sucursal(codigo):
     variable = f"IP_CAJAS_{codigo.upper()}"
     return os.getenv(variable)


# ---------------------------------------------------
# NORMALIZAR CODIGO (quita ceros izquierda y limpia)
# ---------------------------------------------------
def normalizar_codigo(valor):
    if valor is None:
         return ""

 valor = str(valor).strip()
 valor = valor.lstrip("0")

     if valor == "":
        valor = "0"

     return valor


# ---------------------------------------------------
# 🎯 OBTENER TIPO DE PROMOCIÓN SEGÚN CANASTA
# ---------------------------------------------------
def obtener_tipo_promocion(canasta):

     if not canasta:
         return "Descuento Total"

     canasta = int(canasta)
    
     if canasta == 200:
         return "Feria de Frutas y Verduras"

    elif canasta in [201, 202]:
         return "Feria Pollo Trozado"
    
    elif canasta in [203, 204]:
         return "Feria de Carnes de Cerdo"

    elif canasta == 206:
         return "Feria de Vinos"

    elif canasta in [207, 208]:
         return "Feria de Panadería"

    elif 532 <= canasta <= 553:
         return "Feria de Perfumería y Limpieza"

    elif 700 <= canasta <= 800:
         return "Vencimientos"


 return "Descuento Total"


# ---------------------------------------------------
# OBTENER DESCRIPCIONES DESDE MPLU.DBF
# ---------------------------------------------------
def cargar_descripciones_materiales():

 ruta_base = os.getenv("MATERIALES_DESCRIPCION_MA02")

     if not ruta_base:
         print("❌ Variable MATERIALES_DESCRIPCION_MA02 no definida")
             return {}

     ruta_mplu = fr"\\{ruta_base}\mplu.dbf"

     if not os.path.exists(ruta_mplu):
         print("❌ No existe mplu.dbf")
         return {}

    tabla = DBF(ruta_mplu, encoding="latin-1", load=True)

     descripciones = {}

     for row in tabla:
         cod = row.get("Cod") or row.get("COD")
         des = row.get("Des") or row.get("DES")

         if cod is None:
             continue

     codigo_limpio = normalizar_codigo(cod)
     descripcion_limpia = str(des).strip() if des else ""

     descripciones[codigo_limpio] = descripcion_limpia

     print("✔ Materiales cargados desde mplu:", len(descripciones))
     return descripciones


# ---------------------------------------------------
# PARSEAR PROMO.INI
# ---------------------------------------------------
def parsear_promo_ini(path):
     promociones = []

     if not os.path.exists(path):
         return promociones

     with open(path, "r", encoding="latin-1") as f:
     contenido = f.read()

    bloques = re.findall(r"\[(promo\d+)\](.*?)(?=\n\[|$)", contenido, re.S | re.I)

    for nombre, bloque in bloques:

        if "activa = si" not in bloque.lower():
             continue

        canasta_match = re.search(r"VENTA_LISTA\s*\(\s*(\d+)\s*\)", bloque, re.I)
        canasta = canasta_match.group(1) if canasta_match else None

        fecha_match = re.search(r"EN_FECHA\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", bloque, re.I)
        desde = fecha_match.group(1) if fecha_match else None
        hasta = fecha_match.group(2) if fecha_match else None

        desc_match = re.search(
            r"DESC_TOTAL\s*\(\s*(\d+)\s*,.*?,\s*(\d+)\s*\)", bloque, re.I
        )

        if desc_match:
            porcentaje = int(desc_match.group(1)) / 100
            descarga = desc_match.group(2)
        else:
            porcentaje = None
            descarga = None

        promociones.append({
            "canasta": canasta,
            "desde": desde,
            "hasta": hasta,
            "porcentaje": porcentaje,
            "descarga": descarga
        })

    return promociones


# ---------------------------------------------------
# OBTENER MATERIALES DESDE CANASTAS.DBF
# ---------------------------------------------------
def obtener_materiales_de_canasta(path_dbf, numero_canasta):

    if not os.path.exists(path_dbf):
        return []

    tabla = DBF(path_dbf, encoding="latin-1")

    materiales = []

    for row in tabla:
        valor_id = row.get("Id") or row.get("ID")

        if valor_id is None:
            continue

        if int(valor_id) == int(numero_canasta):
            cod = row.get("Cod") or row.get("COD")
            if cod:
                materiales.append(normalizar_codigo(cod))

    return materiales


# ---------------------------------------------------
# RUTA PRINCIPAL
# ---------------------------------------------------
@promociones_bp.route("/", methods=["GET", "POST"])
@login_requerido("sistemas")
def index():

    rows = []

    if request.method == "POST":

        print("========== DEBUG PROMOCIONES ==========")

        sucursal = request.form.get("sucursal")
        ip = obtener_ip_sucursal(sucursal)

        if not ip:
            return render_template(
                     "promociones.html",
                rows=[],
                error="Sucursal no encontrada"
            )

        ruta_ini = fr"\\{ip}\cajas\diego\promo.ini"
        ruta_dbf = fr"\\{ip}\cajas\diego\canastas.dbf"

        promos = parsear_promo_ini(ruta_ini)

        descripciones_materiales = cargar_descripciones_materiales()

        for p in promos:

            if not p["canasta"]:
                continue

        materiales = obtener_materiales_de_canasta(ruta_dbf, p["canasta"])

            estado = "Sin fecha"
            vigencia = "-"

            if p["desde"] and p["hasta"]:
                fecha_desde = datetime.strptime(p["desde"], "%Y%m%d")
                fecha_hasta = datetime.strptime(p["hasta"], "%Y%m%d")
                hoy = datetime.now()

                vigencia = f"{fecha_desde.strftime('%d/%m/%Y')} - {fecha_hasta.strftime('%d/%m/%Y')}"

                if fecha_desde <= hoy <= fecha_hasta:
                    estado = "Vigente"
                else:
                    estado = "Vencido"

            porcentaje_str = "-"
            if p["porcentaje"] is not None:
                porcentaje_str = f"{int(p['porcentaje'])} %"

            tipo_promocion = obtener_tipo_promocion(p["canasta"])

            for material in materiales:

                descripcion_real = descripciones_materiales.get(
                    material,
                    f"Material {material}"
            )

                rows.append({
                    "material": material,
                    "descripcion": descripcion_real,
                    "vigencia": vigencia,
                    "promocion": porcentaje_str,
                    "tipo_promocion": tipo_promocion,
                    "descarga": p["descarga"] if p["descarga"] else "-",
                    "sucursal": sucursal,
                    "estado": estado
                })

        print("Filas finales:", len(rows))
        print("=======================================")

    return render_template("promociones.html", rows=rows)