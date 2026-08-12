"""
Load the mock_transactions schema + seed data (sql/setup_mock_transactions.sql) into
PostgreSQL. Idempotent: if mock_transactions already has rows, does nothing.

Run from the project root:
    python scripts/ingest_mock_transactions.py --file sql/setup_mock_transactions.sql
"""

import argparse

import psycopg2

DB_HOST = "localhost"
DB_PORT = 5432
DB_NAME = "nexuspay_rag"
DB_USER = "postgres"
DB_PASSWORD = "postgres"


def parse_args():
    parser = argparse.ArgumentParser(description="Carga schema + seed de mock_transactions")
    parser.add_argument("--file", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    with open(args.file, encoding="utf-8") as f:
        sql_script = f.read()

    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("SELECT to_regclass('public.mock_transactions');")
    exists = cur.fetchone()[0] is not None

    if not exists:
        print(f"Creando tabla mock_transactions y cargando seed desde {args.file} …")
        cur.execute(sql_script)
        conn.commit()
    else:
        cur.execute("SELECT COUNT(*) FROM mock_transactions;")
        count = cur.fetchone()[0]
        if count > 0:
            print(f"mock_transactions ya existe con {count} filas — no se recarga.")
            cur.close()
            conn.close()
            return
        seed_marker = "-- Seed data"
        insert_sql = sql_script[sql_script.index(seed_marker):]
        cur.execute(insert_sql)
        conn.commit()

    cur.execute("SELECT COUNT(*) FROM mock_transactions;")
    print(f"Listo. mock_transactions tiene {cur.fetchone()[0]} filas.")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
