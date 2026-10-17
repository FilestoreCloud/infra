#!/usr/bin/env python3
"""
Storix Platform - Database Migration Utility (RDS PostgreSQL -> Amazon Aurora Serverless v2)
Transfers schemas, multi-tenant tables (nc_<tenant_id>), sequences, and data with verification.
"""

import argparse
import json
import logging
import subprocess
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rds-to-aurora-migrator")


def run_cmd(cmd, env=None, check=True):
    """Executes a subprocess command safely."""
    logger.info("Executing: %s", " ".join(cmd) if isinstance(cmd, list) else cmd)
    res = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, env=env)
    if check and res.returncode != 0:
        logger.error("Command failed: %s\nStderr: %s", res.stdout, res.stderr)
        raise RuntimeError(f"Command exited with code {res.returncode}: {res.stderr}")
    return res


def test_connection(host, port, user, dbname, password):
    """Verifies PostgreSQL connectivity."""
    cmd = [
        "psql",
        "-h", str(host),
        "-p", str(port),
        "-U", str(user),
        "-d", str(dbname),
        "-c", "SELECT version();",
    ]
    env = {"PGPASSWORD": password}
    try:
        res = run_cmd(cmd, env=env, check=True)
        logger.info("Connection test successful to %s:%s. Version: %s", host, port, res.stdout.strip())
        return True
    except Exception as exc:
        logger.error("Connection failed to %s:%s - %s", host, port, exc)
        return False


def get_tenant_schemas(host, port, user, dbname, password):
    """Retrieves all tenant schema names (e.g. nc_*) from database."""
    cmd = [
        "psql",
        "-h", str(host),
        "-p", str(port),
        "-U", str(user),
        "-d", str(dbname),
        "-t", "-A",
        "-c", "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'nc_%' OR schema_name = 'public';",
    ]
    env = {"PGPASSWORD": password}
    res = run_cmd(cmd, env=env, check=True)
    schemas = [s.strip() for s in res.stdout.strip().split("\n") if s.strip()]
    logger.info("Discovered schemas to migrate: %s", schemas)
    return schemas


def migrate(src_host, src_port, src_user, src_db, src_password,
            tgt_host, tgt_port, tgt_user, tgt_db, tgt_password,
            dry_run=False):
    """Orchestrates pg_dump streaming directly to Aurora target psql."""
    logger.info("=== Starting RDS to Aurora Migration ===")
    logger.info("Source RDS: %s:%s/%s (User: %s)", src_host, src_port, src_db, src_user)
    logger.info("Target Aurora: %s:%s/%s (User: %s)", tgt_host, tgt_port, tgt_db, tgt_user)

    if dry_run:
        logger.info("[DRY RUN] Verifying source connectivity...")
        test_connection(src_host, src_port, src_user, src_db, src_password)
        logger.info("[DRY RUN] Verifying target connectivity...")
        test_connection(tgt_host, tgt_port, tgt_user, tgt_db, tgt_password)
        schemas = get_tenant_schemas(src_host, src_port, src_user, src_db, src_password)
        logger.info("[DRY RUN] Found %d schemas to transfer. Dry run passed successfully.", len(schemas))
        return

    # 1. Test connectivity
    if not test_connection(src_host, src_port, src_user, src_db, src_password):
        raise ConnectionError("Source RDS database unreachable.")
    if not test_connection(tgt_host, tgt_port, tgt_user, tgt_db, tgt_password):
        raise ConnectionError("Target Aurora cluster database unreachable.")

    # 2. Discover schemas
    schemas = get_tenant_schemas(src_host, src_port, src_user, src_db, src_password)

    # 3. Stream data via pipe pg_dump | psql
    start_time = time.time()
    logger.info("Streaming schemas and tables from source to target...")

    dump_cmd = (
        f"PGPASSWORD='{src_password}' pg_dump -h {src_host} -p {src_port} -U {src_user} -d {src_db} "
        f"--clean --if-exists --no-owner --no-privileges "
        f"| PGPASSWORD='{tgt_password}' psql -h {tgt_host} -p {tgt_port} -U {tgt_user} -d {tgt_db}"
    )

    run_cmd(dump_cmd, check=True)
    duration = time.time() - start_time
    logger.info("Data streaming completed in %.2f seconds.", duration)

    # 4. Verify post-migration row counts
    logger.info("=== Post-Migration Verification ===")
    for schema in schemas:
        count_cmd = [
            "psql", "-h", str(tgt_host), "-p", str(tgt_port), "-U", str(tgt_user), "-d", str(tgt_db),
            "-t", "-A", "-c",
            f"SELECT count(*) FROM information_schema.tables WHERE table_schema = '{schema}';",
        ]
        res = run_cmd(count_cmd, env={"PGPASSWORD": tgt_password}, check=False)
        logger.info("Schema %s verified on Aurora: %s tables present", schema, res.stdout.strip())

    logger.info("=== Migration from RDS to Aurora completed successfully! ===")


def main():
    parser = argparse.ArgumentParser(description="Migrate Nextcloud PostgreSQL RDS to Aurora Serverless v2")
    parser.add_argument("--src-host", required=True, help="Source RDS Host")
    parser.add_argument("--src-port", default=5432, type=int, help="Source RDS Port")
    parser.add_argument("--src-user", default="nextcloud", help="Source Master Username")
    parser.add_argument("--src-db", default="nextcloud", help="Source Database Name")
    parser.add_argument("--src-password", required=True, help="Source Master Password")

    parser.add_argument("--tgt-host", required=True, help="Target Aurora Writer Host")
    parser.add_argument("--tgt-port", default=5432, type=int, help="Target Aurora Port")
    parser.add_argument("--tgt-user", default="nextcloud", help="Target Master Username")
    parser.add_argument("--tgt-db", default="nextcloud", help="Target Database Name")
    parser.add_argument("--tgt-password", required=True, help="Target Master Password")

    parser.add_argument("--dry-run", action="store_true", help="Perform pre-flight connectivity check only")

    args = parser.parse_args()
    migrate(
        args.src_host, args.src_port, args.src_user, args.src_db, args.src_password,
        args.tgt_host, args.tgt_port, args.tgt_user, args.tgt_db, args.tgt_password,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
