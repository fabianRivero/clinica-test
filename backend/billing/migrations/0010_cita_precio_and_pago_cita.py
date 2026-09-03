# Hand-written for citas-pagos (PR 1: backend data layer).
#
# Creates the sibling ``PagoCita`` table with the XOR CheckConstraint
# and FK indexes for the admin cobro surface. The ``precio`` columns
# on ``CitaMedica`` and ``CitaClienteLibre`` land in the operations
# app migration ``0028_citamedica_precio_citaclientelibre_precio``;
# both ship together as a single additive change.

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0009_payment_physical_virtual_fields'),
        ('operations', '0028_citamedica_precio_citaclientelibre_precio'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PagoCita',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'monto_pagado',
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=10,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                (
                    'metodo_pago',
                    models.CharField(
                        choices=[
                            ('VIRTUAL', 'Virtual'),
                            ('FISICO', 'Físico'),
                            ('MIXTO', 'Mixto'),
                        ],
                        default='VIRTUAL',
                        max_length=10,
                    ),
                ),
                (
                    'monto_fisico',
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=10,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                (
                    'monto_virtual',
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=10,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                (
                    'comprobante_url',
                    models.FileField(
                        blank=True,
                        upload_to='comprobantes_citas/%Y/%m/',
                        validators=[
                            django.core.validators.FileExtensionValidator(
                                ['png', 'jpg', 'jpeg', 'webp', 'pdf']
                            )
                        ],
                    ),
                ),
                (
                    'estado_verificacion',
                    models.CharField(
                        choices=[
                            ('PENDIENTE', 'Pendiente'),
                            ('APROBADO', 'Aprobado'),
                            ('RECHAZADO', 'Rechazado'),
                            ('CANCELADO', 'Cancelado'),
                        ],
                        default='PENDIENTE',
                        max_length=20,
                    ),
                ),
                ('fecha_verificacion', models.DateTimeField(blank=True, null=True)),
                ('detalles_pago', models.TextField(blank=True)),
                (
                    'cita_medica',
                    models.ForeignKey(
                        blank=True,
                        db_index=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='pagos_cita',
                        to='operations.citamedica',
                    ),
                ),
                (
                    'cita_cliente_libre',
                    models.ForeignKey(
                        blank=True,
                        db_index=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='pagos_cita',
                        to='operations.citaclientelibre',
                    ),
                ),
                (
                    'verificado_por',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='pagos_cita_verificados',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'db_table': 'pagos_citas',
                'ordering': ('-created_at',),
            },
        ),
        migrations.AddIndex(
            model_name='pagocita',
            index=models.Index(
                fields=['cita_medica', '-created_at'],
                name='pagos_citas_cita_me_fcf574_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='pagocita',
            index=models.Index(
                fields=['cita_cliente_libre', '-created_at'],
                name='pagos_citas_cita_cl_504a53_idx',
            ),
        ),
        migrations.AddConstraint(
            model_name='pagocita',
            constraint=models.CheckConstraint(
                check=(
                    models.Q(
                        cita_medica__isnull=True,
                        cita_cliente_libre__isnull=False,
                    )
                    | models.Q(
                        cita_medica__isnull=False,
                        cita_cliente_libre__isnull=True,
                    )
                ),
                name='pago_cita_xor_cita_fk',
            ),
        ),
    ]