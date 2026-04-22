import os
import pandas as pd
from flask import Blueprint, render_template, request

farmacia_bp = Blueprint("farmacia", __name__)

@farmacia_bp.route("/", methods=["GET", "POST"])
def index():
    preview = None
    error = None

    if request.method == "POST":
        archivo = request.files.get("archivo")

        if archivo:
            try:
                df = pd.read_excel(archivo)
                df_preview = df.head(50)
                preview = df_preview.to_html(
                    classes="table table-striped table-hover table-bordered",
                    index=False
                )

            except Exception as e:
                error = f"Error procesando archivo: {e}"

    return render_template(
        "farmacia.html",
        preview=preview,
        error=error
    )