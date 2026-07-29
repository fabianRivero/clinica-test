# Clinic fingerprint agent — Dockerfile
#
# This is a development-only image. Real production deployments use
# the systemd unit on the bare admin PC because the agent needs
# direct USB access to the DigitalPersona 4500 (the reader is a USB
# device, not a network one — running it inside a container outside
# of privileged mode is not useful).
#
# Use this image to:
#   - Run the agent's pytest suite in CI without a real PC.
#   - Smoke-test the HTTP layer with `AGENT_BRIDGE=memory`.
#
# Build:
#   docker build -t fingerprint-agent .
#
# Run tests:
#   docker run --rm fingerprint-agent pytest
#
# Run the agent (in-memory bridge so the container doesn't need a
# USB reader):
#   docker run --rm -p 127.0.0.1:8765:8765 -e AGENT_BRIDGE=memory \
#       -v "$PWD/config.ini.example:/etc/fingerprint-agent/config.ini:ro" \
#       fingerprint-agent

FROM python:3.12-slim

# System deps for the hardware stack. The CI image installs these so
# the Dockerfile can be built and unit tests can run even on a
# developer box without libfprint.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libfprint-2-2 \
        fprintd \
        libdbus-glib-1-2 \
        libgirepository1.0-dev \
        pkg-config \
        gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/fingerprint-agent
COPY requirements.txt .
COPY pyproject.toml .
COPY agent ./agent
COPY server.py .

# Create a venv so the systemd unit can call .venv/bin/python.
RUN python3.12 -m venv .venv \
    && .venv/bin/pip install --no-cache-dir -r requirements.txt

ENV PYTHONUNBUFFERED=1 \
    PATH="/opt/fingerprint-agent/.venv/bin:$PATH"

# Default to the in-memory bridge so the container does not require
# D-Bus. Operators override at runtime with -e AGENT_BRIDGE=fprintd.
ENV AGENT_BRIDGE=memory

EXPOSE 8765

CMD ["server.py", "--config", "/etc/fingerprint-agent/config.ini"]
