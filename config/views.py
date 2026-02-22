from django.views.generic import TemplateView


class DashboardView(TemplateView):
    template_name = 'dashboard.html'


class ProfileView(TemplateView):
    template_name = 'profile.html'


class OperationsView(TemplateView):
    template_name = 'operations.html'


class DocumentationView(TemplateView):
    template_name = 'documentation.html'
