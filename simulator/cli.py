"""Rich & Typer CLI for Storix Real-Time State Simulator."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .engine import SimulatorEngine, hash_password, generate_totp_secret
from .file_generator import generate_all_sample_files

app = typer.Typer(help="Storix Real-Time State & Data Simulator CLI")
console = Console()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SAMPLE_FILES_DIR = BASE_DIR / "sample_files"
DEFAULT_CONSOLE_MOCK = Path(__file__).resolve().parents[2] / "console" / "src" / "mock" / "seedData.json"


@app.command()
def seed(
    seed_number: int = typer.Option(42, "--seed", "-s", help="Random seed for reproducible generation"),
    environment: str = typer.Option("prod", "--env", "-e", help="Environment prefix (prod/staging/dev)"),
    audit_count: int = typer.Option(150, "--audit-logs", "-a", help="Number of historical audit log events"),
    output_json: Optional[Path] = typer.Option(None, "--output", "-o", help="Target output JSON path"),
    generate_files: bool = typer.Option(True, "--files/--no-files", help="Generate all sample files"),
):
    """Generate baseline multi-tenant simulation state and export to Console mock."""
    console.print(Panel.fit("[bold cyan]Storix Real-Time State & Workload Simulator[/bold cyan]\n[dim]Domain-Driven Multi-Tenant SaaS Environment[/dim]"))

    if generate_files:
        with console.status("[bold green]Generating sample file library across 9 formats..."):
            file_summary = generate_all_sample_files(SAMPLE_FILES_DIR)
        console.print(f"[green]✓ Generated {sum(len(v) for v in file_summary.values())} sample files in {SAMPLE_FILES_DIR.relative_to(BASE_DIR.parent)}[/green]")

    engine = SimulatorEngine(seed=seed_number, environment=environment)
    tenants_csv = DATA_DIR / "tenants.csv"
    users_csv = DATA_DIR / "users.csv"

    with console.status("[bold green]Simulating relational tenant state & telemetry..."):
        payload = engine.build_full_simulation(
            tenants_csv_path=tenants_csv,
            users_csv_path=users_csv,
            audit_logs_count=audit_count,
        )

    target_path = output_json or DEFAULT_CONSOLE_MOCK
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(payload.model_dump_json(indent=2))

    # Display Pretty Summary Table
    table = Table(title="Simulation Summary", show_header=True, header_style="bold magenta")
    table.add_column("Tenant ID", style="cyan")
    table.add_column("Domain", style="blue")
    table.add_column("Status", style="bold")
    table.add_column("Quota", justify="right")
    table.add_column("Used", justify="right")
    table.add_column("Users", justify="right")
    table.add_column("Release", style="green")

    for t in payload.tenants:
        st_color = "green" if t.status == "ACTIVE" else ("red" if t.status == "INCIDENT" else "yellow")
        table.add_row(
            t.tenant_id,
            t.domain,
            f"[{st_color}]{t.status}[/{st_color}]",
            f"{t.quota_gb} GB",
            f"{t.storage_used_gb} GB",
            str(len(t.accounts)),
            t.release_channel,
        )

    console.print(table)
    console.print(f"\n[bold green]✓ Successfully exported simulation payload to:[/] [bold underline]{target_path}[/]")
    console.print(f"[dim]Total Tenants: {payload.total_tenants} | Total Users: {payload.total_users} | Audit Events: {payload.total_audit_logs}[/dim]\n")


@app.command()
def add_tenant(
    tenant_id: str = typer.Option(..., "--id", help="Unique Tenant Identifier (e.g. honda-vn)"),
    org_name: str = typer.Option(..., "--name", help="Company Name"),
    quota_gb: int = typer.Option(100, "--quota", help="Storage Quota in GB"),
    admin_email: Optional[str] = typer.Option(None, "--admin", help="Tenant Admin Email"),
    domain: Optional[str] = typer.Option(None, "--domain", help="Custom Domain"),
    status: str = typer.Option("ACTIVE", "--status", help="Status: ACTIVE, INCIDENT, SUSPENDED"),
    channel: str = typer.Option("STABLE", "--channel", help="Release channel: STABLE, BETA, CANARY"),
):
    """Add a new tenant dynamically to tenants.csv and update simulation state."""
    clean_id = tenant_id.strip().lower()
    dom = domain or f"{clean_id}.png261.dev"
    adm = admin_email or f"admin@{clean_id}.com"

    tenants_csv = DATA_DIR / "tenants.csv"
    users_csv = DATA_DIR / "users.csv"

    # Check for duplicate
    existing_tenants = []
    if tenants_csv.exists():
        with open(tenants_csv, "r", encoding="utf-8") as f:
            existing_tenants = list(csv.DictReader(f))

    for et in existing_tenants:
        if et.get("tenant_id") == clean_id:
            console.print(f"[bold red]Error: Tenant '{clean_id}' already exists![/bold red]")
            raise typer.Exit(code=1)

    # Append to tenants.csv
    with open(tenants_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([clean_id, org_name, dom, adm, quota_gb, status, channel])

    # Append default TenantAdmin to users.csv
    with open(users_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        admin_quota = min(100, quota_gb // 2)
        writer.writerow([clean_id, "admin", f"{org_name} Administrator", adm, "TenantAdmin", admin_quota, 1.2, "Administrators", "true"])

    console.print(f"[bold green]✓ Successfully registered tenant '{clean_id}' ({org_name}) in data registry![/bold green]")
    console.print("[dim]Re-running simulation to update console mock state...[/dim]")
    seed(seed_number=42, environment="prod", audit_count=150, output_json=DEFAULT_CONSOLE_MOCK, generate_files=False)


@app.command()
def generate_files(output_dir: Path = typer.Option(SAMPLE_FILES_DIR, "--out", "-o")):
    """Generate all sample files across 9 formats."""
    console.print(f"[cyan]Generating sample files into: {output_dir}...[/cyan]")
    res = generate_all_sample_files(output_dir)
    for cat, files in sorted(res.items()):
        console.print(f"  [green]✓ {cat}[/]: {len(files)} files")
    console.print("[bold green]All sample assets successfully generated![/]")


if __name__ == "__main__":
    app()
