"""URL configuration for idea_factory project."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.web import favicon_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("favicon.ico", favicon_views.favicon_ico, name="favicon_ico"),
    path("favicon.svg", favicon_views.favicon_svg, name="favicon_svg"),
    path(
        "apple-touch-icon.png",
        favicon_views.apple_touch_icon,
        name="apple_touch_icon",
    ),
    # Browsers / cached HTML may still request these paths:
    path("static/favicon.ico", favicon_views.favicon_ico),
    path("static/favicon.svg", favicon_views.favicon_svg),
    path("static/apple-touch-icon.png", favicon_views.apple_touch_icon),
    path("", include("apps.web.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
