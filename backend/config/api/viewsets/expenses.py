"""
Expense viewsets for DRF migration.
Domain 2 of Phase 6.
"""

from decimal import Decimal
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from billing.models import CategoriaGasto, GastoSucursal

from config.api.permissions import AdminRequired
from config.api.serializers.expenses import (
    GastoSucursalSerializer,
    GastoSucursalCreateSerializer,
)
from config.api_helpers import get_user_branch


class GastosViewSet(viewsets.ViewSet):
    """
    DRF ViewSet for expense management.

    Endpoints:
    - GET  /gastos/                                → list expenses with metrics (branch-aware)
    - GET  /gastos/categorias/                     → list active categories (custom action)
    - POST /gastos/crear/                         → create expense
    - POST /gastos/<int:expense_id>/actualizar/   → update expense
    - POST /gastos/<int:expense_id>/eliminar/     → delete expense
    """

    permission_classes = [AdminRequired]

    @action(detail=False, methods=["get"], url_path="categorias")
    def list_categories(self, request):
        """GET /gastos/categorias/ — list active expense categories."""
        categories = CategoriaGasto.objects.filter(activo=True).order_by("nombre")
        return Response(
            {
                "categories": [
                    {
                        "id": c.pk,
                        "nombre": c.nombre,
                        "descripcion": c.descripcion or "",
                        "activo": c.activo,
                        "gastos_count": c.gastos.count(),
                    }
                    for c in categories
                ]
            }
        )

    def list(self, request):
        """GET /gastos/ — list expenses for branch in month/year with metrics."""
        branch = get_user_branch(request)
        if not branch:
            return Response({"detail": "Selecciona una sucursal para consultar gastos."}, status=400)

        today = timezone.localdate()
        try:
            month = int(request.query_params.get("month") or today.month)
            year = int(request.query_params.get("year") or today.year)
            start = date(year, month, 1)
        except (TypeError, ValueError):
            return Response({"detail": "Mes o anio invalido."}, status=400)

        if month == 12:
            end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)

        expenses_qs = (
            GastoSucursal.objects.select_related("categoria", "sucursal", "registrado_por")
            .filter(sucursal=branch, fecha__range=(start, end))
            .order_by("-fecha", "-created_at")
        )

        expenses = list(expenses_qs)
        total_amount = sum((expense.gasto_total for expense in expenses), Decimal("0"))
        average_amount = total_amount / len(expenses) if expenses else Decimal("0")
        categories_count = len({expense.categoria_id for expense in expenses})

        return Response({
            "month": month,
            "year": year,
            "branch": {"id": branch.pk, "name": branch.nombre},
            "metrics": [
                {
                    "id": "expenses-total",
                    "label": "Gasto del mes",
                    "value": f"Bs {total_amount:.2f}",
                    "delta": f"{len(expenses)} registro(s)",
                    "tone": "danger",
                },
                {
                    "id": "expenses-count",
                    "label": "Gastos registrados",
                    "value": str(len(expenses)),
                    "delta": f"{categories_count} categoria(s)",
                    "tone": "primary",
                },
                {
                    "id": "expenses-average",
                    "label": "Promedio por gasto",
                    "value": f"Bs {average_amount:.2f}",
                    "delta": "Calculado sobre el mes",
                    "tone": "warning",
                },
            ],
            "categories": [
                self._expense_category_item(c)
                for c in CategoriaGasto.objects.filter(activo=True).order_by("nombre")
            ],
            "expenses": [self._expense_item(e) for e in expenses],
        })

    def create(self, request):
        """POST /gastos/crear/ — create a new expense."""
        branch = get_user_branch(request)
        if not branch:
            return Response({"detail": "Selecciona una sucursal para registrar gastos."}, status=400)

        serializer = GastoSucursalCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Hay errores en el formulario.", "errors": serializer.errors}, status=400)

        try:
            expense = serializer.save(branch=branch, user=request.user)
        except ValidationError as exc:
            return Response({"detail": "Hay errores en el formulario.", "errors": exc.message_dict}, status=400)

        expense = GastoSucursal.objects.select_related("categoria", "sucursal", "registrado_por").get(pk=expense.pk)
        return Response(
            {
                "detail": "Gasto registrado correctamente.",
                "expense": self._expense_item(expense),
            },
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, expense_id=None):
        """POST /gastos/<int:expense_id>/actualizar/ — update an expense."""
        branch = get_user_branch(request)
        if not branch:
            return Response({"detail": "Selecciona una sucursal para actualizar gastos."}, status=400)

        expense = GastoSucursal.objects.filter(pk=expense_id, sucursal=branch).first()
        if not expense:
            return Response({"detail": "No encontramos el gasto solicitado en esta sucursal."}, status=404)

        serializer = GastoSucursalCreateSerializer(data=request.data, instance=expense)
        if not serializer.is_valid():
            return Response({"detail": "Hay errores en el formulario.", "errors": serializer.errors}, status=400)

        try:
            expense = serializer.save()
        except ValidationError as exc:
            return Response({"detail": "Hay errores en el formulario.", "errors": exc.message_dict}, status=400)

        expense = GastoSucursal.objects.select_related("categoria", "sucursal", "registrado_por").get(pk=expense.pk)
        return Response(
            {
                "detail": "Gasto actualizado correctamente.",
                "expense": self._expense_item(expense),
            }
        )

    def destroy(self, request, expense_id=None):
        """POST /gastos/<int:expense_id>/eliminar/ — delete an expense."""
        branch = get_user_branch(request)
        if not branch:
            return Response({"detail": "Selecciona una sucursal para eliminar gastos."}, status=400)

        expense = GastoSucursal.objects.filter(pk=expense_id, sucursal=branch).first()
        if not expense:
            return Response({"detail": "No encontramos el gasto solicitado en esta sucursal."}, status=404)

        expense.delete()
        return Response({"detail": "Gasto eliminado correctamente."})

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _expense_category_item(self, category):
        return {
            "id": category.pk,
            "nombre": category.nombre,
            "descripcion": category.descripcion or "",
            "activo": category.activo,
            "gastos_count": category.gastos.count(),
        }

    def _expense_item(self, expense):
        return {
            "id": expense.pk,
            "fecha": expense.fecha.isoformat(),
            "concepto": expense.concepto,
            "unidades": str(expense.unidades),
            "costoUnidad": str(expense.costo_unidad),
            "gastoTotal": str(expense.gasto_total),
            "proveedor": expense.proveedor or "",
            "detalles": expense.detalles or "",
            "categoria": {
                "id": expense.categoria.pk,
                "nombre": expense.categoria.nombre,
            },
            "sucursal": {
                "id": expense.sucursal.pk,
                "nombre": expense.sucursal.nombre,
            },
            "registrado_por": (
                f"{expense.registrado_por.primer_nombre} {expense.registrado_por.apellido_paterno}"
                if expense.registrado_por else None
            ),
            "factura_url": expense.factura.url if expense.factura else None,
        }