from django.contrib import admin
from django.urls import path

from config.views import (
    DashboardView,
    ProfileView,
    OperationsView,
    DocumentationView,
)
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from users.views import AdminOnlyView

urlpatterns = [
    path('admin/', admin.site.urls),

    path('', DashboardView.as_view(), name='dashboard'),
    path('perfil/', ProfileView.as_view(), name='profile'),
    path('operacoes/', OperationsView.as_view(), name='operations'),
    path('documentacao/', DocumentationView.as_view(), name='docs'),

    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/admin-only/', AdminOnlyView.as_view(), name='admin_only'),
]
