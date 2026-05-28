"""
Shared DRF mixins for catalog views.
"""

from rest_framework import serializers


class CatalogFormatMixin:
    """
    Provides standardized catalog list/detail formatting used across
    all catalog viewsets to maintain backward compatibility with the
    existing API response structure.
    """

    def build_catalog_meta(self, catalog_key, title, description, create_label):
        return {
            "key": catalog_key,
            "title": title,
            "description": description,
            "createLabel": create_label,
        }

    def build_metric_set(self, active_count, inactive_count, total_count, relation_label):
        return [
            {
                "id": "catalog-active",
                "label": "Activos",
                "value": str(active_count),
                "delta": "Visibles para nuevas operaciones",
                "tone": "success",
            },
            {
                "id": "catalog-inactive",
                "label": "Inactivos",
                "value": str(inactive_count),
                "delta": "Preservados para historico y reactivacion",
                "tone": "warning",
            },
            {
                "id": "catalog-total",
                "label": "Total",
                "value": str(total_count),
                "delta": relation_label,
                "tone": "primary",
            },
        ]

    def build_catalog_entry(self, item_id, title, subtitle, active, metadata, values):
        return {
            "id": item_id,
            "title": title,
            "subtitle": subtitle,
            "active": active,
            "activeLabel": "Activo" if active else "Inactivo",
            "metadata": metadata,
            "values": values,
        }

    def build_field_definition(
        self,
        name,
        label,
        input_type,
        *,
        required=False,
        options=None,
        placeholder="",
        hint="",
        value_type="string",
        allow_empty=False,
        min_value=None,
    ):
        payload = {
            "name": name,
            "label": label,
            "inputType": input_type,
            "required": required,
            "placeholder": placeholder,
            "hint": hint,
            "valueType": value_type,
            "allowEmpty": allow_empty,
        }
        if options is not None:
            payload["options"] = options
        if min_value is not None:
            payload["minValue"] = min_value
        return payload

    def build_option(self, value, label, secondary_label=""):
        payload = {"value": value, "label": label}
        if secondary_label:
            payload["secondaryLabel"] = secondary_label
        return payload