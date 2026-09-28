# Generated for Phase 2A5 of dp4500-host-app-integration-phase2.
#
# Adds ``Cliente.external_id`` UUIDField so the cross-system handle the
# DP4500 service API uses to address a given cliente can be persisted at
# the Cliente layer (independent of the auth-user UUID on
# ``Usuario.biometric_external_id``, which the frontend's wizard-mint
# overrides via the finalize handler).

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0017_alter_cliente_origen"),
    ]

    operations = [
        migrations.AddField(
            model_name="cliente",
            name="external_id",
            field=models.UUIDField(
                blank=True,
                db_index=True,
                help_text=(
                    "Cross-system UUID the DP4500 service API uses to address this "
                    "cliente. Mirrors Usuario.biometric_external_id once the "
                    "prospect-conversion finalize handler has wired the "
                    "wizard-minted UUID."
                ),
                null=True,
                unique=True,
                default=None,
            ),
        ),
    ]
