import os
import psycopg2
from psycopg2.extras import RealDictCursor


#def get_db_connection():
#    try:
#        return psycopg2.connect(
#            host=os.getenv("DB_HOST"),
#            port=os.getenv("DB_PORT", "5432"),
#            dbname=os.getenv("DB_NAME"),
#            user=os.getenv("DB_USER"),
#            password=os.getenv("DB_PASSWORD"),
#            cursor_factory=RealDictCursor
#        )

#    except Exception as e:
#        print(f"Error conectando a PostgreSQL: {e}")
#        raise

def get_db_connection(real_dict=True):
    try:
        params = dict(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT", "5432"),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD")
        )

        if real_dict:
            params["cursor_factory"] = RealDictCursor

        return psycopg2.connect(**params)

    except Exception as e:
        print(f"Error conectando a PostgreSQL: {e}")
        raise