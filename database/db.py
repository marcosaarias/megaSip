import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "sip.s3db")

def get_db_connection():
    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn

def init_cenefas_table():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cenefas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            Codigo TEXT,
            ean TEXT,
            descripcion TEXT,
            Normal REAL,
            Oferta REAL,
            cenefa TEXT,
            desde TEXT,
            hasta TEXT,
            sucursales TEXT
        )
    """)

    conn.commit()
    conn.close()
