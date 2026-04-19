"""Pre-deployment service health check.

Usage:
    uv run python scripts/monitoring/check_services.py

Exits 0 if all services are up, 1 otherwise.
"""
import asyncio
import sys
import time

import httpx
from rich.console import Console
from rich.table import Table

SERVICES: dict[str, str] = {
    "Backend API": "http://localhost:8000/health",
    "NLP Service": "http://localhost:8002/health",
    "CV Service": "http://localhost:8003/health",
    "RecSys Service": "http://localhost:8001/health",
}


async def check_all() -> None:
    console = Console()
    table = Table(title="MovieMatch Service Health")
    table.add_column("Service", style="bold")
    table.add_column("Status")
    table.add_column("Latency")

    all_ok = True
    async with httpx.AsyncClient(timeout=3.0) as client:
        for name, url in SERVICES.items():
            try:
                t = time.perf_counter()
                resp = await client.get(url)
                ms = int((time.perf_counter() - t) * 1000)
                if resp.status_code == 200:
                    table.add_row(name, "[green]UP ✓[/green]", f"{ms}ms")
                else:
                    table.add_row(name, f"[yellow]HTTP {resp.status_code}[/yellow]", f"{ms}ms")
                    all_ok = False
            except Exception as e:
                err = str(e)[:30]
                table.add_row(name, f"[red]DOWN ✗ ({err})[/red]", "—")
                all_ok = False

    console.print(table)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    asyncio.run(check_all())
