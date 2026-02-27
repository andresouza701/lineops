import csv

from django import forms
from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.dateparse import parse_date
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from allocations.models import LineAllocation
from core.mixins import RoleRequiredMixin, StandardPaginationMixin
from users.models import SystemUser

from .forms import PhoneLineForm
from .models import PhoneLine, SIMcard


class SIMCardFilterForm(forms.Form):
    status = forms.ChoiceField(
        required=False,
        choices=[("", "Todos")] + list(SIMcard.Status.choices),
        widget=forms.Select(attrs={"class": "form-select"}),
    )


class SIMcardListView(RoleRequiredMixin, ListView):
    allowed_roles = [SystemUser.Role.ADMIN]
    model = SIMcard
    template_name = "telecom/simcard_list.html"
    context_object_name = "simcards"
    ordering = ["iccid"]

    def get_queryset(self):
        queryset = SIMcard.objects.filter(is_deleted=False)
        status = self.request.GET.get("status", "").strip()
        self.search_query = self.request.GET.get("search", "").strip()

        valid_statuses = {choice[0] for choice in SIMcard.Status.choices}
        if status in valid_statuses:
            queryset = queryset.filter(status=status)

        if self.search_query:
            queryset = queryset.filter(iccid__icontains=self.search_query)

        return queryset.order_by("iccid")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = SIMCardFilterForm(self.request.GET or None)
        context["search_query"] = self.search_query
        return context


class SIMcardCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = [SystemUser.Role.ADMIN]
    model = SIMcard
    template_name = "telecom/simcard_form.html"
    fields = ["iccid", "carrier"]
    success_url = reverse_lazy("telecom:simcard_list")

    def form_valid(self, form):
        messages.success(self.request, "SIM card criado com sucesso.")
        return super().form_valid(form)


class SIMcardUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = [SystemUser.Role.ADMIN]
    model = SIMcard
    template_name = "telecom/simcard_form.html"
    fields = ["iccid", "carrier", "status"]
    success_url = reverse_lazy("telecom:simcard_list")

    def get_queryset(self):
        return SIMcard.objects.filter(is_deleted=False)

    def form_valid(self, form):
        messages.success(self.request, "SIM card atualizado com sucesso.")
        return super().form_valid(form)


class PhoneLineListView(StandardPaginationMixin, RoleRequiredMixin, ListView):
    allowed_roles = [SystemUser.Role.ADMIN]
    model = PhoneLine
    template_name = "telecom/phoneline_list.html"
    context_object_name = "phone_lines"
    paginate_by = 20

    def get_queryset(self):
        self.search_query = self.request.GET.get("search", "").strip()
        self.status_filter = self.request.GET.get("status")
        queryset = PhoneLine.objects.filter(is_deleted=False).select_related("sim_card")

        valid_statuses = {choice[0] for choice in PhoneLine.Status.choices}
        if self.status_filter in valid_statuses:
            queryset = queryset.filter(status=self.status_filter)

        if self.search_query:
            queryset = queryset.filter(
                Q(phone_number__icontains=self.search_query)
                | Q(sim_card__iccid__icontains=self.search_query)
            )

        return queryset.order_by("phone_number")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = PhoneLine.Status.choices
        context["status_filter"] = self.status_filter
        context["search_query"] = self.search_query

        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        encoded = query_params.urlencode()
        context["query_string"] = f"&{encoded}" if encoded else ""

        return context


class PhoneLineDetailView(RoleRequiredMixin, DetailView):
    allowed_roles = [SystemUser.Role.ADMIN]
    model = PhoneLine
    template_name = "telecom/phoneline_detail.html"
    context_object_name = "phone_line"

    def get_queryset(self):
        return PhoneLine.objects.filter(is_deleted=False)


class PhoneLineCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = [SystemUser.Role.ADMIN]
    model = PhoneLine
    form_class = PhoneLineForm
    template_name = "telecom/phoneline_form.html"
    success_url = reverse_lazy("telecom:phoneline_list")

    def form_valid(self, form):
        messages.success(self.request, "Linha telefônica criada com sucesso.")
        return super().form_valid(form)


class PhoneLineUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = [SystemUser.Role.ADMIN]
    model = PhoneLine
    form_class = PhoneLineForm
    template_name = "telecom/phoneline_form.html"
    success_url = reverse_lazy("telecom:phoneline_list")

    def form_valid(self, form):
        messages.success(self.request, "Linha telefônica atualizada com sucesso.")
        return super().form_valid(form)

    def get_queryset(self):
        return PhoneLine.objects.filter(is_deleted=False)


class PhoneLineDeleteView(RoleRequiredMixin, View):
    allowed_roles = [SystemUser.Role.ADMIN]

    def post(self, request, pk):
        phone_line = get_object_or_404(PhoneLine, pk=pk, is_deleted=False)
        phone_line.is_deleted = True
        phone_line.save(update_fields=["is_deleted"])
        messages.success(request, "Linha telefônica excluída com sucesso.")
        return redirect("telecom:phoneline_list")


class PhoneLineHistoryView(RoleRequiredMixin, DetailView):
    allowed_roles = [SystemUser.Role.ADMIN]
    model = PhoneLine
    template_name = "telecom/phoneline_history.html"
    context_object_name = "phone_line"

    def get_queryset(self):
        return PhoneLine.objects.filter(is_deleted=False).prefetch_related(
            "allocations__employee", "allocations__allocated_by"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        allocations = (
            LineAllocation.objects.filter(phone_line=context["phone_line"])
            .select_related("employee", "allocated_by")
            .order_by("-allocated_at")
        )

        start_date = self.request.GET.get("start_date")
        end_date = self.request.GET.get("end_date")

        if start_date:
            start_date_parsed = parse_date(start_date)
            if start_date_parsed:
                allocations = allocations.filter(
                    allocated_at__date__gte=start_date_parsed
                )
        if end_date:
            end_date_parsed = parse_date(end_date)
            if end_date_parsed:
                allocations = allocations.filter(
                    allocated_at__date__lte=end_date_parsed
                )
        context["allocations"] = allocations
        return context


class TelecomOverviewView(RoleRequiredMixin, TemplateView):
    allowed_roles = [SystemUser.Role.ADMIN]
    template_name = "telecom/overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_simcards"] = SIMcard.objects.filter(is_deleted=False).count()
        base_lines = PhoneLine.objects.filter(is_deleted=False)
        context["total_lines"] = base_lines.count()
        counts = self._line_status_counts(base_lines)
        context["allocated_lines"] = LineAllocation.objects.filter(
            is_active=True
        ).count()
        context["available_lines"] = counts.get(PhoneLine.Status.AVAILABLE, 0)
        context["cancelled_lines"] = counts.get(PhoneLine.Status.CANCELLED, 0)
        context["blocked_lines"] = counts.get(PhoneLine.Status.SUSPENDED, 0)

        search = self.request.GET.get("search", "").strip()
        context["search_query"] = search

        lines_qs = base_lines.select_related("sim_card").order_by("phone_number")
        if search:
            lines_qs = lines_qs.filter(
                Q(phone_number__icontains=search) | Q(sim_card__iccid__icontains=search)
            )
        context["phone_lines"] = lines_qs
        # Adiciona as alocações recentes (últimas 10)
        context["allocations"] = LineAllocation.objects.select_related(
            "employee", "phone_line"
        ).order_by("-allocated_at")[:10]
        context.update(self._line_status_summary(counts))
        return context

    def _line_status_counts(self, queryset):
        return {
            row["status"]: row["count"]
            for row in queryset.values("status").annotate(count=Count("id"))
        }

    def _line_status_summary(self, counts):
        boxes = [
            {
                "value": PhoneLine.Status.AVAILABLE,
                "label": "Disponíveis",
                "description": "Prontas para novos colaboradores",
                "variant": "success",
            },
            {
                "value": PhoneLine.Status.ALLOCATED,
                "label": "Ativas",
                "description": "Alocadas e em uso",
                "variant": "primary",
            },
            {
                "value": PhoneLine.Status.SUSPENDED,
                "label": "Bloqueadas",
                "description": "Suspensas temporariamente",
                "variant": "warning",
            },
            {
                "value": PhoneLine.Status.CANCELLED,
                "label": "Canceladas",
                "description": "Encerradas ou desativadas",
                "variant": "danger",
            },
        ]

        status_boxes = []
        for box in boxes:
            status_boxes.append(
                {
                    "label": box["label"],
                    "count": counts.get(box["value"], 0),
                    "value": box["value"],
                    "description": box["description"],
                    "variant": box["variant"],
                }
            )

        return {
            "line_status_boxes": status_boxes,
        }


class ExportPhoneLinesCSVView(RoleRequiredMixin, View):
    allowed_roles = [SystemUser.Role.ADMIN]

    def get(self, request, pk):
        phone_line = get_object_or_404(PhoneLine, pk=pk, is_deleted=False)

        allocations = (
            LineAllocation.objects.filter(phone_line=phone_line)
            .select_related("employee", "allocated_by")
            .order_by("-allocated_at")
        )

        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")

        if start_date:
            start_date_parsed = parse_date(start_date)
            if start_date_parsed:
                allocations = allocations.filter(
                    allocated_at__date__gte=start_date_parsed
                )

        if end_date:
            end_date_parsed = parse_date(end_date)
            if end_date_parsed:
                allocations = allocations.filter(
                    allocated_at__date__lte=end_date_parsed
                )

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="phone_line_{phone_line.id}_history.csv"'
        )

        writer = csv.writer(response)
        writer.writerow(
            [
                "Linha",
                "ICCID",
                "Status",
                "Colaborador",
                "Matrícula",
                "Alocado por",
                "Data alocação",
                "Data liberação",
                "Ativa",
            ]
        )

        for allocation in allocations:
            writer.writerow(
                [
                    phone_line.phone_number,
                    phone_line.sim_card.iccid if phone_line.sim_card else "",
                    phone_line.status,
                    allocation.employee.full_name,
                    allocation.employee.employee_id,
                    allocation.allocated_by.email if allocation.allocated_by else "N/A",
                    allocation.allocated_at,
                    allocation.released_at or "",
                    "Sim" if allocation.is_active else "Não",
                ]
            )

        return response
