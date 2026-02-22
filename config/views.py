from django.contrib.auth.views import LogoutView
from django.http import JsonResponse
from django.views.generic import TemplateView


class DashboardView(TemplateView):
    template_name = 'dashboard.html'


class ProfileView(TemplateView):
    template_name = 'profile.html'


class OperationsView(TemplateView):
    template_name = 'operations.html'


class DocumentationView(TemplateView):
    template_name = 'documentation.html'


class UploadView(TemplateView):
    template_name = 'upload/upload.html'


class LogoutGetView(LogoutView):
    http_method_names = ['get', 'post', 'options']

    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)


class HealthCheckView(TemplateView):
    # Usa TemplateView apenas para evitar boilerplate; sobrepõe get
    def get(self, request, *args, **kwargs):
        return JsonResponse({'status': 'ok'})
