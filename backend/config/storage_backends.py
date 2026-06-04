"""
Custom storage backends for Supabase Storage (S3-compatible) and local dev.
Replace the default storage in STORAGE_PROVIDER logic in settings.py.
"""

import os
import boto3
from botocore.config import Config
from django.core.files.storage import Storage


class SupabaseStorage(Storage):
    """
    Custom storage backend for Supabase Storage (S3-compatible).
    Uses the REST API directly to avoid S3 signing complexity.
    """

    def __init__(self):
        self.bucket_name = os.getenv("SUPABASE_BUCKET")
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.service_role_key = os.getenv("SUPABASE_KEY")
        self.region = "auto"

    def _get_client(self):
        """Build boto3 client with Supabase endpoint."""
        return boto3.client(
            "s3",
            endpoint_url=f"{self.supabase_url}/storage/v1",
            aws_access_key_id=self.service_role_key,
            aws_secret_access_key=self.service_role_key,
            region_name=self.region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        )

    def _open(self, name, mode="rb"):
        from django.core.files.base import ContentFile
        client = self._get_client()
        response = client.get_object(Bucket=self.bucket_name, Key=name)
        return ContentFile(response["Body"].read())

    def _save(self, name, content):
        client = self._get_client()
        content.open()
        client.put_object(Bucket=self.bucket_name, Key=name, Body=content.read())
        content.close()
        return name

    def delete(self, name):
        client = self._get_client()
        client.delete_object(Bucket=self.bucket_name, Key=name)

    def exists(self, name):
        client = self._get_client()
        try:
            client.head_object(Bucket=self.bucket_name, Key=name)
            return True
        except Exception:
            return False

    def url(self, name):
        """
        Returns public URL for the file.
        Supabase public URL format:
        https://xxx.supabase.co/storage/v1/object/public/bucket-name/path
        """
        return f"{self.supabase_url}/storage/v1/object/public/{self.bucket_name}/{name}"

    def size(self, name):
        client = self._get_client()
        response = client.head_object(Bucket=self.bucket_name, Key=name)
        return response["ContentLength"]

    def modification_time(self, name):
        client = self._get_client()
        response = client.head_object(Bucket=self.bucket_name, Key=name)
        from datetime import datetime
        return datetime.fromtimestamp(response["LastModified"].timestamp())


class LocalStorage(Storage):
    """Fallback to local filesystem (Django default FileSystemStorage)."""

    def __init__(self):
        import django.conf
        self.base_url = django.conf.settings.MEDIA_URL
        self.location = django.conf.settings.MEDIA_ROOT

    def _open(self, name, mode="rb"):
        from django.core.files.base import ContentFile
        full_path = self.location / name
        with open(full_path, mode) as f:
            return ContentFile(f.read())

    def _save(self, name, content):
        full_path = self.location / name
        content.open()
        with open(full_path, "wb") as f:
            f.write(content.read())
        content.close()
        return name

    def url(self, name):
        return f"{self.base_url}{name}"

    def delete(self, name):
        import os
        full_path = self.location / name
        os.remove(full_path)

    def exists(self, name):
        import os
        return (self.location / name).exists()