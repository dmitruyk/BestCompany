from django.test import SimpleTestCase, override_settings

from apps.core.public_urls import public_absolute_url, public_site_base


class PublicUrlsTests(SimpleTestCase):
    @override_settings(DJANGO_PUBLIC_HOST="manage.addmylegacy.com")
    def test_public_site_base(self):
        self.assertEqual(public_site_base(), "https://manage.addmylegacy.com")

    @override_settings(DJANGO_PUBLIC_HOST="manage.addmylegacy.com")
    def test_public_absolute_url(self):
        self.assertEqual(
            public_absolute_url("/companies/abc/tasks/"),
            "https://manage.addmylegacy.com/companies/abc/tasks/",
        )

    @override_settings(DJANGO_PUBLIC_HOST="")
    def test_public_absolute_url_falls_back_to_path(self):
        self.assertEqual(public_absolute_url("/local/path/"), "/local/path/")
