import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogs', '0004_sucursal_especialistas_pueden_abrir_fichas'),
        ('clinical', '0001_initial'),
        ('operations', '0021_remove_fichacampo_grupo_opciones_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='FichaCampo',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('codigo', models.CharField(max_length=80)),
                        ('etiqueta', models.CharField(max_length=150)),
                        ('tipo_campo', models.CharField(choices=[('TEXTO', 'Texto'), ('NUMERO', 'Numero'), ('FECHA', 'Fecha'), ('BOOLEANO', 'Booleano'), ('SELECCION', 'Seleccion unica'), ('MULTISELECCION', 'Seleccion multiple')], max_length=20)),
                        ('es_multiple', models.BooleanField(default=False)),
                        ('permite_detalle', models.BooleanField(default=False)),
                        ('requerido', models.BooleanField(default=False)),
                        ('orden', models.PositiveIntegerField(default=0)),
                        ('activo', models.BooleanField(default=True)),
                        ('grupo_opciones', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='campos', to='catalogs.grupoopciones')),
                    ],
                    options={
                        'db_table': 'ficha_campos',
                        'ordering': ('seccion', 'orden', 'etiqueta'),
                    },
                ),
                migrations.CreateModel(
                    name='FichaClinica',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('fecha_ficha', models.DateField(default=django.utils.timezone.localdate)),
                        ('motivo_consulta', models.TextField(blank=True)),
                        ('observaciones', models.TextField(blank=True)),
                        ('firma_paciente_ci', models.CharField(blank=True, max_length=120)),
                        ('firma_paciente_url', models.CharField(blank=True, max_length=255)),
                        ('documento_escaneado_pdf', models.FileField(blank=True, null=True, upload_to='fichas_clinicas/%Y/%m/', validators=[django.core.validators.FileExtensionValidator(['pdf'])])),
                        ('consentimiento_aceptado', models.BooleanField(default=False)),
                        ('operacion', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='ficha_clinica', to='operations.operacion')),
                    ],
                    options={
                        'db_table': 'ficha_clinica',
                        'ordering': ('-fecha_ficha',),
                    },
                ),
                migrations.CreateModel(
                    name='FichaRespuestaCampo',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('valor_texto', models.TextField(blank=True)),
                        ('valor_numero', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                        ('valor_fecha', models.DateField(blank=True, null=True)),
                        ('valor_booleano', models.BooleanField(blank=True, null=True)),
                        ('detalle', models.TextField(blank=True)),
                        ('campo', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='respuestas', to='clinical.fichacampo')),
                        ('ficha', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='respuestas_campos', to='clinical.fichaclinica')),
                    ],
                    options={
                        'db_table': 'ficha_respuestas_campos',
                    },
                ),
                migrations.CreateModel(
                    name='FichaRespuestaOpcion',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('opcion', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='respuestas', to='catalogs.opcioncatalogo')),
                        ('respuesta', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='opciones_seleccionadas', to='clinical.ficharespuestacampo')),
                    ],
                    options={
                        'db_table': 'ficha_respuestas_opciones',
                    },
                ),
                migrations.CreateModel(
                    name='FichaSeccion',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('codigo', models.CharField(max_length=80)),
                        ('nombre', models.CharField(max_length=120)),
                        ('orden', models.PositiveIntegerField(default=0)),
                        ('activo', models.BooleanField(default=True)),
                        ('proc_estetico', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='secciones_ficha', to='catalogs.procestetico')),
                    ],
                    options={
                        'db_table': 'ficha_secciones',
                        'ordering': ('proc_estetico', 'orden', 'nombre'),
                    },
                ),
                migrations.AddField(
                    model_name='fichacampo',
                    name='seccion',
                    field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='campos', to='clinical.fichaseccion'),
                ),
                migrations.CreateModel(
                    name='FichaCirugiaEstetica',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('hace_cuanto_tiempo', models.CharField(blank=True, max_length=120)),
                        ('detalle', models.TextField(blank=True)),
                        ('cirugia', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='fichas_rel', to='catalogs.cirugiaestetica')),
                        ('ficha', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cirugias', to='clinical.fichaclinica')),
                    ],
                    options={
                        'db_table': 'ficha_cirugias_esteticas',
                        'constraints': [models.UniqueConstraint(fields=('ficha', 'cirugia'), name='uniq_ficha_cirugia')],
                    },
                ),
                migrations.CreateModel(
                    name='FichaAntecedenteMedico',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('tipo_antecedente', models.CharField(choices=[('FAMILIAR', 'Familiar'), ('PERSONAL', 'Personal')], max_length=10)),
                        ('detalle', models.TextField(blank=True)),
                        ('antecedente', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='fichas_rel', to='catalogs.antecedentemedico')),
                        ('ficha', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='antecedentes', to='clinical.fichaclinica')),
                    ],
                    options={
                        'db_table': 'ficha_antecedentes_medicos',
                        'constraints': [models.UniqueConstraint(fields=('ficha', 'antecedente', 'tipo_antecedente'), name='uniq_ficha_antecedente_tipo')],
                    },
                ),
                migrations.CreateModel(
                    name='FichaImplanteInjerto',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('detalle', models.TextField(blank=True)),
                        ('ficha', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='implantes', to='clinical.fichaclinica')),
                        ('implante', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='fichas_rel', to='catalogs.implanteinjerto')),
                    ],
                    options={
                        'db_table': 'ficha_implantes_injertos',
                        'constraints': [models.UniqueConstraint(fields=('ficha', 'implante'), name='uniq_ficha_implante')],
                    },
                ),
                migrations.AddConstraint(
                    model_name='ficharespuestacampo',
                    constraint=models.UniqueConstraint(fields=('ficha', 'campo'), name='uniq_ficha_campo_respuesta'),
                ),
                migrations.AddConstraint(
                    model_name='ficharespuestaopcion',
                    constraint=models.UniqueConstraint(fields=('respuesta', 'opcion'), name='uniq_respuesta_opcion'),
                ),
                migrations.AddConstraint(
                    model_name='fichaseccion',
                    constraint=models.UniqueConstraint(fields=('proc_estetico', 'codigo'), name='uniq_proc_codigo_seccion'),
                ),
                migrations.AddConstraint(
                    model_name='fichacampo',
                    constraint=models.UniqueConstraint(fields=('seccion', 'codigo'), name='uniq_seccion_codigo_campo'),
                ),
            ],
            database_operations=[],
        )
    ]
