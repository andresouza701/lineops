from django.contrib import admin
from django.urls import path, include

from config.views import (
    DashboardView,
    ProfileView,
    OperationsView,
    DocumentationView,
    LogoutGetView,
    HealthCheckView,
)
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from users.views import AdminOnlyView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include("dashboard.urls")),
    path('accounts/logout/', LogoutGetView.as_view(), name='logout'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('employees/', include('employees.urls')),
    path('telecom/', include('telecom.urls')),
    path('allocations/', include('allocations.urls')),
    path('health/', HealthCheckView.as_view(), name='health'),

    # path('', DashboardView.as_view(), name='dashboard'),
    # path('perfil/', ProfileView.as_view(), name='profile'),
    # path('operacoes/', OperationsView.as_view(), name='operations'),
    # path('documentacao/', DocumentationView.as_view(), name='docs'),

    # path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    # path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # path('api/admin-only/', AdminOnlyView.as_view(), name='admin_only'),
]
