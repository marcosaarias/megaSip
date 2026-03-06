import os
from flask import Blueprint, render_template

DB_PATH = os.path.join(os.path.dirname(__file__), "sip.s3db")

farmacia_bp = Blueprint("farmacia", __name__)

@farmacia_bp.route("/")
def index():
    return render_template("farmacia.html")