"""Tests for PDF attachment validation."""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.ideas.attachments import validate_pdf_upload, save_idea_attachments, MAX_PDFS_PER_IDEA
from apps.ideas.models import IdeaAttachment, IdeaRequest


def test_validate_pdf_rejects_non_pdf() -> None:
    upload = SimpleUploadedFile("doc.txt", b"text", content_type="text/plain")
    assert validate_pdf_upload(upload) is not None


def test_validate_pdf_accepts_pdf() -> None:
    upload = SimpleUploadedFile(
        "doc.pdf", b"%PDF-1.4", content_type="application/pdf"
    )
    assert validate_pdf_upload(upload) is None


@pytest.mark.django_db
def test_save_attachments_respects_limit(idea_request) -> None:
    for i in range(MAX_PDFS_PER_IDEA):
        att = IdeaAttachment(
            idea_request=idea_request,
            original_filename=f"f{i}.pdf",
            file_size=1,
            extracted_text="x",
        )
        att.file.save(f"f{i}.pdf", SimpleUploadedFile(f"f{i}.pdf", b"%PDF"), save=True)
    upload = SimpleUploadedFile("extra.pdf", b"%PDF", content_type="application/pdf")
    errors = save_idea_attachments(idea_request, [upload])
    assert any("Maximum" in e for e in errors)
