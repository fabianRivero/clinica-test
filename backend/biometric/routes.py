"""Route summary for the biometric endpoints.

Decision: PR #1 mounts everything under ``/api/biometric/`` to keep
the new domain cleanly separated from the existing
``config.api_urls`` (which serves ``/api/admin/...``). The orchestrator
guidance explicitly recommends this layout.

URL map (mounted at ``backend/biometric/urls.py``):

    POST   /api/biometric/clientes/<int:cliente_id>/huella/enroll/
        Init enrollment. ADMIN_PRINCIPAL | ADMIN_SUCURSAL. Requires
        explicit ``consentimiento_aceptado``.

    POST   /api/biometric/clientes/<int:cliente_id>/huella/enroll/finalize/
        Accepts the agent's captured template (PR #1 inlines capture
        into enroll-init; this endpoint exists for spec parity and
        forward compatibility with async capture flows).

    POST   /api/biometric/citas/<int:cita_id>/huella/verify-init/
        Returns ``agent_url`` + ``capture_token`` for a cita in
        ``REALIZADA_PENDIENTE_VERIFICACION``. If the client has no
        template row, returns ``{has_fingerprint:false,
        manual_only:true}`` per spec requirement 8.

    POST   /api/biometric/citas/<int:cita_id>/huella/verify-confirm/
        Server compares ``score`` against the configured threshold,
        transitions the cita on success, logs a ``BiometricAttempt``.

    POST   /api/biometric/agents/
        ADMIN_PRINCIPAL only. Creates a new AgentToken, returns the
        raw secret once.

    GET    /api/biometric/agents/
        ADMIN_PRINCIPAL sees all; ADMIN_SUCURSAL sees only their own.

    POST   /api/biometric/agents/<int:agent_id>/heartbeat/
        Bearer-token-authenticated. Updates ``last_seen_at`` and
        returns 204.

    DELETE /api/biometric/agents/<int:agent_id>/
        ADMIN_PRINCIPAL only soft-delete (``is_active = False``).

The legacy ``/api/admin/citas/<id>/confirmar-biometria/`` endpoint
remains in place to avoid breaking older clients; PR #3 swaps the
front-end over and may remove the legacy view in a later change.
"""

URL_PREFIX = "api/biometric"


__all__ = ["URL_PREFIX"]
