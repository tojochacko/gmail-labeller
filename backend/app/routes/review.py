"""Human review web UI and correction API for classified emails."""

from __future__ import annotations

import html
import logging
from hmac import compare_digest
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..auth import make_csrf_token
from ..config import Settings, get_settings
from ..dependencies import (
    get_classification_session_service,
    get_current_user,
    get_label_service,
)
from ..schemas.labels import ApplyLabelRequest
from ..services.classification_session_service import ClassificationSessionService
from ..services.label_service import LabelService

logger = logging.getLogger(__name__)
router = APIRouter()


class CorrectionRequest(BaseModel):
    """Request to correct an AI label."""

    email_id: UUID
    gmail_message_id: str
    new_label: str


class ApproveRequest(BaseModel):
    """Mark a single email as reviewed (no label change)."""

    email_id: UUID


@router.get("/{session_id}", response_class=HTMLResponse)
async def review_page(
    session_id: UUID,
    current_user: UUID = Depends(get_current_user),
    session_svc: ClassificationSessionService = Depends(get_classification_session_service),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Serve the self-contained HTML review UI for a session."""
    session = await session_svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["user_id"] != str(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    review_items = await session_svc.get_session_review_items(session_id)

    rows_html = ""
    for item in review_items:
        email = item["email"]
        suggestion = item["suggestion"] or "Uncategorized"
        confidence = item["confidence"]
        label_color = (
            "#22c55e"
            if suggestion == "Important"
            else "#f59e0b"
            if suggestion == "Not Important"
            else "#6b7280"
        )
        confidence_str = f"{confidence:.0%}" if confidence is not None else "–"
        subject_raw = email.subject or "(no subject)"
        subject_title = html.escape(subject_raw)
        subject_cell = html.escape(subject_raw[:60])
        sender_raw = email.sender_email or "–"
        sender_title = html.escape(sender_raw)
        sender_cell = html.escape(sender_raw[:35])
        gmail_id_safe = html.escape(email.gmail_message_id or "")
        suggestion_safe = html.escape(suggestion)
        rows_html += f"""
        <tr data-email-id="{email.id}" data-gmail-id="{gmail_id_safe}">
          <td title="{subject_title}">{subject_cell}</td>
          <td title="{sender_title}">{sender_cell}</td>
          <td class="label-cell" style="color:{label_color};font-weight:600">{suggestion_safe}</td>
          <td class="conf-cell">{confidence_str}</td>
          <td class="actions">
            <button class="btn-correct" data-new-label="Important"
              onclick="correct(this,'Important')">✓ Important</button>
            <button class="btn-correct" data-new-label="Not Important"
              onclick="correct(this,'Not Important')">✗ Not Important</button>
            <button class="btn-approve" onclick="approve(this)">👍 OK</button>
          </td>
        </tr>"""

    session_id_str = str(session_id)
    csrf_token = make_csrf_token(
        str(session_id), str(current_user), settings.jwt_secret_key.get_secret_value()
    )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Review — Session {session_id_str[:8]}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
         background:#0f172a;color:#e2e8f0;min-height:100vh;padding:2rem}}
    h1{{font-size:1.4rem;color:#7dd3fc;margin-bottom:.25rem}}
    .meta{{font-size:.8rem;color:#64748b;margin-bottom:1.5rem}}
    table{{width:100%;border-collapse:collapse;font-size:.875rem}}
    th{{text-align:left;padding:.6rem .8rem;border-bottom:2px solid #1e3a5f;
        color:#94a3b8;font-weight:600;text-transform:uppercase;font-size:.75rem}}
    td{{padding:.6rem .8rem;border-bottom:1px solid #1e293b;vertical-align:middle}}
    tr:hover td{{background:#1e293b}}
    tr.done td{{opacity:.4}}
    .actions{{display:flex;gap:.4rem;flex-wrap:wrap}}
    button{{padding:.3rem .65rem;border:none;border-radius:.35rem;cursor:pointer;
            font-size:.8rem;transition:opacity .15s}}
    button:hover{{opacity:.85}}
    .btn-correct[data-new-label="Important"]{{background:#166534;color:#bbf7d0}}
    .btn-correct[data-new-label="Not Important"]{{background:#7f1d1d;color:#fecaca}}
    .btn-approve{{background:#334155;color:#cbd5e1}}
    #toast{{position:fixed;bottom:1.5rem;right:1.5rem;background:#0ea5e9;color:#fff;
            padding:.6rem 1.2rem;border-radius:.5rem;font-size:.875rem;
            opacity:0;transition:opacity .3s;pointer-events:none}}
    #toast.show{{opacity:1}}
    .footer{{margin-top:2rem;display:flex;align-items:center;gap:1rem}}
    #btn-done{{background:#7c3aed;color:#fff;padding:.65rem 1.5rem;
               border:none;border-radius:.5rem;font-size:1rem;cursor:pointer}}
    #btn-done:hover{{background:#6d28d9}}
    #summary{{color:#64748b;font-size:.875rem}}
  </style>
</head>
<body>
  <h1>Email Review — Session <code>{session_id_str[:8]}…</code></h1>
  <p class="meta">{len(review_items)} emails · Correct any misclassifications, then click Done.</p>
  <table>
    <thead>
      <tr>
        <th>Subject</th><th>From</th><th>AI Label</th>
        <th>Confidence</th><th>Actions</th>
      </tr>
    </thead>
    <tbody id="email-tbody">
      {rows_html}
    </tbody>
  </table>
  <div class="footer">
    <button id="btn-done" onclick="doneAndCleanup()">✅ Done — Apply &amp; Cleanup</button>
    <span id="summary"></span>
  </div>
  <div id="toast"></div>

  <script>
    const SESSION_ID = "{session_id_str}";
    const CSRF_TOKEN = "{csrf_token}";
    const params = new URLSearchParams(window.location.search);
    const TOKEN = params.get('token') || '';
    if (TOKEN) {{
      window.history.replaceState({{}}, '', window.location.pathname);
    }}

    function authHeaders() {{
      const h = {{"Content-Type": "application/json"}};
      if (TOKEN) h["Authorization"] = "Bearer " + TOKEN;
      if (CSRF_TOKEN) h["X-CSRF-Token"] = CSRF_TOKEN;
      return h;
    }}

    function toast(msg, ok=true) {{
      const el = document.getElementById("toast");
      el.textContent = msg;
      el.style.background = ok ? "#0ea5e9" : "#dc2626";
      el.classList.add("show");
      setTimeout(() => el.classList.remove("show"), 2500);
    }}

    function getRowData(btn) {{
      const tr = btn.closest("tr");
      return {{
        tr,
        emailId: tr.dataset.emailId,
        gmailId: tr.dataset.gmailId,
        labelCell: tr.querySelector(".label-cell"),
      }};
    }}

    async function correct(btn, newLabel) {{
      const {{tr, emailId, gmailId, labelCell}} = getRowData(btn);
      btn.disabled = true;
      try {{
        const resp = await fetch(`/api/review/${{SESSION_ID}}/correct`, {{
          method: "POST",
          headers: authHeaders(),
          body: JSON.stringify({{
            email_id: emailId,
            gmail_message_id: gmailId,
            new_label: newLabel,
          }}),
        }});
        if (!resp.ok) throw new Error(await resp.text());
        labelCell.textContent = newLabel;
        labelCell.style.color = newLabel === "Important" ? "#22c55e" : "#f59e0b";
        tr.classList.add("done");
        toast(`Corrected to ${{newLabel}}`);
      }} catch(e) {{
        toast("Error: " + e.message, false);
        btn.disabled = false;
      }}
    }}

    function approve(btn) {{
      const {{tr}} = getRowData(btn);
      tr.classList.add("done");
      toast("Approved");
    }}

    async function doneAndCleanup() {{
      const doneBtn = document.getElementById("btn-done");
      doneBtn.disabled = true;
      doneBtn.textContent = "Cleaning up…";
      try {{
        const resp = await fetch(`/api/sessions/${{SESSION_ID}}/cleanup`, {{
          method: "POST",
          headers: authHeaders(),
        }});
        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();
        document.getElementById("summary").textContent =
          `Done! ${{data.emails_deleted}} emails and ${{data.runs_deleted}} runs removed.`;
        doneBtn.textContent = "✅ Complete";
        toast("Session cleaned up successfully");
      }} catch(e) {{
        toast("Cleanup error: " + e.message, false);
        doneBtn.disabled = false;
        doneBtn.textContent = "✅ Done — Apply & Cleanup";
      }}
    }}
  </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)


@router.post("/{session_id}/correct")
async def correct_label(
    session_id: UUID,
    request: CorrectionRequest,
    x_csrf_token: str | None = Header(default=None),
    current_user: UUID = Depends(get_current_user),
    session_svc: ClassificationSessionService = Depends(get_classification_session_service),
    label_svc: LabelService = Depends(get_label_service),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Apply a human correction to an email's label (triggers pattern learning)."""
    if request.new_label not in ("Important", "Not Important"):
        raise HTTPException(
            status_code=422, detail="new_label must be 'Important' or 'Not Important'"
        )

    session = await session_svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["user_id"] != str(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    expected_csrf = make_csrf_token(
        str(session_id), str(current_user), settings.jwt_secret_key.get_secret_value()
    )
    if not compare_digest(x_csrf_token or "", expected_csrf):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token invalid.")

    user_id = UUID(session["user_id"])

    try:
        await label_svc.apply_label(
            ApplyLabelRequest(
                user_id=user_id,
                gmail_message_id=request.gmail_message_id,
                label_name=request.new_label,
            )
        )
        return {"success": True, "label": request.new_label}
    except Exception as e:
        logger.error("Correction failed for email %s: %s", request.email_id, e)
        raise HTTPException(status_code=500, detail="An internal error occurred.")
