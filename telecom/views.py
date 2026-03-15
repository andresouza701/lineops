import csv

from django import forms
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse, JsonResponse
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
from core.exceptions.domain_exceptions import BusinessRuleException
from core.mixins import RoleRequiredMixin, StandardPaginationMixin
from core.services.allocation_service import AllocationService
from users.models import SystemUser

from .forms import PhoneLineForm, PhoneLineUpdateForm, SIMcardCreateWithLineForm
from .models import PhoneLine, PhoneLineHistory, SIMcard


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
    chunk_size = 10

    def get(self, request, *args, **kwargs):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return self._handle_ajax_request(request)
        return super().get(request, *args, **kwargs)

    def _base_filtered_queryset(self, request):
        queryset = SIMcard.objects.filter(is_deleted=False)
        search_query = request.GET.get("search", "").strip()
        status_filter = request.GET.get("status", "").strip()

        valid_statuses = {choice[0] for choice in SIMcard.Status.choices}
        if status_filter in valid_statuses:
            queryset = queryset.filter(status=status_filter)
        else:
            status_filter = ""

        if search_query:
            queryset = queryset.filter(iccid__icontains=search_query)

        return queryset.order_by("iccid"), search_query, status_filter

    def _handle_ajax_request(self, request):
        offset = max(int(request.GET.get("offset", 0)), 0)
        limit = max(int(request.GET.get("limit", self.chunk_size)), 1)
        queryset, _, _ = self._base_filtered_queryset(request)

        simcards = list(queryset[offset : offset + limit])
        has_more = queryset.count() > (offset + len(simcards))

        data = [
            {
                "iccid": sim.iccid,
                "carrier": sim.carrier,
                "status": sim.status,
                "status_display": sim.get_status_display(),
                "activated_at": (
                    sim.activated_at.strftime("%d/%m/%Y %H:%M")
                    if sim.activated_at
                    else ""
                ),
            }
            for sim in simcards
        ]

        return JsonResponse(
            {"data": data, "has_more": has_more, "offset": offset + len(simcards)}
        )

    def get_queryset(self):
        queryset, self.search_query, self.status_filter = self._base_filtered_queryset(
            self.request
        )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = SIMCardFilterForm(self.request.GET or None)
        context["search_query"] = self.search_query
        context["status_filter"] = self.status_filter
        context["initial_simcards"] = list(context["simcards"][: self.chunk_size])
        context["has_more_simcards"] = context["simcards"].count() > len(
            context["initial_simcards"]
        )
        return context


class SIMcardCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = [SystemUser.Role.ADMIN]
    model = SIMcard
    template_name = "telecom/simcard_form.html"
    form_class = SIMcardCreateWithLineForm
    success_url = reverse_lazy("telecom:simcard_list")

    @transaction.atomic
    def form_valid(self, form):
        self.object = form.save()
        phone_number = form.cleaned_data["phone_number"]
        origem = form.cleaned_data.get("origem")
        PhoneLine.objects.create(
            phone_number=phone_number,
            sim_card=self.object,
            status=PhoneLine.Status.AVAILABLE,
            origem=origem,
        )
        messages.success(
            self.request,
            "SIM card e linha criados com sucesso.",
        )
        return redirect(self.get_success_url())


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
    chunk_size = 10

    def get(self, request, *args, **kwargs):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return self._handle_ajax_request(request)
        return super().get(request, *args, **kwargs)

    def _base_filtered_queryset(self, request):
        search_query = request.GET.get("search", "").strip()
        status_filter = request.GET.get("status", "").strip()
        queryset = (
            PhoneLine.objects.filter(is_deleted=False)
            .select_related("sim_card")
            .prefetch_related(
                Prefetch(
                    "allocations",
                    queryset=LineAllocation.objects.filter(is_active=True)
                    .select_related("employee")
                    .order_by("-allocated_at"),
                    to_attr="active_allocations",
                )
            )
        )

        valid_statuses = {choice[0] for choice in PhoneLine.Status.choices}
        if status_filter in valid_statuses:
            queryset = queryset.filter(status=status_filter)
        else:
            status_filter = ""

        if search_query:
            queryset = queryset.filter(
                Q(phone_number__icontains=search_query)
                | Q(sim_card__iccid__icontains=search_query)
            )

        return queryset.order_by("phone_number"), search_query, status_filter

    def _handle_ajax_request(self, request):
        offset = max(int(request.GET.get("offset", 0)), 0)
        limit = max(int(request.GET.get("limit", self.chunk_size)), 1)
        queryset, _, _ = self._base_filtered_queryset(request)

        lines = list(queryset[offset : offset + limit])
        has_more = queryset.count() > (offset + len(lines))
        data = []
        for line in lines:
            employee_name = (
                line.active_allocations[0].employee.full_name
                if line.active_allocations
                else None
            )
            data.append(
                {
                    "phone_number": line.phone_number,
                    "iccid": line.sim_card.iccid,
                    "carrier": line.sim_card.carrier if line.sim_card else "",
                    "origem": line.origem,
                    "origem_display": line.get_origem_display() if line.origem else "",
                    "employee": employee_name,
                    "status": line.status,
                    "status_display": line.get_status_display(),
                }
            )

        return JsonResponse(
            {"data": data, "has_more": has_more, "offset": offset + len(lines)}
        )

    def get_queryset(self):
        queryset, self.search_query, self.status_filter = self._base_filtered_queryset(
            self.request
        )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = PhoneLine.Status.choices
        context["status_filter"] = self.status_filter
        context["search_query"] = self.search_query
        context["initial_lines"] = list(context["phone_lines"][: self.chunk_size])
        context["has_more_lines"] = context["phone_lines"].count() > len(
            context["initial_lines"]
        )

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
    success_url = reverse_lazy("telecom:overview")

    def form_valid(self, form):
        messages.success(self.request, "Linha telefônica criada com sucesso.")
        return super().form_valid(form)


class PhoneLineUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = [SystemUser.Role.ADMIN]
    model = PhoneLine
    form_class = PhoneLineUpdateForm
    template_name = "telecom/phoneline_form.html"
    success_url = reverse_lazy("telecom:overview")

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        if request.POST.get("action") == "release_line":
            active_allocation = (
                LineAllocation.objects.select_related("employee")
                .filter(phone_line=self.object, is_active=True)
                .first()
            )

            if active_allocation:
                AllocationService.release_line(active_allocation, request.user)

            if self.object.status != PhoneLine.Status.AVAILABLE:
                self.object.status = PhoneLine.Status.AVAILABLE
                self.object.save(update_fields=["status"])

            messages.success(request, "Linha liberada com sucesso.")
            return redirect("telecom:phoneline_update", pk=self.object.pk)

        return super().post(request, *args, **kwargs)

    @transaction.atomic
    def form_valid(self, form):
        selected_employee = form.cleaned_data.get("employee")
        active_allocation = (
            LineAllocation.objects.select_related("employee")
            .filter(phone_line=self.object, is_active=True)
            .first()
        )
        will_allocate_new = selected_employee and active_allocation is None

        if will_allocate_new:
            # Avoid intermediate status transitions in audit history.
            form.instance.status = PhoneLine.Status.AVAILABLE

        try:
            with transaction.atomic():
                response = super().form_valid(form)

                if active_allocation and (
                    selected_employee is None
                    or active_allocation.employee_id != selected_employee.id
                ):
                    AllocationService.release_line(active_allocation, self.request.user)

                if selected_employee and (
                    active_allocation is None
                    or active_allocation.employee_id != selected_employee.id
                ):
                    AllocationService.allocate_line(
                        selected_employee, self.object, self.request.user
                    )
        except BusinessRuleException as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        messages.success(self.request, "Linha telefônica atualizada com sucesso.")
        return response

    def get_queryset(self):
        return (
            PhoneLine.objects.filter(is_deleted=False)
            .select_related("sim_card")
            .prefetch_related(
                Prefetch(
                    "allocations",
                    queryset=LineAllocation.objects.filter(is_active=True)
                    .select_related("employee")
                    .order_by("-allocated_at"),
                    to_attr="active_allocations",
                )
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_allocations = getattr(self.object, "active_allocations", [])
        context["active_allocation"] = (
            active_allocations[0] if active_allocations else None
        )
        return context


class PhoneLineDeleteView(RoleRequiredMixin, View):
    allowed_roles = [SystemUser.Role.ADMIN]

    def post(self, request, pk):
        phone_line = get_object_or_404(PhoneLine, pk=pk, is_deleted=False)
        phone_line.is_deleted = True
        phone_line.save(update_fields=["is_deleted"])
        messages.success(request, "Linha telefônica excluída com sucesso.")
        return redirect("telecom:overview")


class PhoneLineHistoryView(RoleRequiredMixin, DetailView):
    allowed_roles = [SystemUser.Role.ADMIN]
    model = PhoneLine
    template_name = "telecom/phoneline_history.html"
    context_object_name = "phone_line"
    paginate_by = 50

    def get_queryset(self):
        return PhoneLine.objects.filter(is_deleted=False).select_related("sim_card")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Consulta o histórico completo da linha
        history = (
            PhoneLineHistory.objects.filter(phone_line=context["phone_line"])
            .select_related("changed_by")
            .order_by("-changed_at")
        )

        context["history"] = history
        return context


class TelecomOverviewView(RoleRequiredMixin, TemplateView):
    allowed_roles = [SystemUser.Role.ADMIN]
    template_name = "telecom/overview.html"

    def get(self, request, *args, **kwargs):
        # Se for requisição AJAX para lazy loading
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return self._handle_ajax_request(request)
        return super().get(request, *args, **kwargs)

    def _handle_ajax_request(self, request):
        """Retorna dados em JSON para lazy loading"""
        table_type = request.GET.get("table", "main")
        offset = int(request.GET.get("offset", 0))
        limit = int(request.GET.get("limit", 10))

        base_lines = PhoneLine.objects.filter(is_deleted=False)
        valid_statuses = {choice[0] for choice in PhoneLine.Status.choices}

        if table_type == "main":
            line_filter = request.GET.get("line", "").strip()
            status_filter = request.GET.get("status", "").strip()

            lines_qs = (
                base_lines.select_related("sim_card")
                .prefetch_related(
                    Prefetch(
                        "allocations",
                        queryset=LineAllocation.objects.filter(is_active=True)
                        .select_related("employee")
                        .order_by("-allocated_at"),
                        to_attr="active_allocations",
                    )
                )
                .order_by("phone_number")
            )

            if line_filter:
                lines_qs = lines_qs.filter(phone_number__icontains=line_filter)
            if status_filter in valid_statuses:
                lines_qs = lines_qs.filter(status=status_filter)

            lines = list(lines_qs[offset : offset + limit])
            has_more = lines_qs.count() > (offset + limit)

        else:  # table_type == 'recent'
            search_query = request.GET.get("search", "").strip()
            status_filter_recent = request.GET.get("status_recent", "").strip()

            lines_qs = (
                base_lines.select_related("sim_card")
                .prefetch_related(
                    Prefetch(
                        "allocations",
                        queryset=LineAllocation.objects.filter(is_active=True)
                        .select_related("employee")
                        .order_by("-allocated_at"),
                        to_attr="active_allocations",
                    )
                )
                .order_by("-updated_at")
            )

            if search_query:
                lines_qs = lines_qs.filter(
                    Q(phone_number__icontains=search_query)
                    | Q(sim_card__iccid__icontains=search_query)
                )
            if status_filter_recent in valid_statuses:
                lines_qs = lines_qs.filter(status=status_filter_recent)

            lines = list(lines_qs[offset : offset + limit])
            has_more = lines_qs.count() > (offset + limit)

        # Formatar dados para JSON
        data = []
        is_admin = request.user.role == "admin"

        for line in lines:
            employee_name = (
                line.active_allocations[0].employee.full_name
                if line.active_allocations
                else None
            )

            line_data = {
                "id": line.pk,
                "phone_number": line.phone_number,
                "iccid": line.sim_card.iccid if line.sim_card else "",
                "carrier": line.sim_card.carrier if line.sim_card else "",
                "origem": line.origem,
                "origem_display": line.get_origem_display() if line.origem else "",
                "employee": employee_name,
                "status": line.status,
                "status_display": line.get_status_display(),
            }

            if table_type == "main" and is_admin:
                line_data["edit_url"] = f"/telecom/phoneline/{line.pk}/update/"
                line_data["history_url"] = f"/telecom/phoneline/{line.pk}/history/"

            data.append(line_data)

        return JsonResponse(
            {"data": data, "has_more": has_more, "offset": offset + len(lines)}
        )

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

        line_filter = self.request.GET.get("line", "").strip()
        status_filter = self.request.GET.get("status", "").strip()
        valid_statuses = {choice[0] for choice in PhoneLine.Status.choices}

        # Consultar apenas as primeiras linhas (lazy loading carregará o resto)
        lines_qs = (
            base_lines.select_related("sim_card")
            .prefetch_related(
                Prefetch(
                    "allocations",
                    queryset=LineAllocation.objects.filter(is_active=True)
                    .select_related("employee")
                    .order_by("-allocated_at"),
                    to_attr="active_allocations",
                )
            )
            .order_by("phone_number")
        )

        if line_filter:
            lines_qs = lines_qs.filter(phone_number__icontains=line_filter)

        if status_filter in valid_statuses:
            lines_qs = lines_qs.filter(status=status_filter)
        else:
            status_filter = ""

        # Carregar primeiros 10 itens
        context["initial_lines"] = list(lines_qs[:10])
        context["has_more_main_lines"] = lines_qs.count() > len(
            context["initial_lines"]
        )
        context["line_filter"] = line_filter
        context["status_filter"] = status_filter
        context["status_choices"] = PhoneLine.Status.choices

        # Segunda tabela: Ações recentes
        search_query = self.request.GET.get("search", "").strip()
        status_filter_recent = self.request.GET.get("status_recent", "").strip()

        recent_lines_qs = (
            base_lines.select_related("sim_card")
            .prefetch_related(
                Prefetch(
                    "allocations",
                    queryset=LineAllocation.objects.filter(is_active=True)
                    .select_related("employee")
                    .order_by("-allocated_at"),
                    to_attr="active_allocations",
                )
            )
            .order_by("-updated_at")
        )

        if search_query:
            recent_lines_qs = recent_lines_qs.filter(
                Q(phone_number__icontains=search_query)
                | Q(sim_card__iccid__icontains=search_query)
            )

        if status_filter_recent in valid_statuses:
            recent_lines_qs = recent_lines_qs.filter(status=status_filter_recent)
        else:
            status_filter_recent = ""

        # Carregar primeiros 10 itens
        context["initial_recent_lines"] = list(recent_lines_qs[:10])
        context["has_more_recent_lines"] = recent_lines_qs.count() > len(
            context["initial_recent_lines"]
        )
        context["search_query"] = search_query
        context["status_filter_recent"] = status_filter_recent

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
                "description": "Prontas para novos usuários",
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
                "Usuário",
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
