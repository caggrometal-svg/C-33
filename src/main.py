"""Interactive asynchronous command-line entry point for C-33."""

from __future__ import annotations

import asyncio

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from agent.brain import Brain, CompatibleChatModel
from core.config import Settings, load_settings
from memory.store import MemoryStore
from tools.web import WebTool

console = Console()


def build_brain(settings: Settings) -> Brain:
    """Construct the C-33 runtime graph from centralized settings."""
    model = None
    if settings.model_base_url and settings.model_name:
        model = CompatibleChatModel(
            settings.model_base_url,
            settings.model_name,
            settings.model_api_key,
            timeout=settings.network_timeout_seconds,
            temperature=settings.model_temperature,
        )
    memory = MemoryStore(
        settings.memory_file,
        short_term_limit=settings.short_term_limit,
        long_term_limit=settings.long_term_limit,
    )
    web = WebTool(
        settings.network_timeout_seconds,
        max_results=settings.search_max_results,
    )
    return Brain(
        memory,
        web,
        max_steps=settings.agent_max_steps,
        model=model,
    )


def render_trace(trace: list) -> None:
    """Render observable ReAct actions without revealing hidden reasoning."""
    table = Table(title="C-33 · ciclo ReAct")
    table.add_column("Paso", justify="right")
    table.add_column("Acción")
    table.add_column("Detalle")
    for item in trace:
        table.add_row(str(item.step), item.action, item.detail or "—")
    console.print(table)


async def interactive() -> None:
    """Run the asynchronous C-33 terminal session until the user exits."""
    settings = load_settings()
    brain = build_brain(settings)
    memory_count = await brain.memory.count()
    model_status = (
        "modelo configurado" if brain.model is not None else "modo local sin modelo"
    )

    console.print(
        Panel(
            f"[bold]C-33[/bold]\n{model_status}\nMemoria persistente: {memory_count} entradas\n"
            "Escribe una pregunta. Comandos: /clear, /memory, /exit",
            title="Núcleo operativo",
        )
    )

    while True:
        prompt = await asyncio.to_thread(Prompt.ask, "[bold cyan]Tú[/bold cyan]")
        command = prompt.strip().lower()
        if command in {"/exit", "/quit"}:
            break
        if command == "/clear":
            await brain.memory.clear_history()
            console.print("[green]Memoria limpiada.[/green]")
            continue
        if command == "/memory":
            count = await brain.memory.count()
            console.print(f"Memoria persistente: {count} entradas")
            continue
        if not prompt.strip():
            continue

        try:
            result = await brain.run(prompt)
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            continue

        render_trace(result.trace)
        console.print(Panel(result.response, title="C-33"))
        if result.sources:
            console.print("[dim]Fuentes:[/dim]")
            for source in result.sources:
                console.print(f"[dim]- {source}[/dim]")


if __name__ == "__main__":
    asyncio.run(interactive())
