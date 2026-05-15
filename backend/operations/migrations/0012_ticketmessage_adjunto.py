from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0011_ticket_ticketmessage"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticketmessage",
            name="adjunto",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="tickets_adjuntos/%Y/%m/",
                validators=[
                    django.core.validators.FileExtensionValidator([
                        "png", "jpg", "jpeg", "webp", "gif", "bmp", "svg", "pdf", "doc", "docx", "xls", "xlsx", "txt", "csv", "zip", "rar", "7z"
                    ])
                ],
            ),
        ),
    ]
