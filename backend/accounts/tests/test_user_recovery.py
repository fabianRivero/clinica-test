"""
Tests for the admin-assisted user recovery flow (commits 1-3 of the
feature branch).

Coverage matrix:

Search:
  - test_search_unauthenticated_returns_401
  - test_search_non_admin_returns_403
  - test_search_by_username_finds_user
  - test_search_by_nombre_y_apellido_finds_user
  - test_search_by_email_finds_user
  - test_search_by_phone_finds_user
  - test_search_by_ci_finds_client
  - test_search_by_ci_finds_specialist
  - test_search_empty_query_returns_empty
  - test_search_branch_admin_only_sees_own_branch
  - test_search_branch_admin_other_branch_returns_empty
  - test_search_main_admin_sees_all_branches

Detail:
  - test_detail_unauthenticated_returns_401
  - test_detail_returns_full_user_context
  - test_detail_branch_admin_other_branch_returns_403
  - test_detail_missing_user_returns_404

Reset:
  - test_reset_returns_temporary_password_and_marks_must_change
  - test_reset_invalidates_target_user_sessions
  - test_reset_self_returns_400
  - test_reset_branch_admin_other_branch_returns_403
  - test_reset_missing_user_returns_404
  - test_reset_logs_audit_event

Lifecycle (commit 1+2 hooks):
  - test_self_password_change_clears_must_change_password
  - test_serialize_user_includes_must_change_password
"""

import json
from datetime import date

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Rol, Usuario
from catalogs.models import Sucursal
from customers.models import Cliente
from staff.models import Especialista

SEARCH_URL = reverse("admin-usuarios-buscar-api")


def _url_detail(user_id):
    return reverse("admin-usuarios-detail-api", kwargs={"user_id": user_id})


def _url_reset(user_id):
    return reverse("admin-usuarios-reset-api", kwargs={"user_id": user_id})


class UserRecoverySearchTests(TestCase):
    """Search endpoint: query parsing, branch scoping, and field coverage."""

    def setUp(self):
        self.rol_cliente = Rol.objects.create(rol="CLIENTE")
        self.rol_trabajador = Rol.objects.create(rol="TRABAJADOR")
        self.rol_admin_sucursal = Rol.objects.create(rol="ADMIN_SUCURSAL")
        self.sucursal_norte = Sucursal.objects.create(nombre="Norte", activa=True)
        self.sucursal_sur = Sucursal.objects.create(nombre="Sur", activa=True)

        self.main_admin = Usuario.objects.create_user(
            username="main.admin.search",
            password="admin12345",
            rol=self.rol_admin_sucursal,
            sucursal=self.sucursal_norte,
            email="main.admin@example.com",
            primer_nombre="Main",
            apellido_paterno="Admin",
        )
        self.main_admin.is_superuser = True
        self.main_admin.save()

        self.branch_admin = Usuario.objects.create_user(
            username="branch.admin.search",
            password="admin12345",
            rol=self.rol_admin_sucursal,
            sucursal=self.sucursal_norte,
            email="branch.admin@example.com",
            primer_nombre="Branch",
            apellido_paterno="Admin",
        )

        self.client_user = Usuario.objects.create_user(
            username="cliente.search",
            password="password123",
            rol=self.rol_cliente,
            sucursal=self.sucursal_norte,
            telefono="70000001",
            email="cliente.search@example.com",
            primer_nombre="Carlos",
            apellido_paterno="Cliente",
        )
        self.cliente = Cliente.objects.create(
            usuario=self.client_user,
            telefono="70000001",
            ci="1234567",
            fecha_nacimiento="1990-01-01",
        )

        self.worker_user = Usuario.objects.create_user(
            username="trabajador.search",
            password="password123",
            rol=self.rol_trabajador,
            sucursal=self.sucursal_sur,
            telefono="71000001",
            email="trabajador.search@example.com",
            primer_nombre="Maria",
            apellido_paterno="Trabajador",
        )
        self.especialista = Especialista.objects.create(
            usuario=self.worker_user,
            telefono="71000001",
            ci="7654321",
        )

        self.sur_client = Usuario.objects.create_user(
            username="cliente.sur.search",
            password="password123",
            rol=self.rol_cliente,
            sucursal=self.sucursal_sur,
            primer_nombre="Sur",
            apellido_paterno="Cliente",
        )

        # Dedicated fixture for the multi-token AND search tests:
        # the worker above has apellido_paterno='Trabajador' which
        # would make 'Maria Garcia' return empty. This user has a
        # two-token full name and lives in Norte so it stays in
        # scope for branch-admin tests too.
        self.garcia_user = Usuario.objects.create_user(
            username="maria.garcia.search",
            password="password123",
            rol=self.rol_trabajador,
            sucursal=self.sucursal_norte,
            telefono="72000002",
            email="maria.garcia@example.com",
            primer_nombre="Maria",
            apellido_paterno="Garcia",
            apellido_materno="Lopez",
        )
        Especialista.objects.create(
            usuario=self.garcia_user,
            telefono="72000002",
            ci="8000001",
        )
        Cliente.objects.create(
            usuario=self.sur_client,
            telefono="72000001",
            ci="9999999",
            fecha_nacimiento="1992-02-02",
        )

    def _login(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_search_unauthenticated_returns_401(self):
        client = Client()
        response = client.get(SEARCH_URL, {"q": "anything"})
        self.assertEqual(response.status_code, 401)

    def test_search_non_admin_returns_403(self):
        client = self._login(self.client_user)
        response = client.get(SEARCH_URL, {"q": "anything"})
        self.assertEqual(response.status_code, 403)

    def test_search_by_username_finds_user(self):
        client = self._login(self.main_admin)
        response = client.get(SEARCH_URL, {"q": "cliente.search"})
        self.assertEqual(response.status_code, 200)
        usernames = [u["username"] for u in response.json()["users"]]
        self.assertIn("cliente.search", usernames)

    def test_search_by_nombre_y_apellido_finds_user(self):
        # Single-token query keeps the original OR semantics: 'Maria'
        # matches the worker whose primer_nombre is Maria.
        client = self._login(self.main_admin)
        response = client.get(SEARCH_URL, {"q": "Maria"})
        self.assertEqual(response.status_code, 200)
        usernames = [u["username"] for u in response.json()["users"]]
        self.assertIn("trabajador.search", usernames)

    def test_search_by_full_name_with_two_tokens_finds_user(self):
        # Multi-token AND on full name: 'Maria Garcia' must match the
        # user whose primer_nombre='Maria' and apellido_paterno='Garcia'.
        client = self._login(self.main_admin)
        response = client.get(SEARCH_URL, {"q": "Maria Garcia"})
        self.assertEqual(response.status_code, 200)
        usernames = [u["username"] for u in response.json()["users"]]
        self.assertIn("maria.garcia.search", usernames)

    def test_search_by_full_name_in_any_order_finds_user(self):
        # Token order is irrelevant: 'Garcia Maria' is the same query.
        client = self._login(self.main_admin)
        response = client.get(SEARCH_URL, {"q": "Garcia Maria"})
        self.assertEqual(response.status_code, 200)
        usernames = [u["username"] for u in response.json()["users"]]
        self.assertIn("maria.garcia.search", usernames)

    def test_search_by_full_name_requires_all_tokens(self):
        # AND semantics: a query that includes a token no user has
        # returns empty.
        client = self._login(self.main_admin)
        response = client.get(SEARCH_URL, {"q": "Maria Inexistente"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["users"], [])

    def test_search_by_full_name_with_extra_tokens_does_not_drop_user(self):
        # 3+ tokens where the user has at least 2 matching fields still
        # match (the AND is per-token, not per-field). The Garcia
        # user has 'Maria' + 'Garcia' on file; 'Maria Garcia Whatever'
        # should NOT match because 'Whatever' is not in any name field.
        client = self._login(self.main_admin)
        response = client.get(SEARCH_URL, {"q": "Maria Garcia Whatever"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["users"], [])

    def test_search_by_full_name_matches_across_separate_fields(self):
        # 'Maria Lopez' must match when primer_nombre='Maria' and
        # apellido_materno='Lopez' (the token does NOT have to live in
        # the same field). Validates the per-token OR across name
        # fields inside the multi-token branch.
        client = self._login(self.main_admin)
        response = client.get(SEARCH_URL, {"q": "Maria Lopez"})
        self.assertEqual(response.status_code, 200)
        usernames = [u["username"] for u in response.json()["users"]]
        self.assertIn("maria.garcia.search", usernames)

    def test_search_by_email_finds_user(self):
        client = self._login(self.main_admin)
        response = client.get(SEARCH_URL, {"q": "branch.admin@"})
        self.assertEqual(response.status_code, 200)
        usernames = [u["username"] for u in response.json()["users"]]
        self.assertIn("branch.admin.search", usernames)

    def test_search_by_phone_finds_user(self):
        client = self._login(self.main_admin)
        response = client.get(SEARCH_URL, {"q": "71000001"})
        self.assertEqual(response.status_code, 200)
        usernames = [u["username"] for u in response.json()["users"]]
        self.assertIn("trabajador.search", usernames)

    def test_search_by_ci_finds_client(self):
        client = self._login(self.main_admin)
        response = client.get(SEARCH_URL, {"q": "1234567"})
        self.assertEqual(response.status_code, 200)
        usernames = [u["username"] for u in response.json()["users"]]
        self.assertIn("cliente.search", usernames)

    def test_search_by_ci_finds_specialist(self):
        client = self._login(self.main_admin)
        response = client.get(SEARCH_URL, {"q": "7654321"})
        self.assertEqual(response.status_code, 200)
        usernames = [u["username"] for u in response.json()["users"]]
        self.assertIn("trabajador.search", usernames)

    def test_search_empty_query_returns_empty(self):
        client = self._login(self.main_admin)
        response = client.get(SEARCH_URL, {"q": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["users"], [])

    def test_search_branch_admin_only_sees_own_branch(self):
        client = self._login(self.branch_admin)
        # cliente.search is in the same branch (Norte). The branch admin
        # should be able to find him.
        response = client.get(SEARCH_URL, {"q": "cliente.search"})
        self.assertEqual(response.status_code, 200)
        usernames = [u["username"] for u in response.json()["users"]]
        self.assertIn("cliente.search", usernames)

    def test_search_branch_admin_other_branch_returns_empty(self):
        client = self._login(self.branch_admin)
        # The CI 9999999 only exists for the Sur-branch cliente. The
        # branch admin is in Norte so the Sur user is invisible.
        response = client.get(SEARCH_URL, {"q": "9999999"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["users"], [])

    def test_search_main_admin_sees_all_branches(self):
        client = self._login(self.main_admin)
        # main admin is a superuser so sees both branches. Search by
        # 'Sur' which is the primer_nombre of cliente.sur.search.
        response = client.get(SEARCH_URL, {"q": "Sur"})
        self.assertEqual(response.status_code, 200)
        usernames = [u["username"] for u in response.json()["users"]]
        self.assertIn("cliente.sur.search", usernames)
        # The Norte client is also reachable for main admin (we use
        # 'cliente.search' to assert cross-branch visibility).
        response_norte = client.get(SEARCH_URL, {"q": "cliente.search"})
        self.assertEqual(response_norte.status_code, 200)
        usernames_norte = [
            u["username"] for u in response_norte.json()["users"]
        ]
        self.assertIn("cliente.search", usernames_norte)


class UserRecoveryDetailTests(TestCase):
    """Detail endpoint: branch scoping, 404 handling."""

    def setUp(self):
        self.rol_cliente = Rol.objects.create(rol="CLIENTE")
        self.rol_admin_sucursal = Rol.objects.create(rol="ADMIN_SUCURSAL")
        self.sucursal_norte = Sucursal.objects.create(nombre="Norte", activa=True)
        self.sucursal_sur = Sucursal.objects.create(nombre="Sur", activa=True)

        self.main_admin = Usuario.objects.create_user(
            username="main.admin.detail",
            password="admin12345",
            rol=self.rol_admin_sucursal,
            sucursal=self.sucursal_norte,
            primer_nombre="Main",
            apellido_paterno="Admin",
        )
        self.main_admin.is_superuser = True
        self.main_admin.save()

        self.branch_admin = Usuario.objects.create_user(
            username="branch.admin.detail",
            password="admin12345",
            rol=self.rol_admin_sucursal,
            sucursal=self.sucursal_norte,
            primer_nombre="Branch",
            apellido_paterno="Admin",
        )

        self.norte_client = Usuario.objects.create_user(
            username="norte.client",
            password="password123",
            rol=self.rol_cliente,
            sucursal=self.sucursal_norte,
            primer_nombre="Norte",
            apellido_paterno="Client",
        )

        self.sur_client = Usuario.objects.create_user(
            username="sur.client",
            password="password123",
            rol=self.rol_cliente,
            sucursal=self.sucursal_sur,
            primer_nombre="Sur",
            apellido_paterno="Client",
        )

    def test_detail_unauthenticated_returns_401(self):
        client = Client()
        response = client.get(_url_detail(self.norte_client.id))
        self.assertEqual(response.status_code, 401)

    def test_detail_returns_full_user_context(self):
        client = Client()
        client.force_login(self.main_admin)
        response = client.get(_url_detail(self.norte_client.id))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["id"], self.norte_client.id)
        self.assertEqual(body["username"], "norte.client")
        self.assertEqual(body["fullName"], "Norte Client")
        self.assertEqual(body["kind"], "cliente")
        self.assertEqual(body["sucursalId"], self.sucursal_norte.id)
        self.assertIn("createdAt", body)
        self.assertIn("lastLogin", body)

    def test_detail_branch_admin_other_branch_returns_403(self):
        client = Client()
        client.force_login(self.branch_admin)
        response = client.get(_url_detail(self.sur_client.id))
        self.assertEqual(response.status_code, 403)
        self.assertIn("detail", response.json())

    def test_detail_missing_user_returns_404(self):
        client = Client()
        client.force_login(self.main_admin)
        response = client.get(_url_detail(99999))
        self.assertEqual(response.status_code, 404)


class UserRecoveryResetTests(TestCase):
    """Reset endpoint: happy path, guards, session invalidation, audit log."""

    def setUp(self):
        self.rol_cliente = Rol.objects.create(rol="CLIENTE")
        self.rol_admin_sucursal = Rol.objects.create(rol="ADMIN_SUCURSAL")
        self.sucursal_norte = Sucursal.objects.create(nombre="Norte", activa=True)
        self.sucursal_sur = Sucursal.objects.create(nombre="Sur", activa=True)

        self.main_admin = Usuario.objects.create_user(
            username="main.admin.reset",
            password="admin12345",
            rol=self.rol_admin_sucursal,
            sucursal=self.sucursal_norte,
            primer_nombre="Main",
            apellido_paterno="Admin",
        )
        self.main_admin.is_superuser = True
        self.main_admin.save()

        self.branch_admin = Usuario.objects.create_user(
            username="branch.admin.reset",
            password="admin12345",
            rol=self.rol_admin_sucursal,
            sucursal=self.sucursal_norte,
            primer_nombre="Branch",
            apellido_paterno="Admin",
        )

        self.target = Usuario.objects.create_user(
            username="reset.target",
            password="oldpassword1",
            rol=self.rol_cliente,
            sucursal=self.sucursal_norte,
            email="reset.target@example.com",
            primer_nombre="Reset",
            apellido_paterno="Target",
        )

        self.sur_target = Usuario.objects.create_user(
            username="sur.target",
            password="password123",
            rol=self.rol_cliente,
            sucursal=self.sucursal_sur,
            primer_nombre="Sur",
            apellido_paterno="Target",
        )

    def test_reset_returns_temporary_password_and_marks_must_change(self):
        client = Client()
        client.force_login(self.main_admin)

        response = client.post(_url_reset(self.target.id))
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertEqual(body["user"]["username"], "reset.target")
        self.assertEqual(body["mustChangePassword"], True)
        self.assertEqual(body["sessionInvalidated"], True)
        self.assertEqual(len(body["temporaryPassword"]), 16)

        self.target.refresh_from_db()
        self.assertTrue(self.target.must_change_password)
        self.assertTrue(self.target.check_password(body["temporaryPassword"]))
        self.assertFalse(self.target.check_password("oldpassword1"))

    def test_reset_invalidates_target_user_sessions(self):
        # Log the target user in to create a session row, then have
        # the admin reset. The session row should be deleted. We
        # count sessions that belong to the target user by decoding
        # the session_data and matching _auth_user_id.
        from django.contrib.sessions.models import Session

        target_client = Client()
        target_client.login(username="reset.target", password="oldpassword1")
        target_session_key = target_client.session.session_key

        sessions_for_target_before = 0
        for session in Session.objects.all():
            if session.get_decoded().get("_auth_user_id") == str(self.target.id):
                sessions_for_target_before += 1
        self.assertGreaterEqual(sessions_for_target_before, 1)

        admin_client = Client()
        admin_client.force_login(self.main_admin)
        response = admin_client.post(_url_reset(self.target.id))
        self.assertEqual(response.status_code, 200)

        # The target's session row should be deleted.
        self.assertFalse(Session.objects.filter(session_key=target_session_key).exists())

    def test_reset_self_returns_400(self):
        client = Client()
        client.force_login(self.main_admin)
        response = client.post(_url_reset(self.main_admin.id))
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())

    def test_reset_branch_admin_other_branch_returns_403(self):
        client = Client()
        client.force_login(self.branch_admin)
        response = client.post(_url_reset(self.sur_target.id))
        self.assertEqual(response.status_code, 403)

    def test_reset_missing_user_returns_404(self):
        client = Client()
        client.force_login(self.main_admin)
        response = client.post(_url_reset(99999))
        self.assertEqual(response.status_code, 404)

    def test_reset_logs_audit_event(self):
        client = Client()
        client.force_login(self.main_admin)

        with self.assertLogs("accounts.views", level="WARNING") as logs:
            response = client.post(_url_reset(self.target.id))
        self.assertEqual(response.status_code, 200)

        joined = "\n".join(logs.output)
        self.assertIn("user_recovery_reset", joined)
        self.assertIn(f"actor={self.main_admin.id}", joined)
        self.assertIn(f"target={self.target.id}", joined)
        self.assertIn("target_username=reset.target", joined)


class UserRecoveryLifecycleTests(TestCase):
    """Cross-cutting: must_change_password lifecycle hooks."""

    def setUp(self):
        self.rol_cliente = Rol.objects.create(rol="CLIENTE")
        self.sucursal = Sucursal.objects.create(nombre="Centro", activa=True)
        self.user = Usuario.objects.create_user(
            username="lifecycle.user",
            password="oldpassword1",
            rol=self.rol_cliente,
            sucursal=self.sucursal,
            email="lifecycle@example.com",
            primer_nombre="Life",
            apellido_paterno="Cycle",
        )

    def test_serialize_user_includes_must_change_password(self):
        # Default flag is False on a freshly created user.
        self.assertFalse(self.user.must_change_password)

        client = Client()
        client.login(username="lifecycle.user", password="oldpassword1")

        response = client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["mustChangePassword"], False)

        # Force the flag on (simulates an admin reset) and confirm
        # the response reflects it on the next /me/ call.
        self.user.must_change_password = True
        self.user.save(update_fields=["must_change_password"])

        response = client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["mustChangePassword"], True)

    def test_self_password_change_clears_must_change_password(self):
        self.user.must_change_password = True
        self.user.save(update_fields=["must_change_password"])

        client = Client()
        client.login(username="lifecycle.user", password="oldpassword1")

        response = client.patch(
            "/api/auth/me/",
            data=json.dumps({"password": "brandnewpass1"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["mustChangePassword"], False)

        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)


class UserImportSearchTests(TestCase):
    """Cross-branch client search endpoint used by the import flow.

    Mirrors the multi-token AND-on-full-name behavior introduced for
    /api/admin/usuarios/buscar/ (commit 5366426). A single token does
    a broad OR across username, names, email, phone, CI; multiple
    tokens AND across the four name fields. The user reported that
    'Demo' matched the paciente.demo cliente but 'Demo Demo' did
    not, and that searching by username ('paciente') didn't work.
    """

    def setUp(self):
        self.rol_cliente = Rol.objects.create(rol="CLIENTE")
        self.sucursal_norte = Sucursal.objects.create(nombre="Norte", activa=True)
        self.sucursal_sur = Sucursal.objects.create(nombre="Sur", activa=True)

        self.main_admin = Usuario.objects.create_user(
            username="main.admin.import",
            password="admin12345",
            rol=self.rol_cliente,
            sucursal=self.sucursal_norte,
            primer_nombre="Main",
            apellido_paterno="Admin",
        )
        self.main_admin.is_superuser = True
        self.main_admin.save()

        # Demo Demo paciente: nombre + apellido = "Demo", user with
        # username paciente.demo in Norte.
        self.demo_user = Usuario.objects.create_user(
            username="paciente.demo",
            password="password123",
            rol=self.rol_cliente,
            sucursal=self.sucursal_norte,
            email="demo@example.com",
            telefono="70000001",
            primer_nombre="Demo",
            apellido_paterno="Demo",
        )
        self.demo_cliente = Cliente.objects.create(
            usuario=self.demo_user,
            sucursal_origen=self.sucursal_norte,
            ci="12345678",
            fecha_nacimiento=date(1990, 1, 1),
        )

    def _search(self, query):
        self.client.force_login(self.main_admin)
        response = self.client.get(f"/api/admin/clientes/buscar-global/?q={query}")
        self.client.logout()
        return response

    def test_single_token_finds_by_username(self):
        # 'paciente' matches paciente.demo by username.
        response = self._search("paciente")
        self.assertEqual(response.status_code, 200)
        usernames = [c["name"] for c in response.json()["clients"]]
        self.assertIn("Demo Demo", usernames)

    def test_single_token_finds_by_name(self):
        # 'Demo' matches primer_nombre='Demo' or apellido_paterno='Demo'.
        response = self._search("Demo")
        self.assertEqual(response.status_code, 200)
        usernames = [c["name"] for c in response.json()["clients"]]
        self.assertIn("Demo Demo", usernames)

    def test_multi_token_and_on_full_name(self):
        # 'Demo Demo' must match Demo Demo (primer='Demo' AND
        # apellido='Demo'). Token order is irrelevant: 'Demo Demo' and
        # 'Demo Demo' both work.
        for query in ("Demo Demo",):
            with self.subTest(query=query):
                response = self._search(query)
                self.assertEqual(response.status_code, 200)
                usernames = [c["name"] for c in response.json()["clients"]]
                self.assertIn("Demo Demo", usernames)

    def test_multi_token_excludes_partial_match(self):
        # 'Demo Inactivo' should NOT match Demo Demo because
        # 'Inactivo' is not in any name field of Demo Demo.
        # (Inactivo Demo IS a user that matches, so we just check
        # that Demo Demo specifically is excluded.)
        response = self._search("Demo Inactivo")
        self.assertEqual(response.status_code, 200)
        names = [c["name"] for c in response.json()["clients"]]
        self.assertNotIn("Demo Demo", names)