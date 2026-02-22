from django.contrib.auth.mixins import LoginRequiredMixin

class AuthenticadView(LoginRequiredMixin):
    login_url = '/accounts/login/'
    redirect_field_name = 'next'