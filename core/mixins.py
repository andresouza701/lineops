from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class AuthenticadView(LoginRequiredMixin):
    login_url = "/accounts/login/"
    redirect_field_name = "next"


class RoleRequiredMixin(LoginRequiredMixin):
    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Usuario nao autenticado.")

        user_role = (request.user.role or "").lower()
        allowed = {role.lower() for role in self.allowed_roles}

        if user_role not in allowed:
            raise PermissionDenied("Acesso negado: funcao insuficiente.")

        return super().dispatch(request, *args, **kwargs)


def roles_required(*allowed_roles):
    allowed = {role.lower() for role in allowed_roles}

    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise PermissionDenied("Usuario nao autenticado.")

            user_role = (getattr(request.user, "role", "") or "").lower()
            if user_role not in allowed:
                raise PermissionDenied("Acesso negado: funcao insuficiente.")

            return view_func(request, *args, **kwargs)

        return wrapped_view

    return decorator


class StandardPaginationMixin:
    paginate_by = 20
    page_kwarg = "page"
    paginate_orphans = 0
