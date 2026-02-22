from core.mixins import AuthenticadView
from django.urls import reverse_lazy
from django.contrib import messages
from django.utils.dateparse import parse_date
from django.shortcuts import get_object_or_404, redirect
from django.db.models import Count, Q
from django.views.generic import (
    ListView,
    TemplateView,
    DetailView,
    CreateView,
    UpdateView,
    View,
)

from allocations.models import LineAllocation
from .models import PhoneLine, SIMcard
from telecom.models import PhoneLine, SIMcard
from .forms import PhoneLineForm


class SIMcardListView(AuthenticadView, ListView):
    model = SIMcard
    template_name = 'telecom/simcard_list.html'
    context_object_name = 'simcards'
    ordering = ['iccid']


class PhoneLineListView(AuthenticadView, ListView):
    model = PhoneLine
    template_name = 'telecom/phoneline_list.html'
    context_object_name = 'phone_lines'
    paginate_by = 20

    def get_queryset(self):
        self.queryset = PhoneLine.objects.filter(is_deleted=False)

        status = self.request.GET.get('status')
        search = self.request.GET.get('search', '')

        if status:
            self.queryset = self.queryset.filter(status=status)

        valid_statuses = [choice[0] for choice in PhoneLine.Status.choices]
        if status and status not in valid_statuses:
            self.queryset = self.queryset.filter(status=status)

        if search:
            self.queryset = self.queryset.filter(
                Q(phone_number__icontains=search) |
                Q(sim_card__iccid__icontains=search)
            )
        return self.queryset.order_by('created_at')


class PhoneLineDetailView(AuthenticadView, DetailView):
    model = PhoneLine
    template_name = 'telecom/phoneline_detail.html'
    context_object_name = 'phone_line'

    def get_queryset(self):
        return PhoneLine.objects.filter(is_deleted=False)


class PhoneLineCreateView(AuthenticadView, CreateView):
    model = PhoneLine
    form_class = PhoneLineForm
    template_name = 'telecom/phoneline_form.html'
    success_url = reverse_lazy('telecom:phoneline_list')


class PhoneLineUpdateView(AuthenticadView, UpdateView):
    model = PhoneLine
    form_class = PhoneLineForm
    template_name = 'telecom/phoneline_form.html'
    success_url = reverse_lazy('telecom:phoneline_list')

    def get_queryset(self):
        return PhoneLine.objects.filter(is_deleted=False)


class PhoneLineDeleteView(AuthenticadView, View):
    def post(self, request, pk):
        phone_line = get_object_or_404(PhoneLine, pk=pk, is_deleted=False)
        phone_line.is_deleted = True
        phone_line.save(update_fields=['is_deleted'])
        messages.success(request, 'Linha telefônica excluída com sucesso.')
        return redirect('telecom:phoneline_list')


class PhoneLineHistoryView(AuthenticadView, DetailView):
    model = PhoneLine
    template_name = 'telecom/phoneline_history.html'
    context_object_name = 'phone_line'

    def get_queryset(self):
        return PhoneLine.objects.filter(is_deleted=False).prefetch_related('allocations__employee', 'allocations__allocated_by')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        allocations = (
            LineAllocation.objects.filter(phone_line=context['phone_line'])
            .select_related('employee', 'allocated_by')
            .order_by('-allocated_at')
        )

        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')

        if start_date:
            start_date_parsed = parse_date(start_date)
            if start_date_parsed:
                allocations = allocations.filter(allocated_at__date__gte=start_date_parsed)
        if end_date:
            end_date_parsed = parse_date(end_date)
            if end_date_parsed:
                allocations = allocations.filter(allocated_at__date__lte=end_date_parsed)
        context['allocations'] = allocations
        return context


class TelecomOverviewView(AuthenticadView, TemplateView):
    template_name = 'telecom/overview.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_simcards'] = SIMcard.objects.filter(
            is_deleted=False).count()
        base_lines = PhoneLine.objects.filter(is_deleted=False)
        context['total_lines'] = base_lines.count()
        counts = self._line_status_counts(base_lines)
        context['allocated_lines'] = LineAllocation.objects.filter(
            is_active=True).count()
        context['available_lines'] = counts.get(PhoneLine.Status.AVAILABLE, 0)
        context['cancelled_lines'] = counts.get(PhoneLine.Status.CANCELLED, 0)
        context['blocked_lines'] = counts.get(PhoneLine.Status.SUSPENDED, 0)

        search = self.request.GET.get('search', '').strip()
        context['search_query'] = search

        lines_qs = base_lines.select_related(
            'sim_card').order_by('phone_number')
        if search:
            lines_qs = lines_qs.filter(
                Q(phone_number__icontains=search) |
                Q(sim_card__iccid__icontains=search)
            )
        context['phone_lines'] = lines_qs
        context.update(self._line_status_summary(counts))
        return context

    def _line_status_counts(self, queryset):
        return {
            row['status']: row['count']
            for row in queryset.values('status').annotate(count=Count('id'))
        }

    def _line_status_summary(self, counts):
        boxes = [
            {
                'value': PhoneLine.Status.AVAILABLE,
                'label': 'Disponíveis',
                'description': 'Prontas para novos colaboradores',
                'variant': 'success',
            },
            {
                'value': PhoneLine.Status.ALLOCATED,
                'label': 'Ativas',
                'description': 'Alocadas e em uso',
                'variant': 'primary',
            },
            {
                'value': PhoneLine.Status.SUSPENDED,
                'label': 'Bloqueadas',
                'description': 'Suspensas temporariamente',
                'variant': 'warning',
            },
            {
                'value': PhoneLine.Status.CANCELLED,
                'label': 'Canceladas',
                'description': 'Encerradas ou desativadas',
                'variant': 'danger',
            },
        ]

        status_boxes = []
        for box in boxes:
            status_boxes.append({
                'label': box['label'],
                'count': counts.get(box['value'], 0),
                'value': box['value'],
                'description': box['description'],
                'variant': box['variant'],
            })

        return {
            'line_status_boxes': status_boxes,
        }
