"""Manage a project-owned Windows development cluster without touching system services."""

import argparse
import os
import secrets
import subprocess
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".local-data"
DATA = STATE / "postgres"
PORT = 55432


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "stop", "test"])
    parser.add_argument("--bin-dir", default=r"C:\Program Files\PostgreSQL\18\bin")
    args = parser.parse_args()
    binaries = Path(args.bin_dir)
    pg_ctl = str(binaries / "pg_ctl.exe")
    if args.action == "stop":
        subprocess.run([pg_ctl, "-D", str(DATA), "-m", "fast", "-w", "stop"], check=True)
        return
    STATE.mkdir(exist_ok=True)
    password_file = STATE / "postgres-password.txt"
    if not DATA.exists():
        password_file.write_text(secrets.token_hex(24), encoding="utf-8")
        subprocess.run(
            [
                str(binaries / "initdb.exe"),
                "-D",
                str(DATA),
                "-U",
                "tracerag_admin",
                "--auth=scram-sha-256",
                "--encoding=UTF8",
                "--locale=C",
                f"--pwfile={password_file}",
            ],
            check=True,
        )
    password = password_file.read_text(encoding="utf-8").strip()
    status = subprocess.run([pg_ctl, "-D", str(DATA), "status"], capture_output=True)
    if status.returncode != 0:
        subprocess.run(
            [
                pg_ctl,
                "-D",
                str(DATA),
                "-l",
                str(STATE / "postgres.log"),
                "-o",
                f"-h 127.0.0.1 -p {PORT}",
                "-w",
                "start",
            ],
            check=True,
        )
    with psycopg.connect(
        host="127.0.0.1",
        port=PORT,
        user="tracerag_admin",
        password=password,
        dbname="postgres",
        autocommit=True,
        connect_timeout=5,
    ) as connection:
        for name in ("tracerag", "tracerag_test"):
            if not connection.execute(
                "SELECT 1 FROM pg_database WHERE datname=%s", (name,)
            ).fetchone():
                connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = f"postgresql+psycopg://tracerag_admin:{password}@127.0.0.1:{PORT}/tracerag"
    if args.action == "test":
        environment = os.environ.copy()
        environment["TRACERAG_TEST_DATABASE_URL"] = url + "_test"
        import sys

        result = subprocess.run([sys.executable, "-m", "pytest"], env=environment)
        raise SystemExit(result.returncode)
    dotenv = ROOT / "backend" / ".env"
    if not dotenv.exists():
        dotenv.write_text(f"TRACERAG_DATABASE_URL={url}\n", encoding="utf-8")
        print("Created ignored backend/.env with local database configuration.")
    else:
        print("Preserved existing backend/.env; it was not modified.")
    print("Project PostgreSQL is running on 127.0.0.1:55432. Run alembic upgrade head next.")


if __name__ == "__main__":
    main()
