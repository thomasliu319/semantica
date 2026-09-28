"""
Semantica Knowledge Explorer : CLI Entry Point

Provides the ``semantica-explorer`` command that loads a graph from a
JSON file, starts a FastAPI server, and optionally opens the browser.

Usage::

    semantica-explorer --graph my_graph.json --port 8000
    python -m semantica.explorer --graph my_graph.json
"""

import argparse
import sys
import webbrowser

from rich.console import Console
from rich.panel import Panel

_out = Console()
_err = Console(stderr=True)


def _resolve_auto_graph(graph_path: str, stem: str) -> str | None:
    """Find a sibling graph whose filename contains ``stem`` next to ``graph_path``."""
    import os
    from pathlib import Path

    base = Path(graph_path).resolve()
    candidates = [base.parent / f"{stem}.json", base.parent / f"{stem}_cleaned_semantics.json"]
    for candidate in candidates:
        if candidate.is_file() and candidate.resolve() != base:
            return str(candidate)
    for sibling in sorted(base.parent.glob("*.json")):
        if stem in sibling.name and sibling.resolve() != base:
            return str(sibling)
    return None


def _load_versioned_sessions(graph_path: str, marketing_graph: str | None):
    """Map a primary ``--graph`` onto IoT + marketing sessions.

    Returns ``(iot_session, marketing_session, labels)``. The marketing graph is
    taken from ``--marketing-graph`` when given; otherwise it is auto-detected as
    a sibling of ``--graph``. If ``--graph`` is itself the marketing graph, the
    IoT graph is auto-detected as its sibling instead.
    """
    from pathlib import Path

    from .session import GraphSession

    primary = Path(graph_path).resolve()
    is_marketing = "marketing" in primary.name.lower()

    if marketing_graph and Path(marketing_graph).is_file():
        mkt_path = str(Path(marketing_graph).resolve())
        iot_path = str(primary) if not is_marketing else (_resolve_auto_graph(graph_path, "iot") or str(primary))
    elif is_marketing:
        mkt_path = str(primary)
        iot_path = _resolve_auto_graph(graph_path, "iot") or str(primary)
    else:
        iot_path = str(primary)
        mkt_path = _resolve_auto_graph(graph_path, "marketing") or str(primary)

    with _out.status("[dim]Loading graph…[/dim]", spinner="dots"):
        iot_session = GraphSession.from_file(iot_path)
        marketing_session = iot_session if mkt_path == iot_path else GraphSession.from_file(mkt_path)

    # 启动时一次性物化并缓存全量节点/边。之后前端无过滤分页（整图加载）
    # 直接从缓存切片，避免每页重复 normalize/哈希整张图（营销图 93k 边会极慢）。
    with _out.status("[dim]Warming graph cache…[/dim]", spinner="dots"):
        iot_session.warm_cache()
        if marketing_session is not iot_session:
            marketing_session.warm_cache()

    labels = [("v=iot2", iot_session)]
    if marketing_session is not iot_session:
        labels.append(("v=marketing", marketing_session))
    return iot_session, marketing_session, labels


def main(argv=None):
    """CLI entry point for the Knowledge Explorer server."""
    parser = argparse.ArgumentParser(
        prog="semantica-explorer",
        description="Semantica Knowledge Explorer — interactive dashboard for KG exploration",
    )
    parser.add_argument(
        "--graph", "-g",
        required=True,
        help="Path to a ContextGraph JSON file to load.",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8000,
        help="Port to bind the server to (default: 8000).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the server to (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the browser automatically.",
    )
    parser.add_argument(
        "--marketing-graph",
        help=(
            "Optional path to the marketing graph exposed under v=marketing. "
            "When omitted, a sibling marketing_cleaned_semantics.json (or the "
            "IoT counterpart) is auto-detected next to --graph."
        ),
    )
    args = parser.parse_args(argv)


    import os
    if not os.path.isfile(args.graph):
        _err.print(f"[bold red]Error:[/bold red] graph file not found: {args.graph}")
        sys.exit(1)

    try:
        import uvicorn
    except ImportError:
        _err.print(
            "[bold red]Error:[/bold red] uvicorn is required.  Install with:\n"
            "  [dim]pip install semantica[explorer][/dim]"
        )
        sys.exit(1)

    from .session import GraphSession
    from .app import create_app

    iot_session, marketing_session, session_labels = _load_versioned_sessions(
        args.graph, args.marketing_graph
    )
    for label, sess in session_labels:
        stats = sess.get_stats()
        _out.print(
            f"[bold green]✓[/bold green] {label} loaded — "
            f"[cyan]{stats.get('node_count', 0)}[/cyan] nodes, "
            f"[cyan]{stats.get('edge_count', 0)}[/cyan] edges"
        )

    app = create_app(session=iot_session, marketing_session=marketing_session)

    url = f"http://{args.host}:{args.port}"

    _LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
    if args.host not in _LOOPBACK_HOSTS:
        import os as _os
        if _os.environ.get("SEMANTICA_ALLOW_ANONYMOUS", "").strip().lower() == "true":
            _err.print(
                f"[bold yellow]Warning:[/bold yellow] Binding to "
                f"[cyan]{args.host}[/cyan] with SEMANTICA_ALLOW_ANONYMOUS=true "
                "exposes the Explorer to the network with no authentication — "
                "all graph data will be readable and writable by any host that "
                "can reach this port."
            )
        elif not _os.environ.get("SEMANTICA_API_KEY"):
            _err.print(
                f"[bold yellow]Warning:[/bold yellow] Binding to "
                f"[cyan]{args.host}[/cyan] but SEMANTICA_API_KEY is not set — "
                "protected routes will refuse all requests (503) until it is "
                "configured."
            )

    if not args.no_browser:
        import threading
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    _out.print(
        Panel(
            f"[cyan]API docs[/cyan]  {url}/docs\n[cyan]Health[/cyan]    {url}/api/health",
            title=f"[bold]Semantica Explorer[/bold] · [dim]{url}[/dim]",
            border_style="cyan",
            expand=False,
        )
    )

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
