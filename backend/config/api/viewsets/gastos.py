"""
Gastos ViewSet for DRF migration.
Domain 11 of Phase 6 — final domain.

5 endpoints:
- GET    /gastos/              → list expenses + metrics
- GET    /gastos/categorias/   → category list
- POST   /gastos/crear/        → create expense
- POST   /gastos/<id>/actualizar/ → update expense
- POST   /gastos/<id>/eliminar/  → delete expense
"""

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath

from django.db import models
from django.utils import timezone

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser

from billing.models import CategoriaGasto, GastoSucursal
from config.api.permissions import AdminRequired
from config.api.serializers.expenses import (
    CategoriaGastoListSerializer,
    GastoSucursalCreateSerializer,
    GastoSucursalSerializer,
)
from config.api_helpers import currency, date_label, full_name, get_user_branch, metric


def _expense_category_item(category):
    return {
        "id": category.pk,
        "name": category.nombre,
        "description": category.descripcion,
    }


def _expense_categories_queryset(*, active_only=False):
    queryset = CategoriaGasto.objects.all()
    if active_only:
        queryset = queryset.filter(activo=True)
    return queryset.order_by(
        models.Case(
            models.When(nombre__iexact="Otros", then=0),
            default=1,
            output_field=models.IntegerField(),
        ),
        "nombre",
    )


def _expense_item(expense):
    return {
        "id": f"GAS-{expense.pk:04d}",
        "rawId": expense.pk,
        "date": expense.fecha.isoformat(),
        "dateLabel": date_label(expense.fecha),
        "categoryId": expense.categoria_id,
        "category": expense.categoria.nombre,
        "concept": expense.concepto,
        "units": str(expense.unidades),
        "unitCost": str(expense.costo_unidad),
        "total": str(expense.gasto_total),
        "totalLabel": currency(expense.gasto_total),
        "provider": expense.proveedor,
        "invoiceUrl": expense.factura.url if expense.factura else "",
        "invoiceName": PurePosixPath(expense.factura.name).name if expense.factura else "",
        "details": expense.detalles,
        "branchId": expense.sucursal_id,
        "branchName": expense.sucursal.nombre,
        "registeredBy": full_name(expense.registrado_por) if expense.registrado_por else "Sin registrar",
    }


class GastosViewSet(viewsets.ViewSet):
    """
    DRF ViewSet for branch expense management.

    Endpoints:
    - GET    /gastos/              → list expenses + metrics for a month/year
    - GET    /gastos/categorias/   → category list
    - POST   /gastos/crear/        → create expense
    - POST   /gastos/<id>/actualizar/ → update expense
    - POST   /gastos/<id>/eliminar/  → delete expense
    """

    permission_classes = [AdminRequired]
    parser_classes = [MultiPartParser, FormParser]

    def list(self, request):
        """
        GET /gastos/?month=X&year=Y
        Returns expenses, metrics, and categories for a given month/year.
        """
        branch = get_user_branch(request)
        if not branch:
            return Response(
                {"detail": "Selecciona una sucursal para consultar gastos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = timezone.localdate()
        try:
            month = int(request.query_params.get("month", today.month))
            year = int(request.query_params.get("year", today.year))
            start = date(year, month, 1)
        except (TypeError, ValueError):
            return Response(
                {"detail": "Mes o anio invalido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
                metric(
                    "expenses-total",
                    "Gasto del mes",
                    currency(total_amount),
                    f"{len(expenses)} registro(s)",
                    "danger",
                ),
                metric(
                    "expenses-count",
                    "Gastos registrados",
                    len(expenses),
                    f"{categories_count} categoria(s)",
                    "primary",
                ),
                metric(
                    "expenses-average",
                    "Promedio por gasto",
                    currency(average_amount),
                    "Calculado sobre el mes",
                    "warning",
                ),
            ],
            "categories": [
                _expense_category_item(c)
                for c in _expense_categories_queryset(active_only=True)
            ],
            "expenses": [_expense_item(expense) for expense in expenses],
        })

    @action(detail=False, methods=["get"], url_path="categorias")
    def categorias(self, request):
        """
        GET /gastos/categorias/
        Returns active expense categories.
        """
        categories = _expense_categories_queryset(active_only=True)
        return Response({
            "categories": [_expense_category_item(c) for c in categories],
        })

    @action(detail=False, methods=["post"], url_path="crear")
    def crear(self, request):
        """
        POST /gastos/crear/
        Creates a new expense for the current branch.
        Accepts FormData (multipart) with invoice file upload.
        """
        branch = get_user_branch(request)
        if not branch:
            return Response(
                {"detail": "Selecciona una sucursal para registrar gastos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = GastoSucursalCreateSerializer(
            data=request.data,
            context={"branch": branch, "user": request.user},
        )

        if not serializer.is_valid():
            return Response(
                {"detail": "Hay errores en el formulario.", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        expense = serializer.save()

        # Handle invoice file separately (multipart upload)
        invoice_file = request.FILES.get("invoice")
        if invoice_file:
            expense.factura = invoice_file
            expense.save(update_fields=["factura"])

        expense.refresh_from_db()
        return Response(
            {
                "detail": "Gasto registrado correctamente.",
                "expense": _expense_item(expense),
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="actualizar")
    def actualizar(self, request, pk=None):
        """
        POST /gastos/<id>/actualizar/
        Updates an existing expense.
        """
        branch = get_user_branch(request)
        if not branch:
            return Response(
                {"detail": "Selecciona una sucursal para actualizar gastos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        expense = GastoSucursal.objects.filter(pk=pk, sucursal=branch).first()
        if not expense:
            return Response(
                {"detail": "No encontramos el gasto solicitado en esta sucursal."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = GastoSucursalCreateSerializer(
            data=request.data,
            instance=expense,
            context={"branch": branch, "user": request.user},
        )

        if not serializer.is_valid():
            return Response(
                {"detail": "Hay errores en el formulario.", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        expense = serializer.save()

        # Handle invoice file separately
        if "invoice" in request.FILES:
            expense.factura = request.FILES["invoice"]
            expense.save(update_fields=["factura"])

        expense.refresh_from_db()
        return Response({
            "detail": "Gasto actualizado correctamente.",
            "expense": _expense_item(expense),
        })

    @action(detail=True, methods=["post"], url_path="eliminar")
    def eliminar(self, request, pk=None):
        """
        POST /gastos/<id>/eliminar/
        Deletes an expense.
        """
        branch = get_user_branch(request)
        if not branch:
            return Response(
                {"detail": "Selecciona una sucursal para eliminar gastos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        expense = GastoSucursal.objects.filter(pk=pk, sucursal=branch).first()
        if not expense:
            return Response(
                {"detail": "No encontramos el gasto solicitado en esta sucursal."},
                status=status.HTTP_404_NOT_FOUND,
            )

        expense.delete()
        return Response({"detail": "Gasto eliminado correctamente."})
