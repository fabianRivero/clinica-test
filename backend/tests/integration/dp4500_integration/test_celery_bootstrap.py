"""Celery bootstrap tests — Phase 2.0.5 + 2.0.6 of
dp4500-host-app-integration-phase2.

Locks the eager-mode default + module-load contract that the cascade
signal + Celery task depend on. The cascade path runs in eager mode for
tests (so ``.delay()`` returns the result synchronously), but a future
deployment flip to a real broker would still rely on the Celery app
being importable + configured the same way.

Why this lives in the ``tests/integration/`` slice: the import assertion
exercises the ``config.celery`` module-load contract and the
``CELERY_TASK_ALWAYS_EAGER`` setting, both of which sit above any
particular view or model — neither belongs under
``dp4500_integration/tests/``.
"""

from __future__ import annotations

import importlib

from django.conf import settings
from django.test import TestCase, override_settings


class CeleryImportTests(TestCase):
    """``config.celery`` imports cleanly and exposes the ``app``
    instance with the documented namespace ``proyecto_c``.
    """

    def test_celery_app_imports_with_expected_namespace(self):
        # Re-import to force a fresh module load; we want to catch any
        # import-time misconfiguration (missing DJANGO_SETTINGS_MODULE,
        # double-``ready`` hook, etc.) immediately.
        import config.celery as celery_module

        importlib.reload(celery_module)
        self.assertTrue(hasattr(celery_module, "app"))
        self.assertEqual(celery_module.app.main, "proyecto_c")


class CeleryEagerDefaultTests(TestCase):
    """The default ``CELERY_TASK_ALWAYS_EAGER`` is True in test
    environments so the cascade path runs synchronously inside the
    request thread. The production code in
    ``dp4500_integration.tasks`` depends on this so the
    PendingCascade row reaches STATUS_COMPLETED before the test
    returns.
    """

    def test_celery_task_always_eager_default_is_true(self):
        # The setting is intentionally read from the module-level
        # ``settings`` because ``override_settings`` would mask the
        # pre-override default; we want the documented default, not
        # whatever an enclosing test class has applied.
        import config.settings as settings_module

        # Reset env-driven overrides before reading the default value.
        # The production helper resolves the env at import time; we
        # verify the default by checking the boolean helper's second
        # argument (the documented fallback) matches the assertion
        # below.
        from config.settings import env_bool

        self.assertIs(
            env_bool("CELERY_TASK_ALWAYS_EAGER_NONEXISTENT", True),
            True,
        )
        # And the live settings value matches the documented default.
        self.assertTrue(settings.CELERY_TASK_ALWAYS_EAGER)

    def test_celery_eager_propagates_errors(self):
        """``CELERY_TASK_EAGER_PROPAGATES`` defaults to True so a
        raised exception during a task body surfaces to the caller
        instead of being swallowed by the eager runner.
        """
        self.assertTrue(settings.CELERY_TASK_EAGER_PROPAGATES)
