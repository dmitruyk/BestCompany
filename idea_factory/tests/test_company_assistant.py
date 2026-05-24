"""Tests for company assistant tools and runner."""
import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.agents.schemas import ChatResponse
from apps.ideas.company_assistant_config import CORE_TOOL_NAMES
from apps.ideas.company_assistant_data import (
    fetch_open_tasks,
    fetch_tasks_for_current_user,
    fetch_team_roster,
)
from apps.ideas.company_assistant_tools import (
    execute_assistant_tool,
    execute_assistant_tools,
    select_tools_for_question,
)
from apps.ideas.company_assistant_conversations import (
    build_conversation_transcript,
    create_conversation,
)
from apps.ideas.models import (
    CompanyAssistantConversation,
    CompanyAssistantMessage,
    CompanyTask,
    CompanyTeamMember,
)
from apps.ideas.company_assistant_runner import run_company_assistant_response

User = get_user_model()


def test_select_tools_always_includes_core():
    names = select_tools_for_question("Hello")
    for core in CORE_TOOL_NAMES:
        assert core in names


def test_select_tools_includes_user_tasks_for_do_i_have_tasks():
    names = select_tools_for_question("Do I have any tasks assigned to me?")
    assert "get_tasks_for_current_user" in names
    assert "get_open_tasks" in names


def test_select_tools_includes_team_for_roster_question():
    names = select_tools_for_question("Who is on the team?")
    assert "get_team_roster" in names


def test_select_tools_planning_drops_redundant_direction():
    names = select_tools_for_question("What is the weekly planning status?")
    assert "get_strategic_planning_snapshot" in names
    assert "get_strategic_direction" not in names


def test_select_tools_includes_calendar_for_schedule_question():
    names = select_tools_for_question("What is on the calendar this week?")
    assert "get_calendar" in names


@pytest.mark.django_db
def test_fetch_tasks_for_team_member(company, user):
    member_user = User.objects.create_user(username="dev1", password="pass12345!")
    member = CompanyTeamMember.objects.create(
        company=company,
        user=member_user,
        name="Dev One",
        role=CompanyTeamMember.Role.DEVELOPER,
    )
    task = CompanyTask.objects.create(
        company=company,
        title="Fix login",
        status=CompanyTask.Status.TODO,
        assigned_human=member,
        assignee_type=CompanyTask.AssigneeType.HUMAN,
        progress_percent=0,
    )
    text = fetch_tasks_for_current_user(company, member_user)
    assert "Fix login" in text
    assert str(task.pk) in text or "Fix login" in text


@pytest.mark.django_db
def test_fetch_team_roster(company, full_agent_fleet):
    CompanyTeamMember.objects.create(
        company=company,
        name="Pat",
        role=CompanyTeamMember.Role.QA,
    )
    text = fetch_team_roster(company)
    assert "Pat" in text
    assert full_agent_fleet[0].name in text


@pytest.mark.django_db
def test_fetch_open_tasks(company, full_agent_fleet):
    agent = full_agent_fleet[0]
    CompanyTask.objects.create(
        company=company,
        title="Build API",
        status=CompanyTask.Status.IN_PROGRESS,
        assigned_agent=agent,
        assignee_type=CompanyTask.AssigneeType.AGENT,
        progress_percent=10,
    )
    text = fetch_open_tasks(company)
    assert "Build API" in text


@pytest.mark.django_db
def test_execute_assistant_tool_tasks(company, user):
    text = execute_assistant_tool("get_company_overview", company, user)
    assert company.name in text


@pytest.mark.django_db
def test_execute_assistant_tools_merges_sections(company, user):
    blob = execute_assistant_tools(
        company, user, ["get_company_overview", "get_navigation_links"]
    )
    assert "### get_company_overview" in blob
    assert "### get_navigation_links" in blob


@pytest.mark.django_db
def test_execute_assistant_tools_preserves_tool_order(company, user):
    blob = execute_assistant_tools(
        company,
        user,
        ["get_company_overview", "get_navigation_links", "get_asking_user"],
    )
    assert blob.index("### get_company_overview") < blob.index("### get_navigation_links")
    assert blob.index("### get_navigation_links") < blob.index("### get_asking_user")


@pytest.mark.django_db
def test_company_assistant_page(client, user, company):
    client.force_login(user)
    url = reverse("company_assistant", kwargs={"company_pk": company.pk})
    response = client.get(url)
    assert response.status_code == 200
    assert b"Company Assistant" in response.content
    assert b"New conversation" in response.content
    assert CompanyAssistantConversation.objects.filter(company=company, user=user).exists()


@pytest.mark.django_db
def test_company_assistant_send_ajax(client, user, company):
    client.force_login(user)
    url = reverse("company_assistant_send", kwargs={"company_pk": company.pk})
    with patch(
        "apps.web.company_assistant_views._spawn_company_assistant_process"
    ) as mock_spawn:
        response = client.post(
            url,
            {"content": "Do I have any tasks?"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["ok"] is True
    assert CompanyAssistantMessage.objects.filter(company=company, user=user).count() == 1
    mock_spawn.assert_called_once()


@pytest.mark.django_db
def test_company_assistant_rejects_long_question(client, user, company):
    from apps.web.company_assistant_views import MAX_USER_QUESTION_CHARS

    client.force_login(user)
    url = reverse("company_assistant_send", kwargs={"company_pk": company.pk})
    response = client.post(
        url,
        {"content": "x" * (MAX_USER_QUESTION_CHARS + 1)},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_company_assistant_forbidden_for_other_user(client, user, company):
    intruder = User.objects.create_user(username="intruder", password="pass12345!")
    client.force_login(intruder)
    url = reverse("company_assistant", kwargs={"company_pk": company.pk})
    assert client.get(url).status_code == 404


@pytest.mark.django_db
def test_run_company_assistant_uses_server_side_tools(company, user):
    mock_out = ChatResponse(response="You have no tasks assigned.")
    with patch(
        "apps.ideas.company_assistant_runner.validate_llm_settings", return_value=None
    ), patch(
        "apps.ideas.company_assistant_runner.get_model_for_assistant", return_value="mock"
    ), patch(
        "apps.ideas.company_assistant_runner.execute_assistant_tools",
        return_value="### get_tasks_for_current_user\nNo tasks assigned.",
    ) as mock_exec, patch(
        "apps.ideas.company_assistant_runner._run_structured_output_direct", return_value=(mock_out, {})
    ) as mock_run:
        text = run_company_assistant_response(
            company, user, "Do I have any tasks?"
        )
    assert "no tasks" in text.lower()
    mock_exec.assert_called_once()
    assert mock_run.call_count == 1


@pytest.mark.django_db
def test_run_company_assistant_openai_uses_server_tools_not_agent_tools(company, user):
    mock_out = ChatResponse(response="Here is your overview.")
    with patch(
        "apps.ideas.company_assistant_runner.validate_llm_settings", return_value=None
    ), patch(
        "apps.ideas.company_assistant_runner.get_model_for_assistant", return_value="mock"
    ), patch(
        "apps.ideas.company_assistant_runner.execute_assistant_tools", return_value="data"
    ), patch(
        "apps.ideas.company_assistant_runner._run_structured_output_direct", return_value=(mock_out, {})
    ) as mock_run:
        run_company_assistant_response(company, user, "What is going on?")
    assert mock_run.call_count == 1


@pytest.mark.django_db
def test_run_company_assistant_rate_limit_message(company, user):
    with patch(
        "apps.ideas.company_assistant_runner.validate_llm_settings", return_value=None
    ), patch(
        "apps.ideas.company_assistant_runner.get_model_for_assistant", return_value="mock"
    ), patch(
        "apps.ideas.company_assistant_runner.execute_assistant_tools", return_value="data"
    ), patch(
        "apps.ideas.company_assistant_runner._run_structured_output_direct",
        side_effect=Exception("Error code: 429 - rate limit exceeded"),
    ):
        text = run_company_assistant_response(company, user, "Status?")
    assert "rate limit" in text.lower()


@pytest.mark.django_db
def test_new_conversation(client, user, company):
    conv = create_conversation(company, user, title="First")
    CompanyAssistantMessage.objects.create(
        conversation=conv,
        company=company,
        user=user,
        user_content="Hello",
        assistant_response="Hi",
    )
    client.force_login(user)
    response = client.post(
        reverse("company_assistant_new", kwargs={"company_pk": company.pk})
    )
    assert response.status_code == 302
    assert CompanyAssistantConversation.objects.filter(company=company, user=user).count() == 2


@pytest.mark.django_db
def test_delete_conversation(client, user, company):
    conv = create_conversation(company, user)
    client.force_login(user)
    response = client.post(
        reverse(
            "company_assistant_delete",
            kwargs={"company_pk": company.pk, "conversation_pk": conv.pk},
        )
    )
    assert response.status_code == 302
    assert not CompanyAssistantConversation.objects.filter(pk=conv.pk).exists()


@pytest.mark.django_db
def test_conversation_transcript_includes_prior_turns(company, user):
    conv = create_conversation(company, user)
    CompanyAssistantMessage.objects.create(
        conversation=conv,
        company=company,
        user=user,
        user_content="First question",
        assistant_response="First answer",
    )
    m2 = CompanyAssistantMessage.objects.create(
        conversation=conv,
        company=company,
        user=user,
        user_content="Follow-up",
        assistant_response="",
    )
    text = build_conversation_transcript(conv, exclude_message_id=m2.pk)
    assert "First question" in text
    assert "First answer" in text
    assert "Follow-up" not in text


@pytest.mark.django_db
def test_runner_includes_conversation_history(company, user):
    history = "--- Prior conversation in this thread ---\nUser: Hi\nAssistant: Hello\n--- End prior conversation ---"
    mock_out = ChatResponse(response="Sure.")
    with patch(
        "apps.ideas.company_assistant_runner.validate_llm_settings", return_value=None
    ), patch(
        "apps.ideas.company_assistant_runner.get_model_for_assistant", return_value="mock"
    ), patch(
        "apps.ideas.company_assistant_runner.execute_assistant_tools", return_value="data"
    ), patch(
        "apps.ideas.company_assistant_runner._run_structured_output_direct", return_value=(mock_out, {})
    ) as mock_run:
        run_company_assistant_response(
            company, user, "And then?", conversation_history=history
        )
    assert "Prior conversation" in mock_run.call_args[0][3]
