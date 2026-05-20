"""Tests for idea context building."""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.ideas.context import build_idea_request_prompt, build_attachment_context_section
from apps.ideas.models import IdeaAttachment


@pytest.mark.django_db
def test_build_prompt_without_attachments(idea_request) -> None:
    text = build_idea_request_prompt(idea_request)
    assert idea_request.title in text
    assert idea_request.prompt in text
    assert "Attached documents" not in text


@pytest.mark.django_db
def test_build_prompt_with_attachment_text(idea_request) -> None:
    att = IdeaAttachment(
        idea_request=idea_request,
        original_filename="spec.pdf",
        extracted_text="Market size is $1B",
        file_size=100,
    )
    att.file.save("spec.pdf", SimpleUploadedFile("spec.pdf", b"%PDF-1.4"), save=True)
    section = build_attachment_context_section(idea_request)
    assert "spec.pdf" in section
    assert "Market size" in section
    prompt = build_idea_request_prompt(idea_request)
    assert "Market size" in prompt
