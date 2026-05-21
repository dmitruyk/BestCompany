"""Discussion moves to COMPLETED when all action proposals are resolved."""
import pytest

from apps.ideas.models import ActionProposal, CompanyAgent, DirectorDiscussion


@pytest.mark.django_db
def test_try_complete_selection_when_all_resolved(company, full_agent_fleet):
    director = next(a for a in full_agent_fleet if a.role == CompanyAgent.Role.DIRECTOR)
    discussion = DirectorDiscussion.objects.create(
        company=company,
        topic="Launch",
        status=DirectorDiscussion.Status.AWAITING_SELECTION,
    )
    ActionProposal.objects.create(
        discussion=discussion,
        proposed_by=director,
        action_type="Email campaign",
        description="Send intro emails",
        status=ActionProposal.ActionStatus.SELECTED,
    )
    ActionProposal.objects.create(
        discussion=discussion,
        proposed_by=director,
        action_type="Skip ads",
        description="No paid ads yet",
        status=ActionProposal.ActionStatus.REJECTED,
    )
    assert discussion.try_complete_selection() is True
    discussion.refresh_from_db()
    assert discussion.status == DirectorDiscussion.Status.COMPLETED


@pytest.mark.django_db
def test_try_complete_selection_waits_on_proposed(company, full_agent_fleet):
    director = next(a for a in full_agent_fleet if a.role == CompanyAgent.Role.DIRECTOR)
    discussion = DirectorDiscussion.objects.create(
        company=company,
        topic="Launch",
        status=DirectorDiscussion.Status.AWAITING_SELECTION,
    )
    ActionProposal.objects.create(
        discussion=discussion,
        proposed_by=director,
        action_type="Email campaign",
        description="Send intro emails",
        status=ActionProposal.ActionStatus.PROPOSED,
    )
    assert discussion.try_complete_selection() is False
    assert discussion.status == DirectorDiscussion.Status.AWAITING_SELECTION


@pytest.mark.django_db
def test_try_complete_selection_empty_discussion(company):
    discussion = DirectorDiscussion.objects.create(
        company=company,
        topic="No actions",
        status=DirectorDiscussion.Status.AWAITING_SELECTION,
    )
    assert discussion.try_complete_selection() is True
    discussion.refresh_from_db()
    assert discussion.status == DirectorDiscussion.Status.COMPLETED
