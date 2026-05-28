from rest_framework.routers import DefaultRouter

from config.api.viewsets.gastos import GastosViewSet

router = DefaultRouter(trailing_slash=False)
router.register(r"gastos", GastosViewSet, basename="gastos")
