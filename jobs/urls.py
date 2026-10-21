from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("upload/", views.resume_upload_view, name="resume_upload"),
    path("applications/<int:pk>/", views.application_detail_view, name="application_detail"),
    path("applications/<int:pk>/status/", views.update_application_status_view, name="update_status"),
    path("applications/<int:pk>/approve/", views.approve_and_apply_view, name="approve_application"),
    path("fetch-jobs/", views.fetch_jobs_view, name="fetch_jobs"),
    path("run-bot/", views.trigger_pipeline_view, name="trigger_bot"),
]