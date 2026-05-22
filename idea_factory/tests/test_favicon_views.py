"""Favicon is served by Django views (not /static/ collectstatic)."""
import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_favicon_ico(client):
    url = reverse("favicon_ico")
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp["Content-Type"] == "image/x-icon"
    assert len(resp.content) > 50


@pytest.mark.django_db
def test_favicon_svg(client):
    resp = client.get(reverse("favicon_svg"))
    assert resp.status_code == 200
    assert "image/svg+xml" in resp["Content-Type"]
    assert b"<svg" in resp.content


@pytest.mark.django_db
def test_static_path_favicon_ico(client):
    resp = client.get("/static/favicon.ico")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "image/x-icon"
