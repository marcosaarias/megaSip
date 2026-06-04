import re
import uuid
import unicodedata
import pandas as pd
import io
from io import StringIO

from flask import Blueprint, render_template, request, send_file, session

from compras import (
    redis_client,
    completar_ean,
    completar_departamento,
    completar_dep,
    guardar_cenefas_en_db,
    existen_cenefas_repetidas
)

saltarefrescos_bp = Blueprint(
    "saltarefrescos",
    __name__,
    url_prefix="/compras/refrescos"
)


SUCURSAL_MAP_REFRESCOS = {
    "Total Empresa": "CO01,CO02,CO04,CO05,CO06,CO07,CO08,CO09,CO10,CO11,CO12,CO14,CO15,CO16,CO17,CO18,CO19,CO20,CO21,CO22,CO23,CO24,CO25,CO26,CO27,CO28,CO29,MA02"
}


#def formatear_moneda(valor):
#    try:
#        if valor == "" or pd.isna(valor):
#            return ""

#        valor_str = str(valor).replace(",", "").strip()
#        num = float(valor_str)

#        num_formateado = "{:,.2f}".format(num)
#        return num_formateado.replace(",", "X").replace(".", ",").replace("X", ".")

#    except (ValueError, TypeError):
#        return valor


def limpiar_precio(valor):

    if pd.isna(valor):
        return None

    valor = str(valor).strip()

    if "," in valor and "." in valor:
        valor = valor.replace(".", "").replace(",", ".")

    elif "," in valor:
        valor = valor.replace(",", ".")

    try:
        return float(valor)

    except:
        return None


def normalizar_texto_refrescos(texto):
    if not texto:
        return ""

    texto = str(texto).replace("\xa0", " ")
    texto = texto.lower().strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    texto = re.sub(r"[-_/|,]+", " ", texto)
    texto = " ".join(texto.split())

    return texto


def detectar_columnas_etiquetas(df_raw, header_idx):
    fila_header = df_raw.iloc[header_idx]

    for i, val in enumerate(fila_header):
        texto = normalizar_texto_refrescos(val)

        if "etiqueta" in texto:
            return i, i + 1

    return None, None



def detectar_header_refrescos(df_raw):
    for i, row in df_raw.iterrows():
        valores = [
            normalizar_texto_refrescos(x).replace(".", "").strip()
            for x in row.values
        ]

        fila_texto = " ".join(valores)

        print(f"FILA {i}:", fila_texto, flush=True)

        if (
            "cod" in valores
            or "codigo" in valores
            or "cod" in fila_texto
            or "codigo" in fila_texto
        ):
            print("HEADER DETECTADO EN FILA:", i, flush=True)
            return i

    return None

def obtener_columna(df, posibles_nombres):
    for col in df.columns:
        col_norm = normalizar_texto_refrescos(col).replace(".", "").strip()

        for nombre in posibles_nombres:
            nombre_norm = normalizar_texto_refrescos(nombre).replace(".", "").strip()

            if nombre_norm == col_norm or nombre_norm in col_norm:
                return col

    return None


def validar_columna(nombre, columna):
    if columna is None:
        raise ValueError(f"No se encontró la columna requerida: {nombre}")




def detectar_columna_sucursales(df):
    for i in range(df.shape[1]):
        valores = df.iloc[:, i].astype(str).apply(normalizar_texto_refrescos)

        if valores.str.contains("jujuy|salta|tucuman", na=False).any():
            print(f"Columna de sucursales detectada: {i}", flush=True)
            return i

    print("No se encontró columna de sucursales", flush=True)
    return None


def mapear_sucursales(texto):
    texto = normalizar_texto_refrescos(texto)

    if not texto:
        return ""

    if all(x in texto for x in ["jujuy", "salta", "tucuman"]):
        return SUCURSAL_MAP_REFRESCOS["Total Empresa"]

    return ""


def obtener_columna(df, posibles_nombres):
    for col in df.columns:
        col_norm = normalizar_texto_refrescos(col).replace(".", "").strip()

        for nombre in posibles_nombres:
            nombre_norm = normalizar_texto_refrescos(nombre).replace(".", "").strip()

            if nombre_norm == col_norm or nombre_norm in col_norm:
                return col

    return None


def validar_columna(nombre, columna):
    if columna is None:
        raise ValueError(f"No se encontró la columna requerida: {nombre}")



#@saltarefrescos_bp.route("/", methods=["GET", "POST"])
#def refrescos():
#    preview = None
#    total_registros = 0
#    cache_id = None

#    if request.method == "POST":
#        archivo = request.files.get("archivo")
#        f_desde_raw = request.form.get("fecha_desde")
#        f_hasta_raw = request.form.get("fecha_hasta")

#        if archivo:
#            try:
#                cache_id = str(uuid.uuid4())

#                f_desde = pd.to_datetime(f_desde_raw).strftime("%d/%m/%Y") if f_desde_raw else ""
#                f_hasta = pd.to_datetime(f_hasta_raw).strftime("%d/%m/%Y") if f_hasta_raw else ""

#                df_raw = pd.read_excel(archivo, header=None)

#                header_idx = detectar_header_refrescos(df_raw)

#                if header_idx is None:
#                    raise ValueError("No se encontró la cabecera 'Cód.' en el archivo.")

#                col_cenefa_idx, col_oferta_idx = detectar_columnas_etiquetas(df_raw, header_idx)
                

#                if col_cenefa_idx is None or col_oferta_idx is None:
#                    raise ValueError("No se pudieron detectar columnas de Etiquetas")
                                

#                if header_idx is None:
#                    raise ValueError("No se encontró la cabecera 'Cód.' en el archivo.")

#                df_data = df_raw.iloc[header_idx:].copy()
#                df_data.columns = df_data.iloc[0]
#                df_data = df_data.iloc[1:].copy()

#                df_data.columns = [
#                    normalizar_texto_refrescos(col).replace(".", "").strip()
#                    for col in df_data.columns
#                ]

#                print("COLUMNAS DETECTADAS:", list(df_data.columns), flush=True)

#                col_codigo = obtener_columna(df_data, ["cod", "codigo"])
#                col_desc = obtener_columna(df_data, ["descrip", "descripcion"])
#                col_precio = obtener_columna(df_data, ["precio", "normal"])

#                validar_columna("CODIGO", col_codigo)
#                validar_columna("DESCRIPCION", col_desc)
#                validar_columna("NORMAL / PRECIO", col_precio)
        
#                df_final = pd.DataFrame()

#                df_final["CODIGO"] = (
#                    df_data[col_codigo]
#                    .astype(str)
#                    .str.strip()
#                    .str.replace(".0", "", regex=False)
#                    .str.lstrip("0")
#                )

#                df_final = completar_ean(df_final)

#                df_final["descripcion"] = df_data[col_desc].astype(str).str.strip()
#                df_final["Normal"] = df_data[col_precio]

#                df_final["Oferta"] = df_data.iloc[:, col_cenefa_idx].replace(
#                    ["nan", "None", "", "NaN"], pd.NA
#                )

#                df_final["Cenefa"] = df_data.iloc[:, col_oferta_idx].replace(
#                    ["nan", "None", "", "NaN"], pd.NA
#                )

#                df_final["desde"] = f_desde
#                df_final["hasta"] = f_hasta

#                col_suc = detectar_columna_sucursales(df_data)

#                if col_suc is None:
#                    raise ValueError("No se pudo detectar la columna de sucursales")

#                df_final["Sucursales"] = df_data.iloc[:, col_suc]

#                df_final["Sucursales"] = df_final["Sucursales"].astype(str)
#                df_final["Sucursales"] = df_final["Sucursales"].apply(normalizar_texto_refrescos)

#                df_final["Sucursales"] = df_final["Sucursales"].apply(
#                    lambda x: x if ("jujuy" in x or "salta" in x or "tucuman" in x) else pd.NA
#                )

#                cols_to_fill = ["Oferta", "Cenefa", "Sucursales"]
#                df_final[cols_to_fill] = df_final[cols_to_fill].ffill()

#                df_final["Sucursales"] = df_final["Sucursales"].apply(mapear_sucursales)

#                df_final["CODIGO"] = pd.to_numeric(df_final["CODIGO"], errors="coerce")
#                df_final = df_final.dropna(subset=["CODIGO"])
#                df_final["CODIGO"] = df_final["CODIGO"].astype(int)

#                df_final["descripcion"] = df_final["descripcion"].replace(
#                    ["nan", "None", "NaN"], ""
#                ).fillna("")

#                for col in ["Normal", "Oferta"]:
#                    if col in df_final.columns:
#                        df_final[col] = df_final[col].apply(formatear_moneda)

#                df_final = df_final.fillna("")

#                if not df_final.empty:
#                    total_registros = len(df_final)

#                    redis_client.set(
#                        f"refrescos:{cache_id}",
#                        df_final.to_json(orient="records"),
#                        ex=3600
#                    )

#                    print("Cache omitido (Redis no disponible)")

#                    preview = df_final.to_html(
#                        classes="table table-sm table-hover table-bordered text-center",
#                        index=False,
#                        na_rep=""
#                    )
#                else:
#                    preview = "<div class='alert alert-warning'>No se encontraron registros válidos.</div>"

#            except Exception as e:
#                preview = f"<div class='alert alert-danger'>Error procesando Refrescos: {e}</div>"

#    return render_template(
#        "saltarefrescos.html",
#        preview=preview,
#        total_registros=total_registros,
#        cache_id=cache_id
#    )


@saltarefrescos_bp.route("/", methods=["GET", "POST"])
def refrescos():
    preview = None
    total_registros = 0
    cache_id = None

    if request.method == "POST":

        accion = request.form.get("accion")

        # ================= TRANSMITIR =================
        if accion == "transmitir":
            cache_id = request.form.get("cache_id")

            if not cache_id:
                preview = "<div class='alert alert-danger'>Cache inválido.</div>"
                return render_template(
                    "saltarefrescos.html",
                    preview=preview,
                    total_registros=0,
                    cache_id=None
                )

            data = redis_client.get(f"refrescos:{cache_id}")

            if not data:
                preview = "<div class='alert alert-danger'>No hay datos para transmitir. Volvé a procesar el archivo.</div>"
                return render_template(
                    "saltarefrescos.html",
                    preview=preview,
                    total_registros=0,
                    cache_id=None
                )

            try:
                df = pd.read_json(StringIO(data), orient="records")

                df = df.rename(columns={
                    "ean": "EAN",
                    "descripcion": "DESCRIPCION",
                    "Cenefa": "cenefa",
                    "Sucursales": "sucursales"
                })

                if "dep" not in df.columns:
                    df["dep"] = ""

                if "departamento" not in df.columns:
                    df["departamento"] = ""

                repetidos = existen_cenefas_repetidas(df, "saltarefrescos")

                if repetidos:
                    preview = (
                        f"<div class='alert alert-warning'>"
                        f"Ya existen {len(repetidos)} registros de Salta Refrescos para este período."
                        f"</div>"
                    )

                    return render_template(
                        "saltarefrescos.html",
                        preview=preview,
                        total_registros=len(df),
                        cache_id=cache_id
                    )

                guardar_cenefas_en_db(
                    df,
                    "saltarefrescos",
                    usuario=session.get("usuario_nombre", "desconocido")
                )

                redis_client.delete(f"refrescos:{cache_id}")

                preview = "<div class='alert alert-success'>Salta Refrescos transmitido correctamente a sucursales.</div>"

                return render_template(
                    "saltarefrescos.html",
                    preview=preview,
                    total_registros=0,
                    cache_id=None
                )

            except Exception as e:
                preview = f"<div class='alert alert-danger'>Error transmitiendo Refrescos: {e}</div>"

                return render_template(
                    "saltarefrescos.html",
                    preview=preview,
                    total_registros=0,
                    cache_id=cache_id
                )

        # ================= PROCESAR ARCHIVO =================
        archivo = request.files.get("archivo")
        f_desde_raw = request.form.get("fecha_desde")
        f_hasta_raw = request.form.get("fecha_hasta")

        if archivo:
            try:
                cache_id = str(uuid.uuid4())

                f_desde = pd.to_datetime(f_desde_raw).strftime("%d/%m/%Y") if f_desde_raw else ""
                f_hasta = pd.to_datetime(f_hasta_raw).strftime("%d/%m/%Y") if f_hasta_raw else ""

                df_raw = pd.read_excel(archivo, header=None)

                header_idx = detectar_header_refrescos(df_raw)

                if header_idx is None:
                    raise ValueError("No se encontró la cabecera 'Cód.' en el archivo.")

                col_cenefa_idx, col_oferta_idx = detectar_columnas_etiquetas(df_raw, header_idx)

                if col_cenefa_idx is None or col_oferta_idx is None:
                    raise ValueError("No se pudieron detectar columnas de Etiquetas")

                df_data = df_raw.iloc[header_idx:].copy()
                df_data.columns = df_data.iloc[0]
                df_data = df_data.iloc[1:].copy()

                df_data.columns = [
                    normalizar_texto_refrescos(col).replace(".", "").strip()
                    for col in df_data.columns
                ]

                print("COLUMNAS DETECTADAS:", list(df_data.columns), flush=True)

                col_codigo = obtener_columna(df_data, ["cod", "codigo"])
                col_desc = obtener_columna(df_data, ["descrip", "descripcion"])
                col_precio = obtener_columna(df_data, ["precio", "normal"])

                validar_columna("CODIGO", col_codigo)
                validar_columna("DESCRIPCION", col_desc)
                validar_columna("NORMAL / PRECIO", col_precio)

                df_final = pd.DataFrame()

                df_final["CODIGO"] = (
                    df_data[col_codigo]
                    .astype(str)
                    .str.strip()
                    .str.replace(".0", "", regex=False)
                    .str.lstrip("0")
                )

                df_final = completar_ean(df_final)
                df_final = completar_departamento(df_final)
                df_final = completar_dep(df_final)


                df_final["descripcion"] = df_data[col_desc].astype(str).str.strip()
                df_final["Normal"] = df_data[col_precio]

                df_final["Oferta"] = df_data.iloc[:, col_cenefa_idx].replace(
                    ["nan", "None", "", "NaN"], pd.NA
                )

                df_final["Cenefa"] = df_data.iloc[:, col_oferta_idx].replace(
                    ["nan", "None", "", "NaN"], pd.NA
                )

                df_final["desde"] = f_desde
                df_final["hasta"] = f_hasta

                col_suc = detectar_columna_sucursales(df_data)

                if col_suc is None:
                    raise ValueError("No se pudo detectar la columna de sucursales")

                df_final["Sucursales"] = df_data.iloc[:, col_suc]

                df_final["Sucursales"] = df_final["Sucursales"].astype(str)
                df_final["Sucursales"] = df_final["Sucursales"].apply(normalizar_texto_refrescos)

                df_final["Sucursales"] = df_final["Sucursales"].apply(
                    lambda x: x if ("jujuy" in x or "salta" in x or "tucuman" in x) else pd.NA
                )

                cols_to_fill = ["Oferta", "Cenefa", "Sucursales"]
                df_final[cols_to_fill] = df_final[cols_to_fill].ffill()

                df_final["Sucursales"] = df_final["Sucursales"].apply(mapear_sucursales)

                df_final["CODIGO"] = pd.to_numeric(df_final["CODIGO"], errors="coerce")
                df_final = df_final.dropna(subset=["CODIGO"])
                df_final["CODIGO"] = df_final["CODIGO"].astype(int)

                df_final["descripcion"] = df_final["descripcion"].replace(
                    ["nan", "None", "NaN"], ""
                ).fillna("")

                for col in ["Normal", "Oferta"]:
                    if col in df_final.columns:
                       # df_final[col] = df_final[col].apply(formatear_moneda)
                       df_final[col] = df_final[col].apply(limpiar_precio)

                df_final = df_final.fillna("")

                if not df_final.empty:
                    total_registros = len(df_final)

                    df_final = df_final.rename(columns={
                        "descripcion": "DESCRIPCION",
                        "Cenefa": "cenefa",
                        "Sucursales": "sucursales"
                    })

                    redis_client.set(
                        f"refrescos:{cache_id}",
                        df_final.to_json(orient="records"),
                        ex=3600
                    )

                    preview = df_final.to_html(
                        classes="table table-sm table-hover table-bordered text-center",
                        index=False,
                        na_rep=""
                    )
                else:
                    preview = "<div class='alert alert-warning'>No se encontraron registros válidos.</div>"

            except Exception as e:
                preview = f"<div class='alert alert-danger'>Error procesando Refrescos: {e}</div>"

    return render_template(
        "saltarefrescos.html",
        preview=preview,
        total_registros=total_registros,
        cache_id=cache_id
    )


@saltarefrescos_bp.route("/descargar")
def descargar_refrescos():
    cache_id = request.args.get("cache_id")

    if not cache_id:
        return "Cache inválido", 400

    data = redis_client.get(f"refrescos:{cache_id}")

    if not data:
        return "No hay datos", 404

    df = pd.read_json(StringIO(data), orient="records")

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Hoja1")

    output.seek(0)

    return send_file(
        output,
        download_name="refrescos.xlsx",
        as_attachment=True
    )