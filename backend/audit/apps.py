from django.apps import AppConfig


class AuditConfig(AppConfig):
    """Django app config for the ``audit`` package.

    Slice 2 of the cloud-storage-migration change ships only the model
    + writer service so the signed-URL endpoint can be wired end to
    end. Future slices may add admin integration or retention cron
    jobs; nothing here blocks slice 2 today.
    """

    name = "audit"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "Audit log"