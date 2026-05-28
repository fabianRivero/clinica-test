"""
Catalog viewsets for DRF migration.
Domain 1 of Phase 6.
"""

from django.db import IntegrityError
from django.core.validators import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from catalogs.models import (
    TipoServicio,
    ProcEstetico,
    ProcEsteticosTipo,
    ServicioConfig,
    GrupoOpciones,
    OpcionCatalogo,
)
from billing.models import CategoriaGasto
from staff.models import Especialidad
from clinical.models import FichaCampo, FichaSeccion
from operations.models import Operacion

from config.api.permissions import AdminRequired, AdminPrincipalRequired
from config.api.mixins import CatalogFormatMixin
from config.api.serializers.catalogs import (
    TipoServicioSerializer,
    TipoServicioCreateSerializer,
    ProcEsteticosTipoSerializer,
    ProcEsteticoSerializer,
    ProcEsteticoCreateSerializer,
    ServicioConfigSerializer,
    ServicioConfigCreateSerializer,
    EspecialidadSerializer,
    EspecialidadCreateSerializer,
    GrupoOpcionesSerializer,
    GrupoOpcionesCreateSerializer,
    OpcionCatalogoSerializer,
    CategoriaGastoSerializer,
    CategoriaGastoCreateSerializer,
)


class CatalogsViewSet(CatalogFormatMixin, viewsets.ViewSet):
    """
    DRF ViewSet replicating the catalog CRUD endpoints.

    Endpoints:
    - GET  /catalogos/                      → list catalogs summary
    - GET  /catalogos/<slug:catalog_key>/   → list items + fields for a catalog
    - POST /catalogos/<slug:catalog_key>/crear/           → create item
    - POST /catalogos/<slug:catalog_key>/<int:item_id>/actualizar/ → update item
    - POST /catalogos/<slug:catalog_key>/<int:item_id>/estado/      → toggle active
    """

    permission_classes = [AdminRequired]

    # -------------------------------------------------------------------------
    # List all catalog keys
    # -------------------------------------------------------------------------
    def list(self, request):
        """GET /catalogos/ — return catalog summary list."""
        active_service_types = TipoServicio.objects.filter(activo=True).count()
        active_groups = GrupoOpciones.objects.filter(activo=True).count()
        active_options = OpcionCatalogo.objects.filter(activo=True).count()

        catalogs = [
            self._catalog_item(
                "todos-los-servicios",
                "Todos los servicios",
                ServicioConfig.objects.filter(activo=True).count(),
                "Servicios completos con precio base y procedimiento asociado",
            ),
            self._catalog_item(
                "procedimientos-esteticos",
                "Procedimientos esteticos",
                ProcEstetico.objects.filter(activo=True).count(),
                f"{ServicioConfig.objects.filter(activo=True).count()} configuraciones activas de servicio",
            ),
            self._catalog_item(
                "tipos-servicio",
                "Tipos de servicio",
                active_service_types,
                "Categorias comerciales visibles en operaciones y ventas",
            ),
            self._catalog_item(
                "campos-ficha",
                "Campos de ficha",
                FichaCampo.objects.filter(activo=True).count(),
                f"{FichaCampo.objects.filter(activo=False).count()} campo(s) inactivos preservados",
            ),
            self._catalog_item(
                "grupos-opciones",
                "Grupos de opciones",
                active_groups,
                f"{active_options} opcion(es) activas asociadas",
            ),
            self._catalog_item(
                "patologias-cutaneas",
                "Patologias cutaneas",
            ),
            self._catalog_item(
                "especialidades",
                "Especialidades",
                Especialidad.objects.filter(activo=True).count(),
                "Catalogo usado para especialistas y asignaciones del equipo",
            ),
            self._catalog_item(
                "categorias-gasto",
                "Categorias de gasto",
                CategoriaGasto.objects.filter(activo=True).count(),
                "Clasificacion administrativa para gastos por sucursal",
            ),
        ]
        return Response({"catalogs": catalogs})

    # -------------------------------------------------------------------------
    # List one catalog's items + fields
    # -------------------------------------------------------------------------
    def retrieve(self, request, pk=None):
        """GET /catalogos/<slug:catalog_key>/ — return catalog detail with items."""
        try:
            data = self._catalog_page_data(pk)
        except KeyError:
            return Response({"detail": "El catalogo solicitado no existe."}, status=404)
        return Response(data)

    # -------------------------------------------------------------------------
    # Create
    # -------------------------------------------------------------------------
    def create(self, request, pk=None):
        """POST /catalogos/<slug:catalog_key>/crear/ — create a catalog item."""
        permission = AdminPrincipalRequired()
        if not permission.has_permission(request, self):
            return Response({"detail": "No tienes permisos para crear registros."}, status=403)

        try:
            payload = request.data
        except Exception:
            return Response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

        try:
            obj = self._catalog_parse_payload(pk, payload)
            obj.full_clean()
            obj.save()
        except KeyError:
            return Response({"detail": "El catalogo solicitado no existe."}, status=404)
        except ValidationError as exc:
            return Response({"detail": "Hay errores en el formulario.", "errors": exc.message_dict}, status=400)
        except IntegrityError:
            return Response({"detail": "Ya existe un registro con esos datos clave."}, status=400)

        item = next(
            (i for i in self._catalog_page_data(pk).get("items", []) if i["id"] == obj.pk),
            None,
        )
        return Response(
            {"detail": "Registro creado correctamente.", "item": item},
            status=status.HTTP_201_CREATED,
        )

    # -------------------------------------------------------------------------
    # Update
    # -------------------------------------------------------------------------
    def update(self, request, pk=None, item_id=None):
        """POST /catalogos/<slug:catalog_key>/<int:item_id>/actualizar/ — update item."""
        permission = AdminPrincipalRequired()
        if not permission.has_permission(request, self):
            return Response({"detail": "No tienes permisos para actualizar registros."}, status=403)

        instance = self._catalog_get_instance(pk, item_id)
        if not instance:
            return Response({"detail": "No encontramos el registro solicitado."}, status=404)

        try:
            payload = request.data
        except Exception:
            return Response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

        try:
            obj = self._catalog_parse_payload(pk, payload, instance=instance)
            obj.full_clean()
            obj.save()
        except KeyError:
            return Response({"detail": "El catalogo solicitado no existe."}, status=404)
        except ValidationError as exc:
            return Response({"detail": "Hay errores en el formulario.", "errors": exc.message_dict}, status=400)
        except IntegrityError:
            return Response({"detail": "Ya existe un registro con esos datos clave."}, status=400)

        item = next(
            (i for i in self._catalog_page_data(pk).get("items", []) if i["id"] == obj.pk),
            None,
        )
        return Response(
            {"detail": "Registro actualizado correctamente.", "item": item},
        )

    # -------------------------------------------------------------------------
    # Toggle active
    # -------------------------------------------------------------------------
    @action(detail=False, methods=["post"], url_path="(?P<catalog_key>[^/]+)/(?P<item_id>[^/]+)/estado")
    def toggle_active(self, request, catalog_key=None, item_id=None):
        """POST /catalogos/<slug:catalog_key>/<int:item_id>/estado/ — toggle item active."""
        permission = AdminPrincipalRequired()
        if not permission.has_permission(request, self):
            return Response({"detail": "No tienes permisos para cambiar el estado."}, status=403)

        instance = self._catalog_get_instance(catalog_key, item_id)
        if not instance:
            return Response({"detail": "No encontramos el registro solicitado."}, status=404)

        active = request.data.get("active")
        if not isinstance(active, bool):
            return Response(
                {"detail": "Debes indicar si el registro queda activo o inactivo."},
                status=400,
            )

        instance.activo = active
        instance.save(update_fields=["activo", "updated_at"])

        item = next(
            (i for i in self._catalog_page_data(catalog_key).get("items", []) if i["id"] == instance.pk),
            None,
        )
        return Response(
            {"detail": "Estado actualizado correctamente.", "item": item},
        )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    VALID_CATALOG_KEYS = {
        "todos-los-servicios",
        "procedimientos-esteticos",
        "tipos-servicio",
        "campos-ficha",
        "patologias-cutaneas",
        "especialidades",
        "grupos-opciones",
        "categorias-gasto",
    }

    def _catalog_item(self, key, title, count, description=""):
        return {
            "key": key,
            "title": title,
            "count": count,
            "description": description,
        }

    def _catalog_get_instance(self, catalog_key, item_id):
        """Return model instance for catalog item, or None."""
        try:
            if catalog_key == "todos-los-servicios":
                return ServicioConfig.objects.filter(pk=item_id).first()
            elif catalog_key == "procedimientos-esteticos":
                return ProcEstetico.objects.filter(pk=item_id).first()
            elif catalog_key == "tipos-servicio":
                return TipoServicio.objects.filter(pk=item_id).first()
            elif catalog_key == "especialidades":
                return Especialidad.objects.filter(pk=item_id).first()
            elif catalog_key == "grupos-opciones":
                return GrupoOpciones.objects.filter(pk=item_id).first()
            elif catalog_key == "categorias-gasto":
                return CategoriaGasto.objects.filter(pk=item_id).first()
            elif catalog_key == "patologias-cutaneas":
                from catalogs.models import PatologiaCutanea
                return PatologiaCutanea.objects.filter(pk=item_id).first()
            elif catalog_key == "campos-ficha":
                return FichaCampo.objects.filter(pk=item_id).first()
        except Exception:
            pass
        return None

    def _catalog_page_data(self, catalog_key):
        """Replicate the original _catalog_page_data logic for DRF responses."""
        if catalog_key not in self.VALID_CATALOG_KEYS:
            raise KeyError(catalog_key)

        if catalog_key == "todos-los-servicios":
            queryset = ServicioConfig.objects.select_related(
                "tipo_servicio", "proc_estetico", "proc_estetico__tipo_p_estetico"
            ).order_by("tipo_servicio__tipo", "proc_estetico__proceso", "pk")
            items = [
                self.build_catalog_entry(
                    item.pk,
                    str(item),
                    f"Precio base: Bs {item.precio_base:.2f}",
                    item.activo,
                    [
                        {"label": "Tipo de servicio", "value": item.tipo_servicio.tipo},
                        {"label": "Procedimiento", "value": item.proc_estetico.proceso if item.proc_estetico else "Sin procedimiento"},
                        {"label": "Tipo de procedimiento", "value": item.proc_estetico.tipo_p_estetico.tipo if item.proc_estetico else "No aplica"},
                        {"label": "Operaciones vinculadas", "value": str(item.operaciones.count())},
                    ],
                    {
                        "serviceTypeId": item.tipo_servicio_id,
                        "procedureId": item.proc_estetico_id,
                        "basePrice": str(item.precio_base),
                    },
                )
                for item in queryset
            ]
            active_count = queryset.filter(activo=True).count()
            total_count = queryset.count()
            return {
                "catalog": self.build_catalog_meta(
                    catalog_key, "Todos los servicios",
                    "Administra cada servicio disponible con su precio base y el procedimiento estetico asociado.",
                    "Crear servicio",
                ),
                "metrics": self.build_metric_set(
                    active_count, total_count - active_count, total_count,
                    f"{Operacion.objects.count()} operacion(es) usan este catalogo",
                ),
                "fields": [
                    self.build_field_definition("serviceTypeId", "Tipo de servicio", "select",
                        required=True, value_type="number",
                        options=[self.build_option(t.pk, t.tipo) for t in TipoServicio.objects.filter(activo=True).order_by("orden", "tipo")]),
                    self.build_field_definition("procedureId", "Procedimiento estetico", "select",
                        value_type="number", allow_empty=True,
                        options=[self.build_option(p.pk, p.proceso) for p in ProcEstetico.objects.filter(activo=True).order_by("proceso")]),
                    self.build_field_definition("basePrice", "Precio base", "number",
                        required=True, value_type="number", min_value=0),
                ],
                "items": items,
            }

        if catalog_key == "procedimientos-esteticos":
            queryset = ProcEstetico.objects.select_related("tipo_p_estetico").order_by("orden", "proceso")
            items = [
                self.build_catalog_entry(
                    item.pk, item.proceso,
                    item.tipo_p_estetico.tipo,
                    item.activo,
                    [
                        {"label": "Orden", "value": str(item.orden)},
                        {"label": "Descripcion", "value": item.descripcion or "Sin descripcion"},
                    ],
                    {"name": item.proceso, "description": item.descripcion, "order": item.orden},
                )
                for item in queryset
            ]
            active_count = queryset.filter(activo=True).count()
            total_count = queryset.count()
            return {
                "catalog": self.build_catalog_meta(catalog_key, "Procedimientos esteticos",
                    "Catalogo operativo de procedimientos disponibles para las ventas y fichas clinicas.",
                    "Crear procedimiento"),
                "metrics": self.build_metric_set(active_count, total_count - active_count, total_count,
                    "Usados en configuraciones de servicio"),
                "fields": [
                    self.build_field_definition("procedureName", "Procedimiento", "text", required=True, placeholder="Ej. Hidratacion facial"),
                    self.build_field_definition("procedureTypeId", "Tipo de procedimiento", "select", required=True, value_type="number",
                        options=[self.build_option(t.pk, t.tipo) for t in ProcEsteticosTipo.objects.filter(activo=True).order_by("orden", "tipo")]),
                    self.build_field_definition("description", "Descripcion", "textarea", placeholder="Notas internas"),
                    self.build_field_definition("order", "Orden", "number", value_type="number", min_value=0),
                ],
                "items": items,
            }

        if catalog_key == "tipos-servicio":
            queryset = TipoServicio.objects.order_by("orden", "tipo")
            items = [
                self.build_catalog_entry(
                    item.pk, item.tipo, "Tipo de servicio comercial",
                    item.activo,
                    [
                        {"label": "Orden", "value": str(item.orden)},
                        {"label": "Descripcion", "value": item.descripcion or "Sin descripcion"},
                    ],
                    {"name": item.tipo, "description": item.descripcion, "order": item.orden},
                )
                for item in queryset
            ]
            active_count = queryset.filter(activo=True).count()
            total_count = queryset.count()
            return {
                "catalog": self.build_catalog_meta(catalog_key, "Tipos de servicio",
                    "Categorias comerciales utilizadas al crear configuraciones de servicio y operaciones.",
                    "Crear tipo de servicio"),
                "metrics": self.build_metric_set(active_count, total_count - active_count, total_count,
                    "Usados en configuraciones de servicio"),
                "fields": [
                    self.build_field_definition("name", "Tipo de servicio", "text", required=True, placeholder="Ej. Estetica facial"),
                    self.build_field_definition("description", "Descripcion", "textarea", placeholder="Notas internas"),
                    self.build_field_definition("order", "Orden", "number", value_type="number", min_value=0),
                ],
                "items": items,
            }

        if catalog_key == "especialidades":
            queryset = Especialidad.objects.order_by("orden", "nombre")
            items = [
                self.build_catalog_entry(
                    item.pk, item.nombre, "Especialidad del equipo",
                    item.activo,
                    [
                        {"label": "Orden", "value": str(item.orden)},
                        {"label": "Descripcion", "value": item.descripcion or "Sin descripcion"},
                        {"label": "Especialistas vinculados", "value": str(item.especialistas_rel.count())},
                    ],
                    {"name": item.nombre, "description": item.descripcion, "order": item.orden},
                )
                for item in queryset
            ]
            active_count = queryset.filter(activo=True).count()
            total_count = queryset.count()
            return {
                "catalog": self.build_catalog_meta(catalog_key, "Especialidades",
                    "Administra las especialidades disponibles para asignar al equipo medico y tecnico.",
                    "Crear especialidad"),
                "metrics": self.build_metric_set(active_count, total_count - active_count, total_count,
                    f"{ Especialidad.objects.count()} especialista(s) registrados"),
                "fields": [
                    self.build_field_definition("name", "Especialidad", "text", required=True, placeholder="Ej. Laser terapeutico"),
                    self.build_field_definition("description", "Descripcion", "textarea", placeholder="Notas internas sobre la especialidad"),
                    self.build_field_definition("order", "Orden", "number", value_type="number", min_value=0),
                ],
                "items": items,
            }

        if catalog_key == "grupos-opciones":
            queryset = GrupoOpciones.objects.prefetch_related("opciones").order_by("nombre")
            items = [
                self.build_catalog_entry(
                    item.pk, item.nombre, item.codigo,
                    item.activo,
                    [
                        {"label": "Descripcion", "value": item.descripcion or "Sin descripcion"},
                        {"label": "Opciones activas", "value": str(item.opciones.filter(activo=True).count())},
                        {"label": "Opciones totales", "value": str(item.opciones.count())},
                    ],
                    {"code": item.codigo, "name": item.nombre, "description": item.descripcion},
                )
                for item in queryset
            ]
            active_count = queryset.filter(activo=True).count()
            total_count = queryset.count()
            return {
                "catalog": self.build_catalog_meta(catalog_key, "Grupos de opciones",
                    "Agrupa respuestas reutilizables para campos de ficha y otros formularios dinamicos.",
                    "Crear grupo de opciones"),
                "metrics": self.build_metric_set(active_count, total_count - active_count, total_count,
                    f"{OpcionCatalogo.objects.filter(activo=True).count()} opcion(es) activas asociadas"),
                "fields": [
                    self.build_field_definition("code", "Codigo", "text", required=True, placeholder="Ej. SI_NO"),
                    self.build_field_definition("name", "Nombre", "text", required=True, placeholder="Ej. Si / No"),
                    self.build_field_definition("description", "Descripcion", "textarea", placeholder="Describe el uso del grupo"),
                ],
                "items": items,
            }

        if catalog_key == "categorias-gasto":
            queryset = CategoriaGasto.objects.order_by("nombre")
            items = [
                self.build_catalog_entry(
                    item.pk, item.nombre, "Categoria administrativa de gasto",
                    item.activo,
                    [
                        {"label": "Descripcion", "value": item.descripcion or "Sin descripcion"},
                        {"label": "Gastos vinculados", "value": str(item.gastos.count())},
                    ],
                    {"name": item.nombre, "description": item.descripcion},
                )
                for item in queryset
            ]
            active_count = queryset.filter(activo=True).count()
            total_count = queryset.count()
            return {
                "catalog": self.build_catalog_meta(catalog_key, "Categorias de gasto",
                    "Administra las categorias disponibles para clasificar gastos de sucursal.",
                    "Crear categoria"),
                "metrics": self.build_metric_set(active_count, total_count - active_count, total_count,
                    f"{GastoSucursal.objects.count()} gasto(s) registrados"),
                "fields": [
                    self.build_field_definition("name", "Categoria", "text", required=True, placeholder="Ej. Insumos"),
                    self.build_field_definition("description", "Descripcion", "textarea", placeholder="Notas internas o alcance"),
                ],
                "items": items,
            }

        if catalog_key == "patologias-cutaneas":
            from catalogs.models import PatologiaCutanea
            queryset = PatologiaCutanea.objects.order_by("orden", "nombre")
            items = [
                self.build_catalog_entry(
                    item.pk, item.nombre, "Catalogo clinico",
                    item.activo,
                    [
                        {"label": "Orden", "value": str(item.orden)},
                        {"label": "Descripcion", "value": item.descripcion or "Sin descripcion"},
                    ],
                    {"name": item.nombre, "description": item.descripcion, "order": item.orden},
                )
                for item in queryset
            ]
            active_count = queryset.filter(activo=True).count()
            total_count = queryset.count()
            return {
                "catalog": self.build_catalog_meta(catalog_key, "Patologias cutaneas",
                    "Administra las patologias disponibles para el analisis estetico y sus reportes.",
                    "Crear patologia cutanea"),
                "metrics": self.build_metric_set(active_count, total_count - active_count, total_count,
                    "Utilizadas en analisis esteticos historicos"),
                "fields": [
                    self.build_field_definition("name", "Patologia cutanea", "text", required=True, placeholder="Ej. Rosacea"),
                    self.build_field_definition("description", "Descripcion", "textarea", placeholder="Notas internas o alcance"),
                    self.build_field_definition("order", "Orden", "number", value_type="number", min_value=0),
                ],
                "items": items,
            }

        if catalog_key == "campos-ficha":
            queryset = FichaCampo.objects.select_related("seccion", "seccion__proc_estetico", "grupo_opciones").order_by(
                "seccion__proc_estetico__proceso", "seccion__orden", "seccion__nombre", "orden"
            )
            items = [
                self.build_catalog_entry(
                    item.pk,
                    item.etiqueta,
                    f"{item.seccion.proc_estetico.proceso} · {item.seccion.nombre}",
                    item.activo,
                    [
                        {"label": "Codigo", "value": item.codigo},
                        {"label": "Tipo", "value": item.get_tipo_campo_display()},
                        {"label": "Grupo de opciones", "value": item.grupo_opciones.nombre if item.grupo_opciones else "Sin grupo"},
                        {"label": "Orden", "value": str(item.orden)},
                        {"label": "Requerido", "value": "Si" if item.requerido else "No"},
                        {"label": "Detalle", "value": "Permitido" if item.permite_detalle else "No"},
                    ],
                    {
                        "sectionId": item.seccion_id,
                        "code": item.codigo,
                        "label": item.etiqueta,
                        "fieldType": item.tipo_campo,
                        "optionGroupId": item.grupo_opciones_id,
                        "isMultiple": item.es_multiple,
                        "allowsDetail": item.permite_detalle,
                        "required": item.requerido,
                        "order": item.orden,
                    },
                )
                for item in queryset
            ]
            active_count = queryset.filter(activo=True).count()
            total_count = queryset.count()
            return {
                "catalog": self.build_catalog_meta(catalog_key, "Campos de ficha",
                    "Gestiona las preguntas configurables que aparecen en las fichas clinicas por procedimiento.",
                    "Crear campo de ficha"),
                "metrics": self.build_metric_set(active_count, total_count - active_count, total_count,
                    f"{FichaSeccion.objects.filter(activo=True).count()} seccion(es) disponibles"),
                "fields": [
                    self.build_field_definition("sectionId", "Seccion", "select", required=True, value_type="number",
                        options=[self.build_option(s.pk, s.nombre, secondary_label=s.proc_estetico.proceso)
                                 for s in FichaSeccion.objects.select_related("proc_estetico").filter(activo=True).order_by("proc_estetico__proceso", "orden", "nombre")]),
                    self.build_field_definition("code", "Codigo interno", "text", required=True, placeholder="Ej. BRONCEADO"),
                    self.build_field_definition("label", "Etiqueta visible", "text", required=True, placeholder="Ej. Bronceado reciente"),
                    self.build_field_definition("fieldType", "Tipo de campo", "select", required=True,
                        options=[self.build_option(cv, cl) for cv, cl in FichaCampo.TipoCampo.choices]),
                    self.build_field_definition("optionGroupId", "Grupo de opciones", "select",
                        value_type="number", allow_empty=True,
                        options=[self.build_option(g.pk, g.nombre, secondary_label=g.codigo)
                                 for g in GrupoOpciones.objects.order_by("nombre")],
                        hint="Solo aplica a campos de seleccion."),
                    self.build_field_definition("order", "Orden", "number", value_type="number", min_value=0),
                    self.build_field_definition("isMultiple", "Permite multiples respuestas", "checkbox", value_type="boolean"),
                    self.build_field_definition("allowsDetail", "Permite detalle adicional", "checkbox", value_type="boolean"),
                    self.build_field_definition("required", "Campo obligatorio", "checkbox", value_type="boolean"),
                ],
                "items": items,
            }

        raise KeyError(catalog_key)

    def _catalog_parse_payload(self, catalog_key, payload, instance=None):
        """Parse payload to create/update a catalog model instance."""
        def text_value(key):
            return (payload.get(key) or "").strip()
        def int_value(key, required=False, minimum=0, allow_empty=False):
            raw = payload.get(key)
            if raw in (None, ""):
                if required and not allow_empty:
                    raise ValidationError({key: "Este campo es obligatorio."})
                return None
            try:
                value = int(raw)
            except (TypeError, ValueError):
                raise ValidationError({key: "Debes enviar un numero valido."})
            if value < minimum:
                raise ValidationError({key: f"El valor minimo permitido es {minimum}."})
            return value

        if catalog_key == "todos-los-servicios":
            if instance is None:
                tipo_servicio = TipoServicio.objects.get(pk=int_value("serviceTypeId", required=True))
                proc_estetico_id = int_value("procedureId", allow_empty=True)
                proc_estetico = ProcEstetico.objects.get(pk=proc_estetico_id) if proc_estetico_id else None
                return ServicioConfig(
                    tipo_servicio=tipo_servicio,
                    proc_estetico=proc_estetico,
                    precio_base=payload.get("basePrice"),
                )
            instance.tipo_servicio_id = int_value("serviceTypeId", required=True)
            instance.proc_estetico_id = int_value("procedureId", allow_empty=True) or None
            instance.precio_base = payload.get("basePrice")
            return instance

        if catalog_key == "procedimientos-esteticos":
            if instance is None:
                return ProcEstetico(
                    proceso=text_value("procedureName"),
                    tipo_p_estetico_id=int_value("procedureTypeId", required=True),
                    descripcion=text_value("description"),
                    orden=int_value("order", minimum=0),
                )
            instance.proceso = text_value("procedureName")
            instance.tipo_p_estetico_id = int_value("procedureTypeId", required=True)
            instance.descripcion = text_value("description")
            instance.orden = int_value("order", minimum=0)
            return instance

        if catalog_key == "tipos-servicio":
            if instance is None:
                return TipoServicio(
                    tipo=text_value("name"),
                    descripcion=text_value("description"),
                    orden=int_value("order", minimum=0),
                )
            instance.tipo = text_value("name")
            instance.descripcion = text_value("description")
            instance.orden = int_value("order", minimum=0)
            return instance

        if catalog_key == "especialidades":
            if instance is None:
                return Especialidad(
                    nombre=text_value("name"),
                    descripcion=text_value("description"),
                    orden=int_value("order", minimum=0),
                )
            instance.nombre = text_value("name")
            instance.descripcion = text_value("description")
            instance.orden = int_value("order", minimum=0)
            return instance

        if catalog_key == "grupos-opciones":
            if instance is None:
                return GrupoOpciones(
                    codigo=text_value("code"),
                    nombre=text_value("name"),
                    descripcion=text_value("description"),
                )
            instance.codigo = text_value("code")
            instance.nombre = text_value("name")
            instance.descripcion = text_value("description")
            return instance

        if catalog_key == "categorias-gasto":
            if instance is None:
                return CategoriaGasto(
                    nombre=text_value("name"),
                    descripcion=text_value("description"),
                )
            instance.nombre = text_value("name")
            instance.descripcion = text_value("description")
            return instance

        if catalog_key == "patologias-cutaneas":
            from catalogs.models import PatologiaCutanea
            if instance is None:
                return PatologiaCutanea(
                    nombre=text_value("name"),
                    descripcion=text_value("description"),
                    orden=int_value("order", minimum=0),
                )
            instance.nombre = text_value("name")
            instance.descripcion = text_value("description")
            instance.orden = int_value("order", minimum=0)
            return instance

        if catalog_key == "campos-ficha":
            if instance is None:
                return FichaCampo(
                    seccion_id=int_value("sectionId", required=True),
                    codigo=text_value("code"),
                    etiqueta=text_value("label"),
                    tipo_campo=payload.get("fieldType"),
                    grupo_opciones_id=int_value("optionGroupId", allow_empty=True) or None,
                    es_multiple=payload.get("isMultiple", False),
                    permite_detalle=payload.get("allowsDetail", False),
                    requerido=payload.get("required", False),
                    orden=int_value("order", minimum=0),
                )
            instance.seccion_id = int_value("sectionId", required=True)
            instance.codigo = text_value("code")
            instance.etiqueta = text_value("label")
            instance.tipo_campo = payload.get("fieldType")
            instance.grupo_opciones_id = int_value("optionGroupId", allow_empty=True) or None
            instance.es_multiple = payload.get("isMultiple", False)
            instance.permite_detalle = payload.get("allowsDetail", False)
            instance.requerido = payload.get("required", False)
            instance.orden = int_value("order", minimum=0)
            return instance

        raise KeyError(catalog_key)