import uuid
import io
from io import StringIO
import pandas as pd

from flask import Blueprint, render_template, request, send_file
from compras import redis_client


ecommerce_cenefas_bp = Blueprint(
    "ecommerce_cenefas",
    __name__,
    url_prefix="/ecommerce/cenefas"
)


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


def formatear_precio_arg(valor):
    try:
        if valor == "" or pd.isna(valor):
            return ""

        num = float(valor)

        return f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    except Exception:
        return valor


def normalizar_texto(valor):
    return str(valor).lower().strip()


def detectar_fila_header(df_raw):
    for i, row in df_raw.iterrows():
        valores = [normalizar_texto(x) for x in row.values]

        if (
            "codigo" in valores
            and "descripcion" in valores
            and "normal" in valores
            and "oferta" in valores
        ):
            return i

    return None


def normalizar_columnas(df):
    df.columns = (
        df.columns
        .astype(str)
        .str.lower()
        .str.strip()
    )

    df = df.rename(columns={
        "cenefas": "cenefa"
    })

    return df


@ecommerce_cenefas_bp.route("/", methods=["GET", "POST"])
def cenefas():
    preview = None
    total_registros = 0
    cache_id = None

    if request.method == "POST":
        archivo = request.files.get("archivo")
        fecha_desde = request.form.get("fecha_desde")
        fecha_hasta = request.form.get("fecha_hasta")

        if archivo:
            try:
                cache_id = str(uuid.uuid4())

                f_desde = pd.to_datetime(fecha_desde).strftime("%d/%m/%Y") if fecha_desde else ""
                f_hasta = pd.to_datetime(fecha_hasta).strftime("%d/%m/%Y") if fecha_hasta else ""

                excel = pd.ExcelFile(archivo)

                hojas = [h.lower().strip() for h in excel.sheet_names]

                if "cenefas" not in hojas:
                    raise ValueError("El archivo debe tener una hoja llamada 'cenefas'.")

                nombre_hoja = excel.sheet_names[hojas.index("cenefas")]

                df_raw = pd.read_excel(
                    excel,
                    sheet_name=nombre_hoja,
                    header=None
                )

                header_idx = detectar_fila_header(df_raw)

                if header_idx is None:
                    raise ValueError("No se pudo detectar la fila de encabezados.")

                df = pd.read_excel(
                    excel,
                    sheet_name=nombre_hoja,
                    header=header_idx
                )

                df = normalizar_columnas(df)

                columnas_necesarias = [
                    "codigo",
                    "descripcion",
                    "normal",
                    "oferta",
                    "cenefa"
                ]

                faltantes = [col for col in columnas_necesarias if col not in df.columns]

                if faltantes:
                    raise ValueError(f"Faltan columnas requeridas: {', '.join(faltantes)}")

                df_final = df[columnas_necesarias].copy()

                # Conservar únicamente las filas cuya cenefa sea "Oferta"
                df_final = df_final[
                    df_final["cenefa"]
                    .astype(str)
                    .str.strip()
                    .str.lower()
                    .eq("oferta")
                ]

                df_final["desde"] = f_desde
                df_final["hasta"] = f_hasta
                df_final["sucursal"] = ""

                df_final = df_final.dropna(subset=["codigo"])
                df_final = df_final.fillna("")

                df_final = df_final[COLUMNAS_SALIDA]

                if not df_final.empty:
                    total_registros = len(df_final)

                    # Copia solo para previsualización y descarga
                    df_final_preview = df_final.copy()

                    for col in ["normal", "oferta"]:
                        if col in df_final_preview.columns:
                            df_final_preview[col] = df_final_preview[col].apply(formatear_precio_arg)

                    redis_client.set(
                        f"ecommerce_cenefas:{cache_id}",
                        df_final_preview.to_json(orient="records"),
                        ex=3600
                    )

                    preview = df_final_preview.to_html(
                        classes="table table-sm table-hover table-bordered text-center",
                        index=False,
                        na_rep=""
                    )
                else:
                    preview = "<div class='alert alert-warning'>No se encontraron registros válidos con cenefa OFERTA.</div>"

            except Exception as e:
                preview = f"<div class='alert alert-danger'>Error procesando Cenefas: {e}</div>"

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
        download_name="cenefas.xlsx",
        as_attachment=True
    )