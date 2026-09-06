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
    clienteCodigo = serializers.CharField(allow_blank=True, required=False)
    firstName = serializers.CharField()
    lastName = serializers.CharField()
    ci = serializers.CharField()
    status = serializers.CharField()
    lastAppointmentDate = serializers.SerializerMethodField()
    nextAppointmentDate = serializers.SerializerMethodField()
    lastPaymentDate = serializers.SerializerMethodField()
    nextPaymentDate = serializers.SerializerMethodField()
    # ``origen`` — surfaced per the ``cliente-origen`` spec requirement
    # that every Cliente-shaped payload expose this field for reporting
    # visibility. Default keeps the field safe even if a future caller
    # forgets to include it in the row dict.
    origen = serializers.CharField(default="NUEVO")

    def _nullable(self, obj, key):
        value = obj.get(key)
        return value if value else None

    def get_lastAppointmentDate(self, obj):
        return self._nullable(obj, "lastAppointmentDate")

    def get_nextAppointmentDate(self, obj):
        return self._nullable(obj, "nextAppointmentDate")

    def get_lastPaymentDate(self, obj):
        return self._nullable(obj, "lastPaymentDate")

    def get_nextPaymentDate(self, obj):
        return self._nullable(obj, "nextPaymentDate")


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
    lastAppointmentDate = serializers.SerializerMethodField()
    nextAppointmentDate = serializers.SerializerMethodField()

    def get_ci(self, obj):
        # Prospects do not always carry a CI; render an explicit dash so the
        # frontend table stays uniform and the export keeps a stable column.
        value = obj.get("ci")
        return value if value else "-"

    def _nullable(self, obj, key):
        value = obj.get(key)
        return value if value else None

    def get_lastAppointmentDate(self, obj):
        return self._nullable(obj, "lastAppointmentDate")

    def get_nextAppointmentDate(self, obj):
        return self._nullable(obj, "nextAppointmentDate")


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
