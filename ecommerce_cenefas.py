import uuid
import io
from io import StringIO
import pandas as pd

from flask import Blueprint, render_template, request, send_file
from compras import redis_client
from database.db import get_db_connection


ecommerce_cenefas_bp = Blueprint(
    "ecommerce_cenefas",
    __name__,
    url_prefix="/ecommerce/cenefas"
)


SUCURSALES_ECOM = "CO01,CO02,CO04,CO05,CO06,CO07,CO09,CO10,CO14,CO16,CO18,CO20,CO21,CO24,CO25,CO27"
SUCURSALES_SALTA = "CO09,CO18,CO21"
SUCURSALES_JUJUY = "CO01,CO02,CO04,CO05,CO06,CO07,CO09,CO10,CO14,CO16,CO20"
SUCURSALES_TUCUMAN = "CO24,CO25,CO27"


COLUMNAS_SALIDA = [
    "codigo",
    "descripcion",
    "normal",
    "oferta",
    "cenefa",
    "desde",
    "hasta",
    "sucursal"
]


def mapear_sucursal(valor):
    if pd.isna(valor):
        return SUCURSALES_ECOM

    texto = str(valor).strip().lower()

    if texto in ["", "nan", "none"]:
        return SUCURSALES_ECOM

    if "interna" in texto:
        return SUCURSALES_ECOM

    if "jujuy" in texto and "salta" in texto:
        sucursales = SUCURSALES_SALTA.split(",") + SUCURSALES_JUJUY.split(",")
        return ",".join(dict.fromkeys(sucursales))

    if "salta" in texto:
        return SUCURSALES_SALTA

    if "jujuy" in texto:
        return SUCURSALES_JUJUY

    if "tucuman" in texto or "tucumán" in texto:
        return SUCURSALES_TUCUMAN

    return texto.upper()


def formatear_precio_arg(valor):
    try:
        if valor == "" or pd.isna(valor):
            return ""

        num = float(valor)

        return f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    except Exception:
        return valor


def obtener_cenefas_desde_db(fecha_desde, fecha_hasta, tipo_origen):
    conn = get_db_connection()

    try:
        print("DEBUG ECOMMERCE => fecha_desde:", fecha_desde)
        print("DEBUG ECOMMERCE => fecha_hasta:", fecha_hasta)
        print("DEBUG ECOMMERCE => tipo_origen:", tipo_origen)

        query = """
            SELECT
                codigo::text AS codigo,
                descripcion,
                normal,
                oferta,
                cenefa,
                desde,
                hasta,
                sucursales AS sucursal,
                tipo_cenefa
            FROM cenefas
            WHERE LOWER(TRIM(cenefa)) LIKE %s
              AND TRIM(desde::text) = %s
              AND TRIM(hasta::text) = %s
        """

        params = [
            "%oferta%",
            str(fecha_desde).strip(),
            str(fecha_hasta).strip()
        ]

        if tipo_origen != "todos":
            query += " AND LOWER(TRIM(tipo_cenefa)) = %s"
            params.append(tipo_origen.strip().lower())

        query += """
            ORDER BY descripcion ASC
        """

        print("DEBUG ECOMMERCE PARAMS:", params)

        df = pd.read_sql(query, conn, params=params)

        print("DEBUG ECOMMERCE REGISTROS:", len(df))

        return df

    finally:
        conn.close()

@ecommerce_cenefas_bp.route("/", methods=["GET", "POST"])
def cenefas():
    preview = None
    total_registros = 0
    cache_id = None

    if request.method == "POST":
        fecha_desde = request.form.get("fecha_desde")
        fecha_hasta = request.form.get("fecha_hasta")
        tipo_origen = request.form.get("tipo_origen", "todos")

        try:
            cache_id = str(uuid.uuid4())

            #f_desde = pd.to_datetime(fecha_desde).strftime("%d/%m/%Y") if fecha_desde else ""
            #f_hasta = pd.to_datetime(fecha_hasta).strftime("%d/%m/%Y") if fecha_hasta else ""

            f_desde = fecha_desde
            f_hasta = fecha_hasta

            df_final = obtener_cenefas_desde_db(
                f_desde,
                f_hasta,
                tipo_origen
            )

            if df_final.empty:
                preview = """
                <div class='alert alert-warning'>
                    No se encontraron cenefas OFERTA para la vigencia seleccionada.
                </div>
                """
            else:
                df_final["sucursal"] = df_final["sucursal"].apply(mapear_sucursal)

                df_final = df_final.dropna(subset=["codigo"])
                df_final = df_final.fillna("")

                df_final = df_final[COLUMNAS_SALIDA]

                total_registros = len(df_final)

                df_preview = df_final.copy()

                for col in ["normal", "oferta"]:
                    df_preview[col] = df_preview[col].apply(formatear_precio_arg)

                redis_client.set(
                    f"ecommerce_cenefas:{cache_id}",
                    df_preview.to_json(orient="records"),
                    ex=3600
                )

                preview = df_preview.to_html(
                    classes="table table-sm table-hover table-bordered text-center",
                    index=False,
                    na_rep=""
                )

        except Exception as e:
            preview = f"""
            <div class='alert alert-danger'>
                Error generando Cenefas Ecommerce: {e}
            </div>
            """

    return render_template(
        "ecommerce_cenefas.html",
        preview=preview,
        total_registros=total_registros,
        cache_id=cache_id
    )


@ecommerce_cenefas_bp.route("/descargar")
def descargar_cenefas():
    cache_id = request.args.get("cache_id")

    if not cache_id:
        return "Cache inválido", 400

    data = redis_client.get(f"ecommerce_cenefas:{cache_id}")

    if not data:
        return "No hay datos", 404

    df = pd.read_json(StringIO(data), orient="records")

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="cenefas")

    output.seek(0)

    return send_file(
        output,
        download_name="cenefas_ecommerce.xlsx",
        as_attachment=True
    )