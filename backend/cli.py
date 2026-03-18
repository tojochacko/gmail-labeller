#!/usr/bin/env python3
"""Rich CLI for testing backend logic: OAuth, email fetching, labelling, and LLM classification."""

from __future__ import annotations

import asyncio
import json
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Event, Thread
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from backend.app.config import get_settings
from backend.app.schemas.agent import AgentRunRequest
from backend.app.schemas.labels import ApplyLabelRequest
from backend.app.services.agent_service import AgentService
from backend.app.services.email_service import EmailService
from backend.app.services.gmail_toolkit import GmailService, GmailToolkitFactory
from backend.app.services.label_service import LabelService
from backend.app.services.supabase_service import SupabaseService

console = Console()

SESSION_FILE = Path.home() / ".gmail-labeler" / "session.json"
OAUTH_CALLBACK_PORT = 3005
OAUTH_CALLBACK_PATH = "/oauth/callback"


# ── Session ──────────────────────────────────────────────────────────────────


def load_session() -> dict | None:
    if SESSION_FILE.exists():
        return json.loads(SESSION_FILE.read_text())
    return None


def save_session(user_id: str, email: str) -> None:
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps({"user_id": user_id, "email": email}))


# ── OAuth callback server ─────────────────────────────────────────────────────


def _make_callback_handler(code_event: Event, captured: dict):
    """Build an HTTPServer handler that captures OAuth callback params.

    Handles two flows:
    - Standard OAuth2: ?code=...
    - Composio-managed: ?connected_account_id=...&status=success
    """

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # silence request logs
            pass

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == OAUTH_CALLBACK_PATH:
                params = parse_qs(parsed.query)
                captured["code"] = params.get("code", [None])[0]
                captured["connected_account_id"] = params.get(
                    "connectedAccountId", [None]
                )[0]
                captured["status"] = params.get("status", [None])[0]
                captured["error"] = params.get("error", [None])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<h2>Connected! You can close this tab and return to the terminal.</h2>"
                )
                code_event.set()

    return Handler


def wait_for_oauth_callback() -> dict:
    """Start a local server, wait for the OAuth redirect, return captured params."""
    code_event = Event()
    captured: dict = {}
    handler = _make_callback_handler(code_event, captured)
    server = HTTPServer(("localhost", OAUTH_CALLBACK_PORT), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    code_event.wait(timeout=120)
    server.shutdown()
    return captured


# ── Service factory ───────────────────────────────────────────────────────────


def build_services():
    settings = get_settings()
    supabase = SupabaseService(settings)
    toolkit = GmailToolkitFactory(settings).build()
    gmail = GmailService(toolkit, settings)
    email_svc = EmailService(gmail, supabase, settings)
    label_svc = LabelService(gmail, supabase)
    agent_svc = AgentService(settings, supabase)
    return settings, supabase, gmail, email_svc, label_svc, agent_svc


# ── Commands ──────────────────────────────────────────────────────────────────


async def cmd_connect(supabase: SupabaseService, gmail: GmailService) -> dict | None:
    """Run the OAuth flow and persist the session."""
    email = Prompt.ask("[cyan]Your Google account email[/cyan]")
    user_id = str(uuid4())
    state = secrets.token_urlsafe(16)

    await supabase.upsert_user(UUID(user_id), email)
    auth_url = await gmail.create_authorization_url(state=state, user_id=user_id)

    console.print(Panel(f"[link={auth_url}]{auth_url}[/link]", title="Opening browser…"))
    webbrowser.open(str(auth_url))

    with console.status("[yellow]Waiting for OAuth callback on port 3005…[/yellow]"):
        callback = wait_for_oauth_callback()

    if not callback.get("code") and not callback.get("connected_account_id"):
        console.print("[red]OAuth timed out or was cancelled.[/red]")
        return None

    with console.status("[yellow]Storing tokens…[/yellow]"):
        if callback.get("connected_account_id"):
            # Composio-managed flow: store the connected_account_id as access token
            from datetime import timedelta
            from pydantic import SecretStr
            from backend.app.schemas.oauth import GmailTokens
            import datetime as dt

            tokens = GmailTokens(
                access_token=SecretStr(callback["connected_account_id"]),
                refresh_token=SecretStr("composio_managed"),
                expires_at=dt.datetime.now(dt.timezone.utc) + timedelta(days=365),
                scope="gmail.modify",
                token_type="Bearer",
            )
        else:
            tokens = await gmail.exchange_code_for_tokens(callback["code"])
        await supabase.store_gmail_tokens(UUID(user_id), tokens)

    save_session(user_id, email)
    console.print(f"[green]✓ Connected as {email}[/green]  (user_id: {user_id})")
    return {"user_id": user_id, "email": email}


async def cmd_status(supabase: SupabaseService, session: dict) -> None:
    tokens = await supabase.fetch_gmail_tokens(UUID(session["user_id"]))
    if tokens:
        console.print(
            f"[green]✓ Connected[/green]  {session['email']}  "
            f"(expires: {tokens.expires_at.strftime('%Y-%m-%d %H:%M UTC')})"
        )
    else:
        console.print("[red]✗ No Gmail connection found. Run 'Connect Gmail' first.[/red]")


async def cmd_fetch_emails(email_svc: EmailService, session: dict) -> list:
    max_results = int(Prompt.ask("Max emails to fetch", default="20"))
    query = Prompt.ask("Gmail query filter (leave blank for inbox)", default="in:inbox") or None

    with console.status("[yellow]Fetching emails…[/yellow]"):
        emails = await email_svc.fetch_latest_emails(
            user_id=UUID(session["user_id"]),
            max_results=max_results,
            query=query,
        )

    table = Table(title=f"{len(emails)} emails", box=box.ROUNDED, show_lines=False)
    table.add_column("#", style="dim", width=3)
    table.add_column("Subject", max_width=45)
    table.add_column("From", max_width=28)
    table.add_column("Label", width=14)
    table.add_column("Source", width=8)
    table.add_column("Confidence", width=10, justify="right")
    table.add_column("Gmail ID", style="dim", max_width=18)

    for i, e in enumerate(emails, 1):
        label_style = (
            "green" if e.label == "Important"
            else "yellow" if e.label == "Not Important"
            else "dim"
        )
        table.add_row(
            str(i),
            e.subject or "(no subject)",
            e.sender_email or "–",
            f"[{label_style}]{e.label or 'Uncategorized'}[/{label_style}]",
            e.label_source or "–",
            f"{e.label_confidence:.2f}" if e.label_confidence is not None else "–",
            e.gmail_message_id,
        )

    console.print(table)
    return emails


async def cmd_label_email(
    label_svc: LabelService, emails: list, session: dict
) -> None:
    if not emails:
        console.print("[yellow]Fetch emails first.[/yellow]")
        return

    idx = int(Prompt.ask("Email # to label")) - 1
    if not (0 <= idx < len(emails)):
        console.print("[red]Invalid selection.[/red]")
        return

    email = emails[idx]
    label_name = Prompt.ask("Label", choices=["Important", "Not Important"])

    with console.status("[yellow]Applying label…[/yellow]"):
        resp = await label_svc.apply_label(
            ApplyLabelRequest(
                user_id=UUID(session["user_id"]),
                gmail_message_id=email.gmail_message_id,
                label_name=label_name,
            )
        )

    if resp.success:
        console.print(f"[green]✓ Labelled as '{resp.label}'[/green]")
    else:
        console.print("[red]✗ Labelling failed.[/red]")


async def cmd_classify_email(
    agent_svc: AgentService, emails: list, session: dict
) -> None:
    if not emails:
        console.print("[yellow]Fetch emails first.[/yellow]")
        return

    idx = int(Prompt.ask("Email # to classify")) - 1
    if not (0 <= idx < len(emails)):
        console.print("[red]Invalid selection.[/red]")
        return

    email = emails[idx]

    with console.status("[yellow]Running LLM classification…[/yellow]"):
        run = await agent_svc.trigger_agent_run(
            AgentRunRequest(
                user_id=UUID(session["user_id"]),
                email_id=email.id,
                gmail_message_id=email.gmail_message_id,
            )
        )
        result = await agent_svc.get_agent_run(run.run_id)

    if result and result.result_payload:
        payload = result.result_payload
        table = Table(box=box.MINIMAL, show_header=False)
        table.add_row("[bold]Suggestion[/bold]", str(payload.get("suggestion", "–")))
        table.add_row("[bold]Confidence[/bold]", str(payload.get("confidence", "–")))
        table.add_row("[bold]Reasoning[/bold]", str(payload.get("reasoning", "–")))
        console.print(Panel(table, title=f"AI Classification — {email.subject or email.gmail_message_id}"))
    else:
        console.print(f"[yellow]Run queued (id: {run.run_id}, status: {run.status})[/yellow]")


# ── Main menu loop ────────────────────────────────────────────────────────────


async def main() -> None:
    console.print(Panel("[bold cyan]Gmail Labeler — Backend CLI[/bold cyan]", expand=False))

    _, supabase, gmail, email_svc, label_svc, agent_svc = build_services()

    session = load_session()
    if session:
        console.print(f"[dim]Session loaded: {session['email']} ({session['user_id']})[/dim]")

    emails: list = []

    menu = {
        "1": "Connect Gmail (OAuth)",
        "2": "Check connection status",
        "3": "Fetch emails",
        "4": "Label an email",
        "5": "Classify email with AI",
        "0": "Exit",
    }

    while True:
        console.print()
        for key, label in menu.items():
            console.print(f"  [cyan]{key}[/cyan]  {label}")
        choice = Prompt.ask("\nChoice", choices=list(menu.keys()), default="0")

        if choice == "0":
            break
        elif choice == "1":
            result = await cmd_connect(supabase, gmail)
            if result:
                session = result
        elif choice == "2":
            if session:
                await cmd_status(supabase, session)
            else:
                console.print("[yellow]No session — connect first.[/yellow]")
        elif choice == "3":
            if session:
                emails = await cmd_fetch_emails(email_svc, session)
            else:
                console.print("[yellow]No session — connect first.[/yellow]")
        elif choice == "4":
            if session:
                await cmd_label_email(label_svc, emails, session)
            else:
                console.print("[yellow]No session — connect first.[/yellow]")
        elif choice == "5":
            if session:
                await cmd_classify_email(agent_svc, emails, session)
            else:
                console.print("[yellow]No session — connect first.[/yellow]")

    console.print("[dim]Bye.[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
