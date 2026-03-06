import io
import pandas as pd
from flask import Flask, request, render_template, send_file, Blueprint
import re
import json
from datetime import datetime
from sistemas import login_requerido

vencimientos_bp = Blueprint("vencimientos", __name__, url_prefix="/vencimientos")

HEADERS = [
    "Codigo",
    "Descripcion",
    "sucursal",
    "PROMO",
    "accion",
    "descuento",
    "descarga",
    "cantidad",
    "addcant",
    "rappel",
    "canper",
    "desde",
    "hasta",
]

SUCURSAL_MAP = {
    "Total Empresa": "CO01,CO02,CO04,CO05,CO06,CO07,CO08,CO09,CO10,CO11,CO12,CO14,CO15,CO16,CO17,CO18,CO19,CO20,CO21,CO22,CO23,CO24,CO25,CO26,CO27,CO29,MA02",
    "Total Empresa - Mayorista": "CO05,CO09,CO12,CO15,CO21,CO29,MA02",
    "Jujuy - Mayorista": "CO05,CO12,CO15,MA02",
    "Salta - Mayorista": "CO09,CO29,CO21",
    "Oran - Mayorista": "CO21",
    "Total Empresa Minorista": "CO01,CO02,CO04,CO06,CO07,CO08,CO10,CO11,CO14,CO16,CO17,CO18,CO19,CO20,CO22,CO23,CO24,CO25,CO26,CO27",
    "Jujuy - Minorista": "CO01,CO02,CO04,CO06,CO07,CO08,CO10,CO11,CO14,CO16,CO17,CO19,CO20,CO22",
    "Salta - Minoristas": "CO18,CO23",
    "Jujuy, Salta - Minoritas": "CO01,CO02,CO04,CO06,CO07,CO08,CO10,CO11,CO14,CO16,CO17,CO18,CO19,CO20,CO22,CO23",
    "Jujuy, Salta - Minoritas y Mayoristas": "CO01,CO02,CO04,CO05,CO06,CO07,CO08,CO09,CO10,CO11,CO12,CO14,CO15,CO16,CO17,CO18,CO19,CO20,CO21,CO22,CO23,CO29,MA02",
    "Tucuman - Minoristas": "CO24,CO25,CO26,CO27",
}

MAYORISTA = {"05": "CO05", "09": "CO09", "12": "CO12", "15": "CO15", "21": "CO21", "29": "CO29", "MA02": "MA02"}
MINORISTA = {
    "01": "CO01", "02": "CO02", "04": "CO04", "06": "CO06", "07": "CO07", "08": "CO08",
    "10": "CO10", "11": "CO11", "14": "CO14", "16": "CO16", "17": "CO17", "18": "CO18",
    "19": "CO19", "20": "CO20", "22": "CO22", "23": "CO23", "24": "CO24", "25": "CO25",
    "26": "CO26", "27": "CO27"
}

ALIAS = {
    "sucursal": ["sucursal", "sucursales", "branch", "branches"],
    "descarga": ["descarga", "descargas"],
    "codigo": ["codigo", "cod", "Material", "material"],
    "descripcion": ["descripcion", "description", "desc"],
    "desde": ["desde", "from"],
    "hasta": ["hasta", "to"],
    "promo": ["acciones", "acciones a realizar", "actions"]
}

MAYORISTA_CODES = set(MAYORISTA.values())
MINORISTA_CODES = set(MINORISTA.values())


def get_column_name(df, aliases, default):
    for col in df.columns:
        if str(col).strip().lower() in [a.lower() for a in aliases.get(default, [])]:
            return col
    return None

def parse_table_data(table_data):
    try:
        data_list = json.loads(table_data)
        safe_data = [{k: str(v) if v is not None else "" for k, v in row.items()} for row in data_list]
        df = pd.DataFrame(safe_data)
        return df
    except Exception as e:
        raise ValueError(f"Error al parsear JSON: {e}")

def clean_descarga(val):
    if pd.isna(val) or str(val).strip() == "":
        return ""
    try:
        f = float(val)
        if f.is_integer():
            return str(int(f))
        return str(f)
    except Exception:
        return str(val)

def autocomplete_descarga(df):
    if "descarga" not in df.columns:
        return df

    df["descarga"] = df["descarga"].apply(clean_descarga)
    df["descarga"] = df["descarga"].replace("", pd.NA)
    df["descarga"] = df["descarga"].ffill()
    df["descarga"] = df["descarga"].fillna("")

    return df

def parse_promo_for_df(promo_text):
    if not promo_text or str(promo_text).strip() == "":
        return "", ""
    promo_text = str(promo_text).strip()
    m = re.match(r"(\d+)x(\d+)", promo_text.lower())
    if m:
        return "mxn", 1
    number_match = re.search(r'\d+(\.\d+)?', promo_text)
    if number_match:
        num = float(number_match.group())
        number = int(num) if num.is_integer() else num
    else:
        number = ""
    if "%" in promo_text:
        action = "%"
    elif "$" in promo_text:
        action = "$"
    else:
        action = ""
    return action, number



def cantidad_from_promo(promo):
    if not promo or str(promo).strip() == "":
        return None

    promo = str(promo).lower().strip()
    m = re.match(r"(\d+)\s*x\s*(\d+)", promo)
    if m:
        return int(m.group(1))
    return None



def standardize_dataframe(df):
    standard_cols = ["Codigo", "Descripcion", "sucursal", "PROMO", "descarga",
                     "cantidad", "addcant", "rappel", "canper", "desde", "hasta"]
    
    new_data = {}
    for std_name in standard_cols:
        alias_key = std_name.lower()
        if std_name == "PROMO":
            orig_name = get_column_name(df, ALIAS, "promo")
        else:
            orig_name = get_column_name(df, ALIAS, alias_key)
        
        if orig_name and orig_name in df.columns:
            new_data[std_name] = df[orig_name]
        else:
            new_data[std_name] = [""] * len(df)
    
    df_std = pd.DataFrame(new_data)

    df_std[["accion", "descuento"]] = df_std["PROMO"].apply(lambda x: pd.Series(parse_promo_for_df(x)))
    df_std["cantidad"] = pd.to_numeric(df_std["cantidad"], errors="coerce")
    cantidad_promo = df_std["PROMO"].apply(cantidad_from_promo)
    df_std["cantidad"] = df_std["cantidad"].fillna(cantidad_promo)
    df_std["cantidad"] = df_std["cantidad"].fillna(1).astype(int)
    df_std["addcant"] = df_std["addcant"].replace("", 0).astype(int)
    df_std["rappel"] = df_std["rappel"].replace("", 0).astype(int)
    df_std["canper"] = df_std["canper"].replace("", 1).astype(int)

    return df_std

def parse_sucursales(raw):
    if pd.isna(raw) or str(raw).strip() == "":
        return []
    raw_str = str(raw).strip()

    raw_str = re.sub(r"[^A-Za-z0-9\-]", "-", raw_str)
    parts = [p.strip().upper() for p in raw_str.split("-") if p.strip() and p.lower() != "nan"]

    result = []
    prefix = None
    for p in parts:
        if p.startswith("COM"):
            prefix = "CO"
            continue
        elif p.startswith("M"):
            num = p[1:]
            if num.isdigit():
                result.append(f"MA{num.zfill(2)}")
        elif p.startswith("CO"):
            num = p[2:]
            if num.isdigit():
                result.append(f"CO{num.zfill(2)}")
        elif p.isdigit():
            if prefix == "CO":
                result.append(f"CO{p.zfill(2)}")
        else:
            m = re.search(r"\d+", p)
            if m:
                result.append(f"CO{m.group().zfill(2)}")

    valid_codes = set(MAYORISTA.values()) | set(MINORISTA.values())
    result = [r for r in result if r in valid_codes]

    return sorted(set(result))

@vencimientos_bp.route("/", methods=["GET"])
@login_requerido("sistemas")
def index():
    return render_template("vencimientos.html", sucursales=SUCURSAL_MAP)

@vencimientos_bp.route("/preview", methods=["POST"])
def preview():
    try:
        file = request.files["file"]
        df = pd.read_excel(file)
        df.rename(columns=lambda c: str(c).strip(), inplace=True)

        df_standardized = standardize_dataframe(df)
        df_standardized = autocomplete_descarga(df_standardized)

        rows = []
        for _, row in df_standardized.iterrows():
            suc = row.get("sucursal", "")
            sucursales_finales = parse_sucursales(suc)

            new_row = row.to_dict()
            new_row["sucursal"] = ",".join(sucursales_finales)
            rows.append(new_row)

        df_expanded = pd.DataFrame(rows)
        df_expanded.fillna("", inplace=True)

        columns = df_expanded.columns.tolist()
        table_data = df_expanded.to_dict(orient="records")

        return render_template(
            "vencimientos.html",
            preview=True,
            columns=columns,
            rows=table_data,
            table_data=json.dumps(table_data),
            sucursales=SUCURSAL_MAP
        )

    except Exception as e:
        return f"Error procesando archivo: {type(e).__name__}: {e}", 500

def get_sucursal_column(df):
    return "sucursal"

def format_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return date_str

@vencimientos_bp.route("/descargar/mayorista", methods=["POST"])
def descargar_mayorista():
    table_data = request.form.get("table_data")
    if not table_data:
        return "No se recibieron datos", 400
    
    try:
        df = parse_table_data(table_data)
        suc_col = get_sucursal_column(df)
        
        df_mayorista = df[df[suc_col].apply(
            lambda x: any(code.strip() in MAYORISTA_CODES for code in str(x).split(","))
        )].copy() 
        
        df_mayorista[suc_col] = df_mayorista[suc_col].apply(
            lambda x: ",".join(sorted([
                code.strip() for code in str(x).split(",")
                if code.strip() in MAYORISTA_CODES
            ]))
        )
        
        available_cols = [c for c in HEADERS if c in df_mayorista.columns]
        df_mayorista_final = df_mayorista[available_cols] if available_cols else df_mayorista
        if "descarga" in df_mayorista_final.columns:
            df_mayorista_final["descarga"] = df_mayorista_final["descarga"].apply(clean_descarga)

    except Exception as e:
        return f"Error al parsear JSON o filtrar: {e}", 500

    output = io.BytesIO()
    df_mayorista_final.to_excel(output, index=False)
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="mayorista.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@vencimientos_bp.route("/descargar/minorista", methods=["POST"])
def descargar_minorista():
    table_data = request.form.get("table_data")
    if not table_data:
        return "No se recibieron datos", 400
    
    try:
        df = parse_table_data(table_data)
        suc_col = get_sucursal_column(df)
        
        df_minorista = df[df[suc_col].apply(
            lambda x: any(code.strip() in MINORISTA_CODES for code in str(x).split(","))
        )].copy()
        
        df_minorista[suc_col] = df_minorista[suc_col].apply(
            lambda x: ",".join(sorted([
                code.strip() for code in str(x).split(",")
                if code.strip() in MINORISTA_CODES
            ]))
        )
        
        available_cols = [c for c in HEADERS if c in df_minorista.columns]
        df_minorista_final = df_minorista[available_cols] if available_cols else df_minorista
        if "descarga" in df_minorista_final.columns:
            df_minorista_final["descarga"] = df_minorista_final["descarga"].apply(clean_descarga)
        
    except Exception as e:
        return f"Error al parsear JSON o filtrar: {e}", 500

    output = io.BytesIO()
    df_minorista_final.to_excel(output, index=False)
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="minorista.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )