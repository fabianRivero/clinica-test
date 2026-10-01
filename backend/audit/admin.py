"""Django admin registration for the ``audit`` app.

Slice 2 only registers a read-only admin view so compliance reviews
can browse the audit trail without touching a database shell. The
list view intentionally exposes no edit/delete affordances — the
audit trail is append-only (design §4 + spec §"Audit Log
(Fail-Closed)"). Future slices may add filter widgets or export
actions; those are not in scope for slice 2.
"""

from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only admin for the audit trail."""

    list_display = (
        "id",
        "created_at",
        "action",
        "user",
        "user_role",
        "resource_type",
        "resource_path",
        "client_ip",
    )
    list_filter = ("action", "user_role")
    search_fields = ("resource_path", "user__username", "client_ip")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False