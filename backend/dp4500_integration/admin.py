"""Read-only admin registration for PendingCascade + BiometricEnrollmentRecord.

Operators can inspect pending cascades (no manual mutation — the
Celery worker owns the lifecycle).
"""
from django.contrib import admin

from dp4500_integration.models import (
    BiometricEnrollmentRecord,
    PendingCascade,
)


@admin.register(PendingCascade)
class PendingCascadeAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user_external_id", "sucursal_id", "status",
        "attempts", "created_at", "last_attempt_at", "completed_at",
    )
    list_filter = ("status", "sucursal_id")
    search_fields = ("user_external_id",)
    readonly_fields = (
        "user_external_id", "sucursal_id", "attempts",
        "last_error_code", "created_at", "last_attempt_at",
        "completed_at",
    )

    def has_add_permission(self, request):
        return False


@admin.register(BiometricEnrollmentRecord)
class BiometricEnrollmentRecordAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user", "user_external_id", "wizard_id",
        "enrollment_strategy", "advanced_at", "cancelled_at",
    )
    list_filter = ("enrollment_strategy",)
    search_fields = ("user__username", "wizard_id", "user_external_id")
    readonly_fields = (
        "user", "user_external_id", "wizard_id",
        "enrollment_strategy", "advanced_at", "advanced_by",
        "cancelled_at",
    )

    def has_add_permission(self, request):
        return False
