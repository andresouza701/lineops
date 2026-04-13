from django import forms
from django.utils import timezone

from core.constants import (
    B2B_PORTFOLIOS,
    B2B_SUPERVISORS,
    B2C_PORTFOLIOS,
    B2C_SUPERVISORS,
)
from employees.models import Employee

from .models import DailyIndicator

MAX_PEOPLE_LOGGED_IN = 5000


def sort_choice_pairs(choices):
    return sorted(choices, key=lambda item: str(item[1]).casefold())


class DailyIndicatorForm(forms.ModelForm):
    segment = forms.ChoiceField(
        choices=DailyIndicator.SEGMENT_CHOICES,
        widget=forms.RadioSelect,
        label="Segmento",
        initial="B2B",
    )
    supervisor = forms.ChoiceField(
        choices=[],
        label="Supervisor",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    portfolio = forms.ChoiceField(
        choices=[],
        label="Carteira",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    class Meta:
        model = DailyIndicator
        fields = ["segment", "supervisor", "portfolio", "people_logged_in", "date"]
        labels = {
            "segment": "Segmento",
            "supervisor": "Supervisor",
            "portfolio": "Carteira",
            "people_logged_in": "Usuários Logados",
            "date": "Data do Indicador",
        }
        widgets = {
            "people_logged_in": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0",
                    "placeholder": "Ex: 15",
                }
            ),
            "date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                    "max": timezone.now().date().isoformat(),
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        segment = self.data.get("segment") or self.initial.get("segment", "B2B")

        if segment == "B2B":
            supervisors = sort_choice_pairs(B2B_SUPERVISORS)
            portfolios = sort_choice_pairs(B2B_PORTFOLIOS)
        else:
            supervisors = sort_choice_pairs(B2C_SUPERVISORS)
            portfolios = sort_choice_pairs(B2C_PORTFOLIOS)

        self.fields["supervisor"].choices = [("", "Selecione")] + supervisors
        self.fields["portfolio"].choices = [("", "Selecione")] + portfolios

        if not self.data:
            self.fields["date"].initial = timezone.now().date()

    def clean(self):
        cleaned_data = super().clean()
        date = cleaned_data.get("date")
        supervisor = cleaned_data.get("supervisor")
        portfolio = cleaned_data.get("portfolio")
        people_logged_in = cleaned_data.get("people_logged_in")

        if date and date > timezone.now().date():
            self.add_error("date", "A data não pode ser no futuro.")

        if not supervisor:
            self.add_error("supervisor", "Selecione um supervisor.")
        if not portfolio:
            self.add_error("portfolio", "Selecione uma carteira.")
        if people_logged_in is None:
            self.add_error("people_logged_in", "Campo obrigatorio.")
        elif people_logged_in < 0:
            self.add_error("people_logged_in", "Insira um valor valido (>= 0).")
        elif people_logged_in > MAX_PEOPLE_LOGGED_IN:
            self.add_error(
                "people_logged_in",
                f"Valor deve estar entre 0 e {MAX_PEOPLE_LOGGED_IN}.",
            )

        return cleaned_data


class DailyIndicatorFilterForm(forms.Form):
    """Formulário para filtrar indicadores na página de gestão"""

    SEGMENT_CHOICES = [("", "Todos")] + list(DailyIndicator.SEGMENT_CHOICES)

    segment = forms.ChoiceField(
        choices=SEGMENT_CHOICES,
        required=False,
        label="Segmento",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    supervisor = forms.CharField(
        max_length=100,
        required=False,
        label="Supervisor",
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Filtrar por supervisor..."}
        ),
    )

    portfolio = forms.CharField(
        max_length=100,
        required=False,
        label="Carteira",
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Filtrar por carteira..."}
        ),
    )

    date_from = forms.DateField(
        required=False,
        label="Data início",
        widget=forms.DateInput(
            attrs={
                "class": "form-control",
                "type": "date",
            }
        ),
    )

    date_to = forms.DateField(
        required=False,
        label="Data fim",
        widget=forms.DateInput(
            attrs={
                "class": "form-control",
                "type": "date",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.data:
            today = timezone.now().date()
            self.fields["date_from"].initial = today - timezone.timedelta(days=30)
            self.fields["date_to"].initial = today

    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get("date_from")
        date_to = cleaned_data.get("date_to")

        if date_from and date_to and date_from > date_to:
            self.add_error("date_from", "Data início não pode ser depois da data fim.")

        return cleaned_data


class DailyUserActionForm(forms.Form):
    ACTION_CHOICES = [
        ("", "Sem ação"),
        ("new_number", "Número novo"),
        ("reconnect_whatsapp", "Reconectar WhatsApp"),
        ("pending", "PendÃªncia"),
    ]

    day = forms.DateField(widget=forms.HiddenInput())
    employee_id = forms.IntegerField(widget=forms.HiddenInput())
    allocation_id = forms.CharField(widget=forms.HiddenInput(), required=False)
    action_type = forms.ChoiceField(
        choices=ACTION_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    note = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-sm",
                "placeholder": "Observação opcional",
            }
        ),
    )
    line_status = forms.ChoiceField(
        choices=Employee.LineStatus.choices,
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
