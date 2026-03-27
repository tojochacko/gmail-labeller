#!/usr/bin/env python3
"""Rich CLI for testing backend logic: OAuth, email fetching, labelling, and LLM classification."""

from __future__ import annotations

import asyncio
import json
import secrets
import webbrowser
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID, uuid4

import logging

from rich import box
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from backend.app.config import get_settings
from backend.app.db.engine import make_engine, make_session_factory
from backend.app.schemas.agent import AgentRunRequest
from backend.app.schemas.labels import ApplyLabelRequest
from backend.app.services.agent_service import AgentService
from backend.app.services.batch_classifier import BatchClassifier
from backend.app.services.classification_session_service import ClassificationSessionService
from backend.app.services.db_service import DBService
from backend.app.services.email_service import EmailService
from backend.app.services.session_repository import SessionRepository
from backend.app.services.gmail_toolkit import GmailService, GmailToolkitFactory
from backend.app.services.label_service import LabelService

console = Console()

# TODO(deployment): set level=logging.WARNING to silence LLM response logs in production
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, show_path=False, markup=True)],
)
# Keep noisy libraries quiet — we only want our own service logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

SESSION_FILE = Path.home() / ".gmail-labeler" / "session.json"

# Map Gmail system label IDs to short display names; anything else is shown as-is.
_SYSTEM_LABEL_MAP = {
    "INBOX": None,
    "UNREAD": None,
    "SENT": None,
    "TRASH": None,
    "SPAM": None,
    "DRAFT": None,
    "IMPORTANT": None,
    "STARRED": "★",
    "CATEGORY_PERSONAL": "Personal",
    "CATEGORY_PROMOTIONS": "Promotions",
    "CATEGORY_SOCIAL": "Social",
    "CATEGORY_UPDATES": "Updates",
    "CATEGORY_FORUMS": "Forums",
}


def _format_gmail_label(
    labels: list[str] | None,
    custom_label_map: dict[str, str] | None = None,
) -> str:
    """Return a short display string for a list of Gmail label IDs."""
    if not labels:
        return "–"
    parts: list[str] = []
    for lbl in labels:
        if lbl in _SYSTEM_LABEL_MAP:
            mapped = _SYSTEM_LABEL_MAP[lbl]
            if mapped:
                parts.append(mapped)
        elif custom_label_map and lbl in custom_label_map:
            parts.append(custom_label_map[lbl])
        else:
            parts.append(lbl)
    return ", ".join(parts) if parts else "–"


async def _build_custom_label_map(
    gmail: GmailService, db: DBService, user_id: UUID
) -> dict[str, str]:
    """Return {label_id: label_name} for all user-defined (non-system) Gmail labels."""
    tokens = await db.fetch_gmail_tokens(user_id)
    if not tokens:
        return {}
    labels = await gmail.list_labels(tokens=tokens, user_id=str(user_id))
    return {
        lbl["id"]: lbl["name"]
        for lbl in labels
        if isinstance(lbl, dict) and "id" in lbl and "name" in lbl
        and lbl["id"] not in _SYSTEM_LABEL_MAP
    }

# ── Session ──────────────────────────────────────────────────────────────────


def load_session() -> dict | None:
    if SESSION_FILE.exists():
        return json.loads(SESSION_FILE.read_text())
    return None


def save_session(user_id: str, email: str, last_session_id: str | None = None) -> None:
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {"user_id": user_id, "email": email}
    if last_session_id:
        data["last_session_id"] = last_session_id
    elif SESSION_FILE.exists():
        existing = json.loads(SESSION_FILE.read_text())
        if "last_session_id" in existing:
            data["last_session_id"] = existing["last_session_id"]
    SESSION_FILE.write_text(json.dumps(data))


def save_last_session_id(session: dict, session_id: str) -> None:
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {**session, "last_session_id": session_id}
    SESSION_FILE.write_text(json.dumps(data))




# ── Service factory ───────────────────────────────────────────────────────────


def build_services():
    settings = get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    db = DBService(session_factory=session_factory, fernet_key=settings.fernet_secret_key.get_secret_value())
    toolkit = GmailToolkitFactory(settings).build()
    gmail = GmailService(toolkit, settings)
    email_svc = EmailService(gmail, db, settings)
    label_svc = LabelService(gmail, db)
    agent_svc = AgentService(settings, db)
    session_repo = SessionRepository(db.session_factory)
    session_svc = ClassificationSessionService(session_repo, email_svc)
    batch_classifier = BatchClassifier(session_repo, db, agent_svc, gmail)
    return settings, db, gmail, email_svc, label_svc, agent_svc, session_svc, batch_classifier


# ── Commands ──────────────────────────────────────────────────────────────────


async def cmd_connect(db: DBService, gmail: GmailService) -> dict | None:
    """Run the OAuth flow and persist the session."""
    email = Prompt.ask("[cyan]Your Google account email[/cyan]")
    user_id = str(await db.upsert_user(uuid4(), email))
    state = f"{user_id}.{secrets.token_urlsafe(16)}"
    auth_url = await gmail.create_authorization_url(state=state, user_id=user_id)

    console.print("\nOpen this URL in your browser to connect Gmail:\n")
    print(str(auth_url))
    console.print("\n[dim]Complete the OAuth flow in your browser, then press Enter.[/dim]")
    input()

    tokens = await db.fetch_gmail_tokens(UUID(user_id))
    if not tokens:
        console.print("[red]No tokens found. Did you complete the OAuth flow?[/red]")
        return None

    save_session(user_id, email)
    console.print(f"[green]✓ Connected as {email}[/green]  (user_id: {user_id})")
    return {"user_id": user_id, "email": email}


async def cmd_disconnect(db: DBService, session: dict) -> None:
    if not Confirm.ask("[yellow]Remove stored Gmail tokens?[/yellow]"):
        console.print("[dim]Cancelled.[/dim]")
        return
    await db.delete_gmail_tokens(UUID(session["user_id"]))
    SESSION_FILE.unlink(missing_ok=True)
    console.print("[green]✓ Disconnected. Session cleared.[/green]")


async def cmd_status(db: DBService, session: dict) -> None:
    tokens = await db.fetch_gmail_tokens(UUID(session["user_id"]))
    if tokens:
        console.print(
            f"[green]✓ Connected[/green]  {session['email']}  "
            f"(expires: {tokens.expires_at.strftime('%Y-%m-%d %H:%M UTC')})"
        )
    else:
        console.print("[red]✗ No Gmail connection found. Run 'Connect Gmail' first.[/red]")


async def cmd_fetch_emails(
    email_svc: EmailService, gmail: GmailService, db: DBService, session: dict
) -> list:
    max_results = int(Prompt.ask("Max emails to fetch", default="20"))
    query = Prompt.ask("Gmail query filter (leave blank for inbox)", default="in:inbox") or None
    user_id = UUID(session["user_id"])

    with console.status("[yellow]Fetching emails and labels…[/yellow]"):
        emails, custom_label_map = await asyncio.gather(
            email_svc.fetch_latest_emails(
                user_id=user_id, max_results=max_results, query=query
            ),
            _build_custom_label_map(gmail, db, user_id),
        )

    table = Table(title=f"{len(emails)} emails", box=box.ROUNDED, show_lines=False)
    table.add_column("#", style="dim", width=3)
    table.add_column("Subject", max_width=55)
    table.add_column("From", max_width=32)
    table.add_column("Label", max_width=18)
    table.add_column("Gmail ID", style="dim", max_width=18)

    for i, e in enumerate(emails, 1):
        table.add_row(
            str(i),
            e.subject or "(no subject)",
            e.sender_email or "–",
            _format_gmail_label(e.gmail_labels, custom_label_map),
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
        title = f"AI Classification — {email.subject or email.gmail_message_id}"
        console.print(Panel(table, title=title))
    else:
        console.print(f"[yellow]Run queued (id: {run.run_id}, status: {run.status})[/yellow]")


async def cmd_start_session(
    session_svc: ClassificationSessionService,
    batch_classifier: BatchClassifier,
    gmail: GmailService,
    db: DBService,
    session: dict,
) -> None:
    """Create a classification session, fetch emails, run batch classification."""
    max_results = int(
        Prompt.ask("How many emails?", choices=["10", "15", "20"], default="10")
    )
    user_id = UUID(session["user_id"])

    with console.status("[yellow]Creating session and fetching emails…[/yellow]"):
        (session_id, queued_emails), custom_label_map = await asyncio.gather(
            session_svc.create_session(user_id=user_id, max_results=max_results),
            _build_custom_label_map(gmail, db, user_id),
        )

    save_last_session_id(session, str(session_id))
    console.print(f"[green]✓ Session created:[/green] {session_id}")

    # queued_emails already has live gmail_labels from the fetch above
    table = Table(title=f"{len(queued_emails)} emails queued for classification", box=box.ROUNDED)
    table.add_column("#", style="dim", width=3)
    table.add_column("Subject", max_width=55)
    table.add_column("From", max_width=32)
    table.add_column("Label", max_width=18)
    for i, e in enumerate(queued_emails, 1):
        table.add_row(
            str(i),
            e.subject or "(no subject)",
            e.sender_email or "–",
            _format_gmail_label(e.gmail_labels, custom_label_map),
        )
    console.print(table)

    if not Confirm.ask("[cyan]Proceed with LLM classification?[/cyan]", default=True):
        console.print("[dim]Cancelled. Session saved — use option 8 to clean up.[/dim]")
        return

    with console.status("[yellow]Classifying emails (this may take a moment)…[/yellow]"):
        result = await batch_classifier.run_batch(
            session_id=session_id,
            user_id=UUID(session["user_id"]),
        )

    console.print(
        f"[green]✓ Classified {result.classified}/{result.total} emails[/green]"
        + (f"  [yellow]({result.failed} failed)[/yellow]" if result.failed else "")
    )
    review_url = f"http://localhost:8001/api/review/{session_id}"
    console.print(Panel(f"[link={review_url}]{review_url}[/link]", title="Review UI"))
    webbrowser.open(review_url)


async def cmd_open_review(session: dict) -> None:
    """Open the review UI for the last classification session."""
    last_session_id = session.get("last_session_id")
    if not last_session_id:
        console.print(
            "[yellow]No previous session found. Run 'Start classification session' first.[/yellow]"
        )
        return
    review_url = f"http://localhost:8001/api/review/{last_session_id}"
    console.print(f"[cyan]Opening:[/cyan] {review_url}")
    webbrowser.open(review_url)


async def cmd_cleanup_session(session_svc: ClassificationSessionService, session: dict) -> None:
    """Cleanup the last classification session."""
    last_session_id = session.get("last_session_id")
    if not last_session_id:
        console.print("[yellow]No previous session found.[/yellow]")
        return

    confirmed = Confirm.ask(
        f"[yellow]Delete emails and agent runs for session {last_session_id[:8]}…?[/yellow]"
    )
    if not confirmed:
        console.print("[dim]Cancelled.[/dim]")
        return

    with console.status("[yellow]Cleaning up session…[/yellow]"):
        result = await session_svc.cleanup_session(UUID(last_session_id))

    console.print(
        f"[green]✓ Cleaned up:[/green] "
        f"{result['emails_deleted']} emails, {result['runs_deleted']} agent runs deleted"
    )


# ── Main menu loop ────────────────────────────────────────────────────────────


async def main() -> None:
    console.print(Panel("[bold cyan]Gmail Labeler — Backend CLI[/bold cyan]", expand=False))

    settings, db, gmail, email_svc, label_svc, agent_svc, session_svc, batch_classifier = (
        build_services()
    )

    session = load_session()
    if session:
        console.print(f"[dim]Session loaded: {session['email']} ({session['user_id']})[/dim]")

    emails: list = []

    menu = {
        "1": "Connect Gmail (OAuth)",
        "2": "Check connection status",
        "3": "Disconnect Gmail",
        "4": "Fetch emails",
        "5": "Label an email",
        "6": "Classify email with AI",
        "7": "Start classification session (batch)",
        "8": "Open review UI",
        "9": "Cleanup last session",
        "0": "Exit",
    }

    while True:
        console.print()
        for key, label in menu.items():
            console.print(f"  [cyan]{key}[/cyan]  {label}")
        choice = Prompt.ask("\nChoice", choices=list(menu.keys()), default="7")

        if choice == "0":
            break
        elif choice == "1":
            result = await cmd_connect(db, gmail)
            if result:
                session = result
        elif choice == "2":
            if session:
                await cmd_status(db, session)
            else:
                console.print("[yellow]No session — connect first.[/yellow]")
        elif choice == "3":
            if session:
                await cmd_disconnect(db, session)
                session = None
            else:
                console.print("[yellow]No session — connect first.[/yellow]")
        elif choice == "4":
            if session:
                emails = await cmd_fetch_emails(email_svc, gmail, db, session)
            else:
                console.print("[yellow]No session — connect first.[/yellow]")
        elif choice == "5":
            if session:
                await cmd_label_email(label_svc, emails, session)
            else:
                console.print("[yellow]No session — connect first.[/yellow]")
        elif choice == "6":
            if session:
                await cmd_classify_email(agent_svc, emails, session)
            else:
                console.print("[yellow]No session — connect first.[/yellow]")
        elif choice == "7":
            if session:
                await cmd_start_session(session_svc, batch_classifier, gmail, db, session)
            else:
                console.print("[yellow]No session — connect first.[/yellow]")
        elif choice == "8":
            if session:
                await cmd_open_review(session)
            else:
                console.print("[yellow]No session — connect first.[/yellow]")
        elif choice == "9":
            if session:
                await cmd_cleanup_session(session_svc, session)
            else:
                console.print("[yellow]No session — connect first.[/yellow]")

    console.print("[dim]Bye.[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
