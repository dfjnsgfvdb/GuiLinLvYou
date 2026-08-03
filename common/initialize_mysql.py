import argparse
import os
import re
from pathlib import Path
from typing import Iterable, List, Optional

import pymysql
from pymysql import MySQLError

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - deployment scripts install python-dotenv in normal use.
    load_dotenv = None


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SQL_FILE = ROOT_DIR / "docker" / "init_sql.sql"
DEFAULT_ENV_FILE = ROOT_DIR / ".env.local"


def load_local_env() -> None:
    if load_dotenv and DEFAULT_ENV_FILE.exists():
        load_dotenv(DEFAULT_ENV_FILE, override=False)


def mysql_config(database: Optional[str] = None) -> dict:
    load_local_env()
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "13006")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", "1"),
        "database": database,
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": False,
    }


def connect(database: Optional[str] = None):
    cfg = mysql_config(database)
    if not cfg["database"]:
        cfg.pop("database")
    return pymysql.connect(**cfg)


def read_sql_file(file_path: Path) -> str:
    if not file_path.is_file():
        raise FileNotFoundError(f"SQL file not found: {file_path}")
    return file_path.read_text(encoding="utf-8")


def split_sql_statements(sql_script: str) -> List[str]:
    statements: List[str] = []
    current: List[str] = []
    quote: Optional[str] = None
    escaped = False

    for char in sql_script:
        current.append(char)
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if char in {"'", '"', "`"}:
            quote = char
        elif char == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement[:-1].strip())
            current = []

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def table_name_from_create(statement: str) -> Optional[str]:
    match = re.search(r"CREATE\s+TABLE\s+`?([A-Za-z0-9_]+)`?", statement, flags=re.IGNORECASE)
    return match.group(1) if match else None


def create_table_if_missing(statement: str) -> str:
    return re.sub(r"CREATE\s+TABLE\s+", "CREATE TABLE IF NOT EXISTS ", statement, count=1, flags=re.IGNORECASE)


def execute_statements(connection, statements: Iterable[str]) -> int:
    executed = 0
    with connection.cursor() as cursor:
        for statement in statements:
            if statement.strip():
                cursor.execute(statement)
                executed += 1
    connection.commit()
    return executed


def ensure_database(database: str) -> None:
    with connect() as connection:
        execute_statements(
            connection,
            [
                f"CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci",
            ],
        )


def ensure_tables(sql_file: Path, database: str) -> int:
    sql_script = read_sql_file(sql_file)
    create_table_statements = []
    for statement in split_sql_statements(sql_script):
        table_name = table_name_from_create(statement)
        if table_name:
            create_table_statements.append(create_table_if_missing(statement))

    ensure_database(database)
    with connect(database) as connection:
        return execute_statements(connection, create_table_statements)


def seed_required_data(database: str) -> None:
    with connect(database) as connection:
        execute_statements(
            connection,
            [
                """
                INSERT IGNORE INTO t_user
                    (id, userName, password, mobile, createTime, updateTime)
                VALUES
                    (1, 'admin', '123456', NULL, '2024-01-15 15:30:00', '2024-01-15 15:30:00')
                """,
            ],
        )


def reset_database(sql_file: Path, database: str) -> int:
    sql_script = read_sql_file(sql_file)
    statements = split_sql_statements(sql_script)
    with connect() as connection:
        return execute_statements(connection, statements)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize or repair MySQL schema for sanic-web.")
    parser.add_argument("--sql-file", default=str(DEFAULT_SQL_FILE), help="Path to init_sql.sql.")
    parser.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "chat_db"), help="Database name.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate demo tables from init_sql.sql. This is destructive.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sql_file = Path(args.sql_file).resolve()
    database = args.database

    try:
        if args.reset:
            count = reset_database(sql_file, database)
            print(f"MySQL reset completed, executed {count} statements from {sql_file}.")
        else:
            count = ensure_tables(sql_file, database)
            seed_required_data(database)
            print(f"MySQL schema ensured, checked {count} CREATE TABLE statements from {sql_file}.")
        return 0
    except (MySQLError, OSError, ValueError) as exc:
        print(f"MySQL initialization failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
