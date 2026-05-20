"""Save and validate PDF attachments on idea requests."""
from __future__ import annotations

import os
import uuid

from django.core.files.uploadedfile import UploadedFile

from apps.ideas.models import IdeaAttachment, IdeaRequest
from apps.ideas.pdf_utils import extract_text_from_pdf

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PDFS_PER_IDEA = 5
ALLOWED_CONTENT_TYPES = frozenset({"application/pdf", "application/x-pdf"})


def validate_pdf_upload(upload: UploadedFile) -> str | None:
    """Return error message if invalid, else None."""
    name = (upload.name or "").lower()
    if not name.endswith(".pdf"):
        return f"{upload.name}: only PDF files are allowed."
    if upload.size and upload.size > MAX_PDF_BYTES:
        return f"{upload.name}: file exceeds 10 MB limit."
    content_type = (upload.content_type or "").lower()
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        return f"{upload.name}: invalid content type."
    return None


def save_idea_attachments(
    idea_request: IdeaRequest,
    uploads: list[UploadedFile],
) -> list[str]:
    """Save PDF uploads for an idea. Returns error messages (empty if ok)."""
    errors: list[str] = []
    existing = idea_request.attachments.count()
    slots = max(0, MAX_PDFS_PER_IDEA - existing)
    if slots == 0:
        return [f"Maximum {MAX_PDFS_PER_IDEA} PDF attachments per idea."]

    for upload in uploads[:slots]:
        if not upload:
            continue
        err = validate_pdf_upload(upload)
        if err:
            errors.append(err)
            continue

        original = os.path.basename(upload.name or "document.pdf")
        ext = os.path.splitext(original)[1].lower() or ".pdf"
        stored_name = f"{uuid.uuid4()}{ext}"

        attachment = IdeaAttachment(
            idea_request=idea_request,
            original_filename=original[:255],
            file_size=upload.size or 0,
        )
        attachment.file.save(stored_name, upload, save=False)
        attachment.extracted_text = extract_text_from_pdf(attachment.file.path)
        attachment.save()

    if len(uploads) > slots:
        errors.append(f"Only {slots} more PDF(s) allowed (max {MAX_PDFS_PER_IDEA} total).")

    return errors
