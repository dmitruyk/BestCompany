"""URL configuration for web app."""
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("ideas/new/", views.new_idea, name="new_idea"),
    path("ideas/<uuid:pk>/", views.idea_detail, name="idea_detail"),
    path("ideas/<uuid:pk>/status/", views.idea_status, name="idea_status"),
    path("ideas/<uuid:pk>/accept/", views.accept_idea, name="accept_idea"),
    path("ideas/<uuid:pk>/stop/", views.stop_pipeline, name="stop_pipeline"),
    path("ideas/<uuid:pk>/rerun/", views.rerun_failed_steps, name="rerun_failed"),
    path("ideas/<uuid:pk>/rerun-from-scratch/", views.rerun_from_scratch, name="rerun_from_scratch"),
    path("ideas/<uuid:pk>/delete/", views.delete_idea_confirm, name="delete_idea_confirm"),
    path("ideas/<uuid:pk>/delete/confirm/", views.delete_idea, name="delete_idea"),
    path("ideas/<uuid:pk>/save-conclusion/", views.save_conclusion, name="save_conclusion"),
    path("ideas/<uuid:pk>/download/", views.download_json, name="download_json"),
    path("companies/", views.company_list, name="company_list"),
    path("companies/<uuid:pk>/", views.company_detail, name="company_detail"),
    path("companies/<uuid:company_pk>/agents/<uuid:agent_pk>/chat/", views.company_agent_chat, name="company_agent_chat"),
    path("companies/<uuid:company_pk>/agents/<uuid:agent_pk>/chat/send/", views.agent_chat_send, name="agent_chat_send"),
    path("companies/<uuid:company_pk>/discussions/new/", views.start_discussion, name="start_discussion"),
    path("companies/<uuid:company_pk>/discussions/<uuid:discussion_pk>/", views.director_discussion_detail, name="director_discussion_detail"),
    path("companies/<uuid:company_pk>/discussions/<uuid:discussion_pk>/rerun/", views.rerun_discussion, name="rerun_discussion"),
    path("companies/<uuid:company_pk>/discussions/<uuid:discussion_pk>/status/", views.discussion_status, name="discussion_status"),
    path("companies/<uuid:company_pk>/actions/<uuid:action_pk>/select/", views.action_select, name="action_select"),
    path("companies/<uuid:company_pk>/actions/<uuid:action_pk>/schedule/", views.action_schedule, name="action_schedule"),
    path("companies/<uuid:company_pk>/actions/<uuid:action_pk>/reject/", views.action_reject, name="action_reject"),
    path("companies/<uuid:company_pk>/calendar/", views.company_calendar, name="company_calendar"),
    path("companies/<uuid:company_pk>/calendar/add/", views.calendar_action_add, name="calendar_action_add"),
    path("companies/<uuid:company_pk>/calendar/<int:year>/<int:month>/<int:day>/", views.company_calendar_date, name="company_calendar_date"),
    path("companies/<uuid:company_pk>/calendar/entry/<uuid:entry_pk>/status/", views.calendar_action_update_status, name="calendar_action_update_status"),
]
