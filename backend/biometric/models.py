"""Models for the biometric integration (DigitalPersona 4500).

`HuellaBiometricaCliente` itself lives in `customers/models.py` per project
convention; this module only declares the **new** models that the integration
brings in:

- ``BiometricAttempt``: per-action audit log (enroll/verify).
- ``AgentToken``: per-PC static bearer token (hashed at rest).

Both rely on ``common.models.TimeStampedModel`` for ``created_at`` /
``updated_at`` to match the rest of the project.
"""

from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class BiometricAttempt(TimeStampedModel):
    """Audit log row written for every enroll/verify attempt.

    Holds **only** metadata (no template bytes) per spec requirement on
    privacy of template material. The composite index
    ``(cita, created_at)`` supports the "list by cita ordered by time"
    query pattern.
    """

    class Operation(models.TextChoices):
        ENROLL = "ENROLL", "Enrollment"
        VERIFY = "VERIFY", "Verification"

    class FailureReason(models.TextChoices):
        NO_IMAGE = "NO_IMAGE", "No image"
        LOW_QUALITY = "LOW_QUALITY", "Low capture quality"
        BELOW_THRESHOLD = "BELOW_THRESHOLD", "Score below threshold"
        DECRYPT_FAILED = "DECRYPT_FAILED", "Decryption failed"
        AGENT_OFFLINE = "AGENT_OFFLINE", "Agent unreachable"

    cita = models.ForeignKey(
        "operations.CitaMedica",
        on_delete=models.SET_NULL,
        related_name="biometric_attempts",
        null=True,
        blank=True,
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="biometric_attempts",
        null=True,
        blank=True,
    )
    cliente = models.ForeignKey(
        "customers.Cliente",
        on_delete=models.CASCADE,
        related_name="biometric_attempts",
    )
    operation = models.CharField(max_length=16, choices=Operation.choices)
    success = models.BooleanField(default=False)
    score = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    failure_reason = models.CharField(
        max_length=32,
        choices=FailureReason.choices,
        blank=True,
        default="",
    )
    agent_pc = models.ForeignKey(
        "biometric.AgentToken",
        on_delete=models.SET_NULL,
        related_name="attempts_logged",
        null=True,
        blank=True,
    )
    # ``created_at`` comes from TimeStampedModel; we explicitly include it in
    # the composite index via Meta.indexes.

    class Meta:
        db_table = "biometric_attempts"
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(
                fields=("cita", "created_at"),
                name="biometric_atts_cita_created",
            ),
            models.Index(
                fields=("cliente", "operation"),
                name="biometric_atts_cliente_op",
            ),
        ]               

    def __str__(self):
        return (
            f"BiometricAttempt(cliente={self.cliente_id}, "
            f"op={self.operation}, success={self.success})"
        )


class AgentToken(TimeStampedModel):
    """Per-PC bearer token issued by an admin principal.

    The raw token is generated once on create and returned in the create
    response. Only its SHA-256 hex digest is persisted in ``token_hash``;
    the raw token is also stored under ``token_encrypted`` (Fernet-encrypted)
    so the backend can perform OUTBOUND calls to the agent (the agent
    itself never initiates contact). The Fernet key is the same
    ``BIOMETRIC_FERNET_KEY`` used for templates.

    The two fields serve different purposes:

    - ``token_hash``  — INBOUND auth: the agent presents the raw bearer,
      the backend hashes it and looks up the row by hash. Never decrypts.
    - ``token_encrypted`` — OUTBOUND auth: the backend constructs the
      Authorization header for ``BaseAgentClient`` calls.

    Inactive tokens are rejected by ``IsAgentToken`` permission.
    """

    name = models.CharField(max_length=120)
    sucursal = models.ForeignKey(
        "catalogs.Sucursal",
        on_delete=models.PROTECT,
        related_name="biometric_agent_tokens",
    )
    token_hash = models.CharField(max_length=64, unique=True)
    public_url = models.URLField(max_length=255)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="biometric_agent_tokens_created",
        null=True,
        blank=True,
    )
    # Fernet-encrypted raw token (used for outbound calls). Optional so
    # existing rows from PR #1 (which only had token_hash) keep
    # working; the agent will need to be re-issued to call out.
    token_encrypted = models.BinaryField(null=True, blank=True)

    class Meta:
        db_table = "biometric_agent_tokens"
        ordering = ("sucursal__nombre", "name")

    def __str__(self):
        return f"AgentToken({self.name} @ {self.sucursal_id})"

    @staticmethod
    def hash_token(raw_token: str) -> str:
        """Return ``sha256(raw).hexdigest()`` — used both for storage and
        during auth lookup. Centralized so it cannot drift between code
        paths.
        """
        import hashlib

        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @property
    def token_fingerprint(self) -> str:
        """First 8 chars of the SHA-256 hex — safe to log/display for
        correlation without exposing the secret.
        """
        return self.token_hash[:8]

    def decrypt_raw_token(self) -> str:
        """Return the raw bearer token (Fernet-decrypted).

        Used by ``HttpAgentClient`` to construct the
        ``Authorization: Bearer <raw>`` header for outbound calls.

        Raises:
            RuntimeError: when ``token_encrypted`` is empty (legacy
                row, or the agent was created before PR #2). Operators
                must DELETE + recreate the agent to recover.
            cryptography.fernet.InvalidToken: when the Fernet key has
                rotated; same remediation path.
        """
        from biometric.services.encryption import InvalidToken, decrypt_template

        if not self.token_encrypted:
            raise RuntimeError(
                f"AgentToken {self.id} has no encrypted raw token; "
                "re-issue the agent via DELETE + POST /api/biometric/agents/."
            )
        try:
            plaintext = decrypt_template(bytes(self.token_encrypted))
        except InvalidToken as exc:
            raise RuntimeError(
                f"AgentToken {self.id} raw token could not be decrypted; "
                "the Fernet key has rotated. Re-issue the agent."
            ) from exc
        return plaintext.decode("utf-8")
