from django.test import SimpleTestCase, override_settings

from apps.core.assistant_markdown import is_safe_assistant_link_url, render_assistant_markdown


class AssistantMarkdownTests(SimpleTestCase):
    @override_settings(DJANGO_PUBLIC_HOST="manage.addmylegacy.com")
    def test_https_public_host_link_renders_clickable(self):
        text = (
            "No tasks assigned. See [open tasks]"
            "(https://manage.addmylegacy.com/companies/abc/tasks/)."
        )
        html = str(render_assistant_markdown(text))
        assert 'href="https://manage.addmylegacy.com/companies/abc/tasks/"' in html
        assert "open tasks</a>" in html
        assert "[open tasks]" not in html

    @override_settings(DJANGO_PUBLIC_HOST="manage.addmylegacy.com")
    def test_relative_path_link(self):
        html = str(render_assistant_markdown("Go to [tasks](/companies/abc/tasks/)."))
        assert 'href="/companies/abc/tasks/"' in html

    @override_settings(DJANGO_PUBLIC_HOST="manage.addmylegacy.com")
    def test_unsafe_link_left_as_text(self):
        html = str(render_assistant_markdown("[bad](javascript:alert(1))"))
        assert "javascript:" in html
        assert "<a " not in html

    @override_settings(DJANGO_PUBLIC_HOST="manage.addmylegacy.com")
    def test_bullet_list(self):
        html = str(
            render_assistant_markdown("- First item\n- Second item")
        )
        assert "<ul" in html
        assert "<li" in html
        assert "First item" in html
        assert "Second item" in html

    @override_settings(DJANGO_PUBLIC_HOST="manage.addmylegacy.com")
    def test_bold(self):
        html = str(render_assistant_markdown("You have **14 active tasks**."))
        assert "<strong" in html
        assert "14 active tasks" in html

    def test_is_safe_rejects_unknown_host(self):
        with self.settings(DJANGO_PUBLIC_HOST="manage.addmylegacy.com"):
            assert not is_safe_assistant_link_url("https://evil.example/phish")
