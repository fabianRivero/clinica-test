"""Method dispatch helpers for biometric URLs.

Allows a single URL path to serve more than one HTTP verb by routing
on ``request.method``. We keep this in its own module so the views
themselves stay focused on business logic.
"""

from __future__ import annotations

from django.http import HttpResponseNotAllowed

from biometric import views


def dispatch_agent_root(request, **kwargs):
    if request.method == "POST":
        return views.agent_create(request, **kwargs)
    if request.method == "GET":
        return views.agent_list(request, **kwargs)
    return HttpResponseNotAllowed(["GET", "POST"])


def dispatch_agent_detail(request, agent_id: int, **kwargs):
    if request.method == "DELETE":
        return views.agent_delete(request, agent_id=agent_id, **kwargs)
    if request.method == "GET":
        # Reserved for future single-agent retrieve; for now return
        # 405 so the contract is explicit.
        return HttpResponseNotAllowed(["DELETE"])
    return HttpResponseNotAllowed(["DELETE"])


__all__ = ["dispatch_agent_detail", "dispatch_agent_root"]
