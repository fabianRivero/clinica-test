"""Rename FichaClinica.documento_escaneado_pdf to documento_escaneado and accept images.

The wizard at /cms/prospectos/<id>/convertir step 3 (and the matching
reactivation / direct-creation flows) used to require a PDF scan of
the medical ficha. Operators in branches that only have a phone
camera asked for an image upload path too, since not every clinic
has a flatbed scanner at the front desk.

This migration:

1. Renames ``documento_escaneado_pdf`` to ``documento_escaneado``.
   Existing rows keep their stored file paths; the column rename
   doesn't move any bytes on disk.
2. Widens the FileExtensionValidator from ``["pdf"]`` to
   ``["pdf", "jpg", "jpeg", "png", "webp"]`` so either format is
   accepted on subsequent saves.

The matching frontend change widens the ``accept`` attribute on the
file input in ``ConversionStepMedical`` (and renames the FormData
keys to drop the "Pdf" suffix). The endpoint helpers in
``config/prospect_conversion_views.py`` already accept either
``documento_escaneado`` or the legacy ``documento_escaneado_pdf``
key for backward compatibility with in-flight uploads from the old
UI, then normalize the value to the new column name.
"""

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clinical', '0004_analisisestetico_alergias_productos_texto'),
    ]

    operations = [
        migrations.RenameField(
            model_name='fichaclinica',
            old_name='documento_escaneado_pdf',
            new_name='documento_escaneado',
        ),
        migrations.AlterField(
            model_name='fichaclinica',
            name='documento_escaneado',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='fichas_clinicas/%Y/%m/',
                validators=[django.core.validators.FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png', 'webp'])],
            ),
        ),
    ]
