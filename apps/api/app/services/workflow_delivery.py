"""
Workflow Delivery Service — dispatches workflow output to external destinations.

Supports: email, teams_message, calendar_event, webhook_out, outlook_reply.
Called by the `run_triggered_workflow` Celery task after workflow execution.
"""

import logging
import base64
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _render_template(template: str, context: dict) -> str:
    """Simple Mustache-style template rendering: {{key}} and {{a.b}} paths."""
    import re

    def _resolve(match: re.Match) -> str:
        path = match.group(1).strip()
        value = context
        for part in path.split("."):
            if isinstance(value, dict):
                value = value.get(part, "")
            else:
                return ""
        return str(value) if value is not None else ""

    return re.sub(r"\{\{(.+?)\}\}", _resolve, template)


class DeliveryService:
    """Dispatch workflow results to configured destinations."""

    async def dispatch(
        self,
        delivery_type: str,
        config: dict,
        output: dict,
        user_id: str,
        db: AsyncSession,
        trigger_event: dict | None = None,
    ) -> dict:
        """Route delivery to the appropriate handler."""
        context = {
            "output": output,
            "trigger_event": trigger_event or {},
        }

        handlers = {
            "email": self._send_email,
            "teams_message": self._send_teams_message,
            "calendar_event": self._create_calendar_event,
            "webhook_out": self._send_webhook,
            "outlook_reply": self._reply_outlook,
        }

        handler = handlers.get(delivery_type)
        if not handler:
            logger.warning(f"Unknown delivery type: {delivery_type}")
            return {"status": "error", "message": f"Unknown delivery type: {delivery_type}"}

        try:
            return await handler(config, output, user_id, db, context, trigger_event)
        except Exception as e:
            logger.exception(f"Delivery {delivery_type} failed: {e}")
            return {"status": "error", "delivery_type": delivery_type, "message": str(e)}

    async def _send_email(
        self,
        config: dict,
        output: dict,
        user_id: str,
        db: AsyncSession,
        context: dict,
        trigger_event: dict | None,
    ) -> dict:
        """Send email via Microsoft Graph API."""
        from app.services.graph_email import send_email

        # Resolve recipients — may contain templates like {{trigger_event.sender}}
        to_raw = config.get("to", "")
        to_list = [_render_template(addr.strip(), context) for addr in to_raw.split(",") if addr.strip()]

        subject = _render_template(config.get("subject", "Resultado do Workflow"), context)

        # Build body from output
        body_html = self._build_email_body(output, config)

        # Forward attachments from trigger event if configured
        attachments = self._resolve_attachments(config, trigger_event) or []

        # Optionally attach the workflow output as a file
        if config.get("include_output_attachment", False):
            out_att = self._build_output_attachment(output, config)
            if out_att:
                attachments.append(out_att)

        return await send_email(
            user_id=user_id,
            to=to_list,
            subject=subject,
            body_html=body_html,
            db=db,
            attachments=attachments if attachments else None,
        )

    async def _send_teams_message(
        self,
        config: dict,
        output: dict,
        user_id: str,
        db: AsyncSession,
        context: dict,
        trigger_event: dict | None,
    ) -> dict:
        """Send a proactive message via Teams Bot."""
        from app.services.teams_bot.cards import build_completion_card

        conversation_id = config.get("conversation_id") or (trigger_event or {}).get("conversation_id")
        if not conversation_id:
            logger.warning("No conversation_id for Teams delivery")
            return {"status": "skipped", "reason": "no_conversation_id"}

        # Build summary from output
        summary = self._extract_summary(output)
        workflow_name = config.get("workflow_name", "Workflow")

        card = build_completion_card(
            workflow_name=workflow_name,
            run_id=context.get("run_id", ""),
            summary=summary[:2000],
        )

        # Send via Bot Framework proactive message
        try:
            from app.services.teams_bot.proactive import send_proactive_card
            await send_proactive_card(conversation_id, card)
            return {"status": "sent", "channel": "teams", "conversation_id": conversation_id}
        except ImportError:
            logger.warning("Proactive messaging not available")
            return {"status": "skipped", "reason": "proactive_not_available"}

    async def _create_calendar_event(
        self,
        config: dict,
        output: dict,
        user_id: str,
        db: AsyncSession,
        context: dict,
        trigger_event: dict | None,
    ) -> dict:
        """Create a calendar event via Microsoft Graph API."""
        from datetime import datetime, timedelta

        from app.services.graph_calendar import create_event

        subject = _render_template(config.get("subject", "Prazo — Workflow"), context)
        body_html = self._build_email_body(output, config)

        # Parse start datetime — from config or from output.prazo
        start_str = _render_template(config.get("start", ""), context)
        duration_minutes = int(config.get("duration_minutes", 60))
        timezone = config.get("timezone", "America/Sao_Paulo")

        try:
            start = datetime.fromisoformat(start_str)
        except (ValueError, TypeError):
            # Default: tomorrow 9 AM
            now = datetime.now()
            start = now.replace(hour=9, minute=0, second=0) + timedelta(days=1)

        end = start + timedelta(minutes=duration_minutes)

        attendees_raw = config.get("attendees", "")
        attendees = [a.strip() for a in attendees_raw.split(",") if a.strip()] if attendees_raw else None

        reminder = int(config.get("reminder_minutes", 15))

        result = await create_event(
            user_id=user_id,
            subject=subject,
            body_html=body_html,
            start=start,
            end=end,
            db=db,
            attendees=attendees,
            reminder_minutes=reminder,
            timezone=timezone,
        )
        return {"status": "created", "channel": "calendar", "event_id": result.get("id", "")}

    async def _send_webhook(
        self,
        config: dict,
        output: dict,
        user_id: str,
        db: AsyncSession,
        context: dict,
        trigger_event: dict | None,
    ) -> dict:
        """POST workflow output to an external webhook URL."""
        url = config.get("url")
        if not url:
            return {"status": "error", "message": "No webhook URL configured"}

        method = config.get("method", "POST").upper()
        headers = config.get("headers", {})
        headers.setdefault("Content-Type", "application/json")

        payload = {
            "workflow_output": output,
            "trigger_event": trigger_event,
            "user_id": user_id,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "PUT":
                response = await client.put(url, json=payload, headers=headers)
            else:
                response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

        return {"status": "sent", "channel": "webhook", "status_code": response.status_code}

    async def _reply_outlook(
        self,
        config: dict,
        output: dict,
        user_id: str,
        db: AsyncSession,
        context: dict,
        trigger_event: dict | None,
    ) -> dict:
        """Reply to the original Outlook email that triggered the workflow."""
        from app.services.graph_email import reply_email

        message_id = (trigger_event or {}).get("message_id")
        if not message_id:
            return {"status": "skipped", "reason": "no_message_id_in_trigger"}

        include_original = bool(config.get("include_original_quote", config.get("include_original", True)))
        body_html = self._build_email_body(output, config)

        # Forward original attachments if configured
        attachments = self._resolve_attachments(config, trigger_event) or []

        # Optionally attach the workflow output as a file (same as email delivery)
        if config.get("include_output_attachment", False):
            out_att = self._build_output_attachment(output, config)
            if out_att:
                attachments.append(out_att)

        # If we are going through createReply (attachments present), we overwrite the draft body,
        # so we must embed the original message ourselves when requested.
        if include_original and attachments and trigger_event:
            original_html = (trigger_event or {}).get("body_html") or ""
            original_preview = (trigger_event or {}).get("body") or ""
            if original_html or original_preview:
                quoted = original_html or f"<pre>{self._escape_html(original_preview)}</pre>"
                body_html = (
                    body_html
                    + "\n<hr />\n"
                    + "<div style=\"font-size:12px;color:#666\">Mensagem original:</div>"
                    + f"<div style=\"margin-top:8px;padding:12px;border-left:3px solid #ddd\">{quoted}</div>"
                )

        return await reply_email(
            user_id=user_id,
            message_id=message_id,
            body_html=body_html,
            db=db,
            attachments=attachments if attachments else None,
            include_original_quote=include_original,
        )

    # --- Helpers ---

    def _build_email_body(self, output: dict, config: dict) -> str:
        """Build HTML email body from workflow output."""
        # If output has a 'text' or 'content' field, use it directly
        content = output.get("text") or output.get("content") or output.get("summary") or ""

        if not content and isinstance(output, dict):
            # Try to build from all string values
            parts = []
            for key, val in output.items():
                if isinstance(val, str) and val:
                    parts.append(f"<strong>{key}:</strong><br>{val}")
            content = "<br><br>".join(parts) if parts else str(output)

        html = f"""
<div style="font-family: Arial, sans-serif; max-width: 700px;">
    <h2 style="color: #1a1a2e;">Resultado do Workflow</h2>
    <hr style="border: 1px solid #e0e0e0;">
    <div style="margin-top: 16px; line-height: 1.6;">
        {content}
    </div>
    <hr style="border: 1px solid #e0e0e0; margin-top: 24px;">
    <p style="font-size: 12px; color: #888;">
        Enviado automaticamente pelo Vorbium.
    </p>
</div>
"""
        return html

    def _escape_html(self, text: str) -> str:
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def _build_output_attachment(self, output: dict, config: dict) -> dict | None:
        """
        Build a simple HTML attachment of the workflow output.

        Graph expects: { name, contentType, contentBytes(base64) }.
        """
        filename = config.get("output_attachment_name") or "workflow_output.html"
        html = self._build_email_body(output, config)
        try:
            b64 = base64.b64encode(html.encode("utf-8")).decode("ascii")
        except Exception:
            return None
        return {
            "name": filename,
            "contentType": "text/html",
            "contentBytes": b64,
        }

    def _extract_summary(self, output: dict) -> str:
        """Extract a text summary from workflow output."""
        return (
            output.get("summary")
            or output.get("text")
            or output.get("content")
            or str(output)[:500]
        )

    def _resolve_attachments(
        self, config: dict, trigger_event: dict | None
    ) -> list[dict] | None:
        """Extract attachments to forward from the trigger event.

        Returns a list of Graph-compatible attachment dicts (name, contentType,
        contentBytes) or None if forwarding is not configured / no attachments
        available.

        Config keys:
          - forward_attachments: bool — forward all trigger attachments (default False)
          - attachment_filter: list[str] — optional allowlist of file extensions (e.g. [".pdf", ".docx"])
        """
        if not config.get("forward_attachments", False):
            return None
        if not trigger_event:
            return None

        raw = trigger_event.get("attachments", [])
        if not raw:
            return None

        ext_filter = config.get("attachment_filter")  # e.g. [".pdf", ".docx"]

        trigger_message_id = trigger_event.get("message_id")
        attachments: list[dict] = []
        for att in raw:
            name = att.get("name", "")
            if ext_filter:
                if not any(name.lower().endswith(ext.lower()) for ext in ext_filter):
                    continue
            # Back-compat: if we already have base64, send it inline (small attachments).
            if att.get("contentBytes"):
                attachments.append(
                    {
                        "name": name,
                        "contentType": att.get("contentType", "application/octet-stream"),
                        "contentBytes": att.get("contentBytes", ""),
                        "size": att.get("size"),
                    }
                )
                continue

            # New path: store metadata only in trigger_event and download on-demand during delivery.
            # Requires: trigger_event.message_id + attachment id.
            att_id = att.get("id") or att.get("attachment_id")
            size = att.get("size")
            if trigger_message_id and att_id and isinstance(size, int) and size > 0:
                attachments.append(
                    {
                        "name": name or "attachment",
                        "contentType": att.get("contentType", "application/octet-stream"),
                        "size": size,
                        "source_message_id": trigger_message_id,
                        "source_attachment_id": att_id,
                    }
                )

        return attachments if attachments else None


# Singleton
delivery_service = DeliveryService()
