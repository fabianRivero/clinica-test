"""Clinic fingerprint agent.

A small Python service that runs on each admin PC with a DigitalPersona
4500 reader attached. It exposes an HTTP/JSON API on
``127.0.0.1:8765`` with the following endpoints:

- ``GET  /health``             — unauthenticated; returns ``{"status":"ok"}``.
- ``POST /capture``            — capture a fingerprint template.
- ``POST /match``              — compare a captured template against an
                                 enrolled template and return a raw score.
- ``POST /release``            — reset fprintd's ``Release`` + ``Claim``
                                 state so a fresh ``VerifyStart`` waits
                                 for a finger contact.
- ``POST /heartbeat``          — forward a heartbeat ping to the backend.

The agent is meant to be exposed to the public internet through a
Cloudflare Tunnel (see ``cloudflared-example.yml``). All sensitive
operations require a static bearer token configured in
``config.ini`` (chmod 600).
"""

from __future__ import annotations

__version__ = "0.2.0"
