"""
Microsoft Graph API — Email operations.

Send and reply to emails using the user's Graph OBO token.
"""

import logging
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.graph_client import GraphClient

logger = logging.getLogger(__name__)

INLINE_ATTACHMENT_MAX_BYTES = 3 * 1024 * 1024  # 3MB (Graph limit for "simple" fileAttachment payloads)
UPLOAD_CHUNK_BYTES = 5 * 1024 * 1024  # 5MB chunks for upload sessions


def _needs_upload_session(att: dict) -> bool:
    """
    Decide whether an attachment must be sent via upload session.

    Cases:
      - No contentBytes present (Graph didn't inline it; large attachment or non-file type).
      - Caller provided a source reference (download-on-demand).
      - Size hint is > inline threshold.
    """
    if att.get("source_attachment_id") and att.get("source_message_id"):
        return True
    if not att.get("contentBytes"):
        # If we don't have bytes inline, we can still try adding as fileAttachment if size is unknown,
        # but in practice this means we must fetch and upload.
        return True
    size = att.get("size")
    if isinstance(size, int) and size > INLINE_ATTACHMENT_MAX_BYTES:
        return True
    return False


async def _create_draft_message(
    client: GraphClient,
    to: list[str],
    subject: str,
    body_html: str,
    cc: list[str] | None = None,
) -> str:
    """Create a draft message in the user's mailbox and return its message id."""
    to_recipients = [{"emailAddress": {"address": addr}} for addr in to]
    cc_recipients = [{"emailAddress": {"address": addr}} for addr in (cc or [])]
    message: dict = {
        "subject": subject,
        "body": {"contentType": "HTML", "content": body_html},
        "toRecipients": to_recipients,
    }
    if cc_recipients:
        message["ccRecipients"] = cc_recipients

    draft = await client.post("/me/messages", json_data=message)
    draft_id = draft.get("id")
    if not draft_id:
        raise RuntimeError("Failed to create draft message (no id returned)")
    return draft_id


async def _send_draft_message(client: GraphClient, draft_id: str) -> None:
    """Send an existing draft message."""
    url = f"{client.base_url}/me/messages/{draft_id}/send"
    response = await client.client.post(url)
    if response.status_code == 429:
        retry_after = int(response.headers.get("Retry-After", 5))
        import asyncio
        await asyncio.sleep(retry_after)
        response = await client.client.post(url)
    response.raise_for_status()


async def _add_small_attachment_to_draft(client: GraphClient, draft_id: str, att: dict) -> None:
    """Add an inline (<=3MB) fileAttachment to a draft message."""
    content_bytes = att.get("contentBytes") or ""
    if not content_bytes:
        return
    await client.post(
        f"/me/messages/{draft_id}/attachments",
        json_data={
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": att.get("name", "attachment"),
            "contentType": att.get("contentType", "application/octet-stream"),
            "contentBytes": content_bytes,
        },
    )


async def _create_attachment_upload_session(
    client: GraphClient,
    draft_id: str,
    name: str,
    size: int,
    content_type: str,
) -> str:
    """
    Create an upload session for an attachment on a draft message.

    Graph endpoint: POST /me/messages/{id}/attachments/createUploadSession
    """
    resp = await client.post(
        f"/me/messages/{draft_id}/attachments/createUploadSession",
        json_data={
            "AttachmentItem": {
                "@odata.type": "microsoft.graph.attachmentItem",
                "attachmentType": "file",
                "name": name,
                "size": size,
                "contentType": content_type,
            }
        },
    )
    upload_url = resp.get("uploadUrl")
    if not upload_url:
        raise RuntimeError("createUploadSession did not return uploadUrl")
    return upload_url


def _iter_source_attachment_bytes(
    client: GraphClient,
    source_message_id: str,
    source_attachment_id: str,
):
    """
    Async iterator of bytes for a message attachment, ensuring the response is closed.

    Uses: GET /me/messages/{message_id}/attachments/{attachment_id}/$value
    """
    url = f"{client.base_url}/me/messages/{source_message_id}/attachments/{source_attachment_id}/$value"

    async def _gen():
        async with client.client.stream("GET", url, headers={"Accept": "application/octet-stream"}) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                yield chunk

    return _gen()


async def _upload_stream_to_upload_url(
    upload_url: str,
    byte_iter,
    total_size: int,
    chunk_bytes: int = UPLOAD_CHUNK_BYTES,
) -> None:
    """
    Upload bytes to an uploadUrl using chunked PUT with Content-Range.

    The uploadUrl is pre-authorized; do not send Authorization header.
    """
    async with httpx.AsyncClient(timeout=120.0) as up:
        sent = 0
        buf = b""

        async for piece in byte_iter:
            if not piece:
                continue
            buf += piece
            while len(buf) >= chunk_bytes:
                chunk = buf[:chunk_bytes]
                buf = buf[chunk_bytes:]
                start = sent
                end = sent + len(chunk) - 1
                headers = {
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {start}-{end}/{total_size}",
                }
                r = await up.put(upload_url, content=chunk, headers=headers)
                r.raise_for_status()
                sent += len(chunk)

        # final chunk
        if buf:
            chunk = buf
            start = sent
            end = sent + len(chunk) - 1
            headers = {
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end}/{total_size}",
            }
            r = await up.put(upload_url, content=chunk, headers=headers)
            r.raise_for_status()
            sent += len(chunk)

        if sent != total_size:
            # Graph may accept fewer bytes only if total_size was wrong; treat as error.
            raise RuntimeError(f"Attachment upload incomplete: sent={sent} expected={total_size}")


async def _get_graph_token(user_id: str, db: AsyncSession) -> Optional[str]:
    """Resolve user_id → microsoft_oid → Redis graph_token."""
    from app.core.redis import redis_client
    from app.models.microsoft_user import MicrosoftUser

    if not redis_client:
        logger.warning("Redis not available for graph token lookup")
        return None

    stmt = select(MicrosoftUser).where(MicrosoftUser.user_id == user_id)
    result = await db.execute(stmt)
    ms_user = result.scalar_one_or_none()
    if not ms_user:
        logger.warning(f"No Microsoft account linked for user {user_id}")
        return None

    token = await redis_client.get(f"graph_token:{ms_user.microsoft_oid}")
    if not token:
        logger.warning(f"Graph token expired for oid={ms_user.microsoft_oid}")
    return token


async def send_email(
    user_id: str,
    to: list[str],
    subject: str,
    body_html: str,
    db: AsyncSession,
    cc: list[str] | None = None,
    attachments: list[dict] | None = None,
    save_to_sent: bool = True,
) -> dict:
    """Send email via Microsoft Graph API using the user's OBO token.

    *attachments*: list of dicts with keys:
      - Small inline: ``name``, ``contentType``, ``contentBytes`` (base64), optional ``size``
      - Large/source: ``name``, ``contentType``, ``size`` and ``source_message_id`` + ``source_attachment_id``
    Returns the Graph API response dict on success.
    Raises RuntimeError if token not available.
    """
    token = await _get_graph_token(user_id, db)
    if not token:
        raise RuntimeError(f"Graph token unavailable for user {user_id}")

    to_recipients = [
        {"emailAddress": {"address": addr}} for addr in to
    ]
    cc_recipients = [
        {"emailAddress": {"address": addr}} for addr in (cc or [])
    ]

    message: dict = {
        "subject": subject,
        "body": {
            "contentType": "HTML",
            "content": body_html,
        },
        "toRecipients": to_recipients,
    }
    if cc_recipients:
        message["ccRecipients"] = cc_recipients

    async with GraphClient(token) as client:
        atts = attachments or []
        if atts and any(_needs_upload_session(a) for a in atts):
            # Create draft → attach (small + upload sessions) → send
            draft_id = await _create_draft_message(client, to, subject, body_html, cc=cc)

            for att in atts:
                if not _needs_upload_session(att):
                    await _add_small_attachment_to_draft(client, draft_id, att)
                    continue

                # Source attachment: download and upload
                src_mid = att.get("source_message_id")
                src_aid = att.get("source_attachment_id")
                name = att.get("name", "attachment")
                ctype = att.get("contentType", "application/octet-stream")
                size = att.get("size")
                if not (src_mid and src_aid):
                    raise RuntimeError(f"Large attachment missing source reference: {name}")
                if not isinstance(size, int) or size <= 0:
                    # We require size for Content-Range. Fetching it via metadata should have provided it.
                    raise RuntimeError(f"Large attachment missing size: {name}")

                upload_url = await _create_attachment_upload_session(client, draft_id, name=name, size=size, content_type=ctype)
                # Stream from the original message attachment into the upload session
                byte_iter = _iter_source_attachment_bytes(client, src_mid, src_aid)
                await _upload_stream_to_upload_url(upload_url, byte_iter, total_size=size)

            await _send_draft_message(client, draft_id)
        else:
            # Simple sendMail with small inline attachments only
            if atts:
                message["attachments"] = [
                    {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": att.get("name", "attachment"),
                        "contentType": att.get("contentType", "application/octet-stream"),
                        "contentBytes": att.get("contentBytes", ""),
                    }
                    for att in atts
                    if att.get("contentBytes")
                ]

            payload = {"message": message, "saveToSentItems": save_to_sent}
            # sendMail returns 202 Accepted (no body) — GraphClient.post expects JSON,
            # so we use the underlying httpx client directly.
            url = f"{client.base_url}/me/sendMail"
            response = await client.client.post(url, json=payload)
            if response.status_code == 429:
                import asyncio
                retry_after = int(response.headers.get("Retry-After", 5))
                await asyncio.sleep(retry_after)
                response = await client.client.post(url, json=payload)
            response.raise_for_status()

    att_count = len(attachments) if attachments else 0
    logger.info(f"Email sent to {to} (subject={subject[:60]}, attachments={att_count})")
    return {"status": "sent", "to": to, "subject": subject, "attachments": att_count}


async def reply_email(
    user_id: str,
    message_id: str,
    body_html: str,
    db: AsyncSession,
    attachments: list[dict] | None = None,
    include_original_quote: bool = True,
) -> dict:
    """Reply to an email via Microsoft Graph API.

    message_id: The Graph message ID of the email to reply to.
    *attachments*: optional list of dicts (see send_email).

    When attachments are present, uses the createReply → add attachments → send
    pattern (the simple /reply endpoint does not support attachments).
    """
    token = await _get_graph_token(user_id, db)
    if not token:
        raise RuntimeError(f"Graph token unavailable for user {user_id}")

    async with GraphClient(token) as client:
        if not attachments and include_original_quote:
            # Simple reply (no attachments) — one-shot POST
            # Graph will include the original message quote automatically.
            url = f"{client.base_url}/me/messages/{message_id}/reply"
            payload = {"comment": body_html}
            response = await client.client.post(url, json=payload)
            if response.status_code == 429:
                import asyncio
                retry_after = int(response.headers.get("Retry-After", 5))
                await asyncio.sleep(retry_after)
                response = await client.client.post(url, json=payload)
            response.raise_for_status()
        else:
            # createReply → draft → add attachments → update body → send
            # 1. Create reply draft
            draft = await client.post(
                f"/me/messages/{message_id}/createReply",
                json_data={"comment": ""},
            )
            draft_id = draft.get("id")
            if not draft_id:
                raise RuntimeError("createReply did not return a draft id")

            # 2. Update draft body
            await client.patch(
                f"/me/messages/{draft_id}",
                json_data={
                    "body": {
                        "contentType": "HTML",
                        "content": body_html,
                    },
                },
            )

            # 3. Add attachments to the draft (small inline or upload session)
            for att in (attachments or []):
                if not _needs_upload_session(att):
                    await _add_small_attachment_to_draft(client, draft_id, att)
                    continue

                src_mid = att.get("source_message_id")
                src_aid = att.get("source_attachment_id")
                name = att.get("name", "attachment")
                ctype = att.get("contentType", "application/octet-stream")
                size = att.get("size")
                if not (src_mid and src_aid):
                    raise RuntimeError(f"Large attachment missing source reference: {name}")
                if not isinstance(size, int) or size <= 0:
                    raise RuntimeError(f"Large attachment missing size: {name}")

                upload_url = await _create_attachment_upload_session(client, draft_id, name=name, size=size, content_type=ctype)
                byte_iter = _iter_source_attachment_bytes(client, src_mid, src_aid)
                await _upload_stream_to_upload_url(upload_url, byte_iter, total_size=size)

            # 4. Send the draft
            await _send_draft_message(client, draft_id)

    att_count = len(attachments) if attachments else 0
    logger.info(f"Reply sent to message {message_id} (attachments={att_count})")
    return {"status": "replied", "message_id": message_id, "attachments": att_count}


async def get_email_details(
    user_id: str,
    message_id: str,
    db: AsyncSession,
) -> dict | None:
    """Fetch full email details from Graph API."""
    token = await _get_graph_token(user_id, db)
    if not token:
        return None

    async with GraphClient(token) as client:
        try:
            return await client.get(
                f"/me/messages/{message_id}",
                params={"$select": "id,subject,bodyPreview,body,from,toRecipients,ccRecipients,receivedDateTime,hasAttachments,internetMessageId"},
            )
        except Exception as e:
            logger.error(f"Failed to fetch email {message_id}: {e}")
            return None


async def get_attachments(
    user_id: str,
    message_id: str,
    db: AsyncSession,
    include_content_bytes_up_to_mb: float = 0.0,
) -> list[dict]:
    """Fetch attachments for an email via Graph API.

    Returns a list of dicts with keys: id, name, contentType, size, isInline, contentBytes (optional).
    By default we do NOT embed base64 bytes in the event payload (to avoid large Celery/DB blobs).
    If include_content_bytes_up_to_mb > 0, will include contentBytes only when Graph returns it
    and the attachment is <= that threshold.
    """
    token = await _get_graph_token(user_id, db)
    if not token:
        return []

    include_bytes_max = int(include_content_bytes_up_to_mb * 1024 * 1024)

    async with GraphClient(token) as client:
        try:
            data = await client.get(
                f"/me/messages/{message_id}/attachments",
                params={"$select": "id,name,contentType,size,isInline,contentBytes"},
            )
        except Exception as e:
            logger.error(f"Failed to fetch attachments for {message_id}: {e}")
            return []

    attachments: list[dict] = []
    for att in data.get("value", []):
        # Skip inline images (CID references) and oversized files
        if att.get("isInline", False):
            continue

        size = att.get("size", 0) or 0
        out = {
            "id": att.get("id", ""),
            "name": att.get("name", "attachment"),
            "contentType": att.get("contentType", "application/octet-stream"),
            "size": int(size) if isinstance(size, (int, float)) else 0,
            "isInline": False,
        }
        if include_bytes_max > 0 and out["size"] > 0 and out["size"] <= include_bytes_max:
            # Graph only provides contentBytes for smaller attachments; if present we include it.
            if att.get("contentBytes"):
                out["contentBytes"] = att.get("contentBytes", "")

        attachments.append(out)

    logger.info(f"Fetched {len(attachments)} attachments for message {message_id}")
    return attachments
