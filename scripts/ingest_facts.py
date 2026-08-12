"""
Load the api_facts schema + seed data (sql/setup_api_facts.sql) into PostgreSQL.
Idempotent: if api_facts already has rows, does nothing.

Run from the project root:
    python scripts/ingest_facts.py --file sql/setup_api_facts.sql
"""

import argparse

import psycopg2

# ── Configuration (must match ingest.py) ─────────────────────────────────────

DB_HOST     = "localhost"
DB_PORT     = 5432
DB_NAME     = "nexuspay_rag"
DB_USER     = "postgres"
DB_PASSWORD = "postgres"


def parse_args():
    parser = argparse.ArgumentParser(description="Carga schema + seed de api_facts")
    parser.add_argument("--file", required=True, help="Ruta al .sql con schema + seed de api_facts")
    return parser.parse_args()


def main():
    args = parse_args()

    with open(args.file, encoding="utf-8") as f:
        sql_script = f.read()

    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT,
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
    )
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("SELECT to_regclass('public.api_facts');")
    table_exists = cur.fetchone()[0] is not None

    if not table_exists:
        print(f"Creando tabla api_facts y cargando seed data desde {args.file} …")
        cur.execute(sql_script)
        conn.commit()
    else:
        cur.execute("SELECT COUNT(*) FROM api_facts;")
        count = cur.fetchone()[0]
        if count > 0:
            print(f"api_facts ya existe con {count} filas — no se vuelve a cargar.")
            cur.close()
            conn.close()
            return
        print("api_facts existe pero está vacía — insertando solo el seed data …")
        seed_marker = "-- Seed data"
        if seed_marker not in sql_script:
            raise RuntimeError(f"No se encontró el marcador '{seed_marker}' en {args.file}")
        insert_sql = sql_script[sql_script.index(seed_marker):]
        cur.execute(insert_sql)
        conn.commit()

    cur.execute("SELECT COUNT(*) FROM api_facts;")
    total = cur.fetchone()[0]
    print(f"Listo. api_facts tiene {total} filas.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
