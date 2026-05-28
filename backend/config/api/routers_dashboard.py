from rest_framework.routers import DefaultRouter

from config.api.viewsets.dashboard import DashboardViewSet

router = DefaultRouter(trailing_slash=False)
router.register(r"dashboard", DashboardViewSet, basename="dashboard")
