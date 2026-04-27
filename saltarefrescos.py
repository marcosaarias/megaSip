import re
import uuid
import unicodedata
import pandas as pd
import io
from io import StringIO

from flask import Blueprint, render_template, request, send_file

from compras import redis_client, completar_ean


saltarefrescos_bp = Blueprint(
    "saltarefrescos",
    __name__,
    url_prefix="/compras/refrescos"
)


SUCURSAL_MAP_REFRESCOS = {
    "Total Empresa": "CO01,CO02,CO04,CO05,CO06,CO07,CO08,CO09,CO10,CO11,CO12,CO14,CO15,CO16,CO17,CO18,CO19,CO20,CO21,CO22,CO23,CO24,CO25,CO26,CO27,CO28,CO29,MA02"
}


def formatear_moneda(valor):
    try:
        if valor == "" or pd.isna(valor):
            return ""

        valor_str = str(valor).replace(",", "").strip()
        num = float(valor_str)

        num_formateado = "{:,.2f}".format(num)
        return num_formateado.replace(",", "X").replace(".", ",").replace("X", ".")

    except (ValueError, TypeError):
        return valor


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


@saltarefrescos_bp.route("/", methods=["GET", "POST"])
def refrescos():
    preview = None
    total_registros = 0
    cache_id = None

    if request.method == "POST":
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

                df_data = df_raw.iloc[header_idx + 1:].copy()

                df_final = pd.DataFrame()

                df_final["CODIGO"] = (
                    df_data.iloc[:, 0]
                    .astype(str)
                    .str.strip()
                    .str.replace(".0", "", regex=False)
                    .str.lstrip("0")
                )

                df_final = completar_ean(df_final)

                df_final["descripcion"] = df_data.iloc[:, 1].astype(str).str.strip()
                df_final["Normal"] = df_data.iloc[:, 2]

                # Columnas según estructura:
                # A Cód. | B Descrip | C Precio | D Accion | E Descarga | F Etiquetas | G/H Sucursales
                df_final["Oferta"] = df_data.iloc[:, 3].replace(
                    ["nan", "None", "", "NaN"], pd.NA
                )

                df_final["Cenefa"] = df_data.iloc[:, 5].replace(
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
                        df_final[col] = df_final[col].apply(formatear_moneda)

                df_final = df_final.fillna("")

                if not df_final.empty:
                    total_registros = len(df_final)

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