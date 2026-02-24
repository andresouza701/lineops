from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class AuthenticadView(LoginRequiredMixin):
    login_url = "/accounts/login/"
    redirect_field_name = "next"


class RoleRequiredMixin(LoginRequiredMixin):
    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Usuário não autenticado.")

        user_role = (request.user.role or "").lower()
        allowed = {role.lower() for role in self.allowed_roles}

        if user_role not in allowed:
            raise PermissionDenied("Acesso negado: função insuficiente.")

        return super().dispatch(request, *args, **kwargs)


class StandardPaginationMixin:
    paginate_by = 20
    page_kwarg = "page"
    paginate_orphans = 0
