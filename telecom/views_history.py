from django.shortcuts import get_object_or_404
from django.views.generic import ListView

from core.mixins import RoleRequiredMixin
from users.models import SystemUser

from .models import PhoneLine, PhoneLineHistory


class PhoneLineHistoryView(RoleRequiredMixin, ListView):
    """View para exibir o historico de uma linha visivel ao usuario."""

    allowed_roles = [role for role, _label in SystemUser.Role.choices]
    model = PhoneLineHistory
    template_name = "telecom/phoneline_history.html"
    context_object_name = "history"
    paginate_by = 50

    def get_queryset(self):
        visible_lines = PhoneLine.visible_to_user(
            self.request.user,
            PhoneLine.objects.select_related("sim_card"),
        )
        self.phone_line = get_object_or_404(visible_lines, pk=self.kwargs["pk"])
        return PhoneLineHistory.objects.filter(
            phone_line=self.phone_line
        ).select_related("changed_by")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["phone_line"] = self.phone_line
        return context
