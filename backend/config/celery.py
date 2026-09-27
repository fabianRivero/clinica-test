"""Celery application instance.

Phase 2 of dp4500-host-app-integration-phase2. The Celery app is
configured to discover tasks from the \`dp4500_integration\` Django
app. Test settings set \`CELERY_TASK_ALWAYS_EAGER=True\` so tests
run synchronously without a worker; production sets it to False.

The celery app is wired into \`manage.py\` (imported at module load) so
\`manage.py shell\` and \`manage.py runserver\` are aware of the
\`-A config\` worker entry point.
"""
from __future__ import annotations

import os

from celery import Celery


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("proyecto_c")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
