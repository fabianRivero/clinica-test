import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogs', '0004_sucursal_especialistas_pueden_abrir_fichas'),
        ('notifications', '0001_initial'),
        ('staff', '0003_especialista_puede_abrir_fichas'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='Ticket',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('asunto', models.CharField(max_length=180)),
                        ('estado', models.CharField(choices=[('ABIERTO', 'Abierto'), ('CERRADO', 'Cerrado')], default='ABIERTO', max_length=10)),
                        ('closed_at', models.DateTimeField(blank=True, null=True)),
                        ('creado_por', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tickets_creados', to=settings.AUTH_USER_MODEL)),
                        ('destinatario_admin', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tickets_recibidos', to=settings.AUTH_USER_MODEL)),
                        ('especialista', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tickets', to='staff.especialista')),
                        ('sucursal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tickets', to='catalogs.sucursal')),
                    ],
                    options={
                        'db_table': 'tickets',
                        'ordering': ('-updated_at',),
                    },
                ),
                migrations.CreateModel(
                    name='TicketMessage',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('contenido', models.TextField()),
                        ('adjunto', models.FileField(blank=True, null=True, upload_to='tickets_adjuntos/%Y/%m/', validators=[django.core.validators.FileExtensionValidator(['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'svg', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'csv', 'zip', 'rar', '7z'])])),
                        ('estado', models.CharField(choices=[('ENVIADO', 'Enviado'), ('RESPONDIDO', 'Respondido')], default='ENVIADO', max_length=12)),
                        ('autor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mensajes_ticket', to=settings.AUTH_USER_MODEL)),
                        ('ticket', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mensajes', to='notifications.ticket')),
                    ],
                    options={
                        'db_table': 'ticket_messages',
                        'ordering': ('created_at',),
                    },
                ),
            ],
            database_operations=[],
        )
    ]
