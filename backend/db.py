from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row
from .config import database_config

@contextmanager
def transaction():
    # A request owns one connection/transaction: exceptions roll back every step.
    with psycopg.connect(**database_config(), row_factory=dict_row) as conn:
        conn.execute('SET LOCAL search_path TO pawcare, public')
        conn.execute("SET LOCAL TIME ZONE 'Australia/Sydney'")
        conn.execute("SET LOCAL lock_timeout = '8s'")
        yield conn

def one(conn, query, params=()):
    return conn.execute(query, params).fetchone()

def all_rows(conn, query, params=()):
    return conn.execute(query, params).fetchall()

def schedule_lock(conn):
    conn.execute('SELECT pg_advisory_xact_lock(9120, 1)')
