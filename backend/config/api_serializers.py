"""
DRF serializers for the admin reports endpoints.

These serializers back the read-only data exposed under
``/api/admin/reportes/``. They are intentionally flat and explicitly emit the
report-specific camelCase fields (``firstName``, ``lastName``, ``ci``,
``status``, ``lastAppointmentDate`` for clients; ``firstName`` / ``lastName``
plus phone/ci/interest/state/createdAt/registeredBy for prospects; and the
income-specific ``paymentId``/``date``/``time``/``amount``/``clientName``/
``serviceName``/``status``/``invoiceUrl``/``invoiceName`` for income) so the
frontend never has to re-split strings or rename backend fields.

Each serializer derives its row data from the corresponding helper in
``config.api_views`` (``_client_item``, ``_prospect_item``,
``_payment_item``). That keeps branch-scoped queries, formatting, and fallback
values (e.g. ``"Sin telefono"``) consistent with the rest of the admin API.
"""

from rest_framework import serializers


class ReportClientSerializer(serializers.Serializer):
    """Read-only row used by the admin client report."""

    id = serializers.CharField()
    rawId = serializers.IntegerField()
    firstName = serializers.CharField()
    lastName = serializers.CharField()
    ci = serializers.CharField()
    status = serializers.CharField()
    lastAppointmentDate = serializers.SerializerMethodField()

    def get_lastAppointmentDate(self, obj):
        value = obj.get("lastAppointmentDate")
        return value if value else None


class ReportProspectSerializer(serializers.Serializer):
    """Read-only row used by the admin prospect report."""

    id = serializers.CharField()
    rawId = serializers.IntegerField()
    firstName = serializers.CharField()
    lastName = serializers.CharField()
    phone = serializers.CharField()
    ci = serializers.SerializerMethodField()
    interest = serializers.CharField()
    state = serializers.CharField()
    createdAt = serializers.CharField()
    registeredBy = serializers.CharField()

    def get_ci(self, obj):
        # Prospects do not always carry a CI; render an explicit dash so the
        # frontend table stays uniform and the export keeps a stable column.
        value = obj.get("ci")
        return value if value else "-"


class ReportIncomeSerializer(serializers.Serializer):
    """Read-only row used by the admin monthly income report."""

    paymentId = serializers.IntegerField()
    date = serializers.CharField()
    time = serializers.CharField()
    amount = serializers.CharField()
    clientName = serializers.CharField()
    serviceName = serializers.CharField()
    status = serializers.CharField()
    invoiceUrl = serializers.CharField(allow_blank=True, allow_null=True)
    invoiceName = serializers.CharField(allow_blank=True, allow_null=True)
