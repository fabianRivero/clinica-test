"""URL configuration for the backups domain.

Mounted by :mod:`config.api_urls` under ``admin/backups/``. View
bodies land in PR #2 commits 2 & 3 — this file wires the routes so
the authz matrix and URL resolution can be tested independently.
"""

from django.urls import path

from . import views

app_name = "backups"

urlpatterns = [
    path("trigger/", views.admin_backup_trigger, name="trigger"),
    path("", views.admin_backup_list, name="list"),
    path(
        "<str:filename>/download/",
        views.admin_backup_download,
        name="download",
    ),
    path(
        "<str:filename>/",
        views.admin_backup_delete,
        name="delete",
    ),
]