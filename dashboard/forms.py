from django import forms
from django.utils import timezone

from .models import DailyIndicator

# B2B Carteiras e Supervisores
B2B_SUPERVISORS = [
    ("Alex", "Alex"),
    ("Barbara", "Barbara"),
    ("Eduardo", "Eduardo"),
    ("Gislaine", "Gislaine"),
    ("Jane", "Jane"),
    ("Jessica", "Jessica"),
    ("Paloma", "Paloma"),
    ("Quezia", "Quezia"),
    ("Rodrigo", "Rodrigo"),
    ("Rosimeri", "Rosimeri"),
]

B2B_PORTFOLIOS = [
    ("Alimentos", "Alimentos"),
    ("Andina", "Andina"),
    ("BackOffice", "BackOffice"),
    ("BAT", "BAT"),
    ("Chilli Beans", "Chilli Beans"),
    ("Femsa", "Femsa"),
    ("Heineki", "Heineki"),
    ("Industria", "Industria"),
    ("Manual Dellys", "Manual Dellys"),
    ("MV - Martins", "MV - Martins"),
    ("MV - Pepsico Repique", "MV - Pepsico Repique"),
    ("MV - Pepsico", "MV - Pepsico"),
    ("MV - Transportes", "MV - Transportes"),
    ("MV - Ações", "MV - Ações"),
    ("MV - Mix", "MV - Mix"),
    ("MV - Dellys", "MV - Dellys"),
    ("MV - Potencial", "MV - Potencial"),
    ("MV - Represado", "MV - Represado"),
    ("Pepsico", "Pepsico"),
    ("Pesquisa", "Pesquisa"),
    ("Sascar", "Sascar"),
    ("Souza", "Souza"),
    ("Tabacos", "Tabacos"),
    ("Têxtil", "Têxtil"),
]

# B2C Carteiras e Supervisores
B2C_SUPERVISORS = [
    ("Camila", "Camila"),
    ("Alex", "Alex"),
    ("Leonardo", "Leonardo"),
]

B2C_PORTFOLIOS = [
    ("Ambiental", "Ambiental"),
    ("Natura", "Natura"),
    ("ViaSat", "ViaSat"),
    ("Opera", "Opera"),
    ("Valid", "Valid"),
]


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
        widget=forms.Select(
            attrs={
                "class": "form-control",
            }
        ),
    )
    portfolio = forms.ChoiceField(
        choices=[],
        label="Carteira",
        widget=forms.Select(
            attrs={
                "class": "form-control",
            }
        ),
    )

    class Meta:
        model = DailyIndicator
        fields = ["segment", "supervisor", "portfolio", "people_logged_in", "date"]
        labels = {
            "segment": "Segmento",
            "supervisor": "Supervisor",
            "portfolio": "Carteira",
            "people_logged_in": "Pessoas Logadas",
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

        # Definir choices dinâmicas baseado no segmento
        segment = self.data.get("segment") or self.initial.get("segment", "B2B")

        if segment == "B2B":
            self.fields["supervisor"].choices = B2B_SUPERVISORS
            self.fields["portfolio"].choices = B2B_PORTFOLIOS
        else:  # B2C
            self.fields["supervisor"].choices = B2C_SUPERVISORS
            self.fields["portfolio"].choices = B2C_PORTFOLIOS

        # Pré-preencher data com hoje
        if not self.data:
            self.fields["date"].initial = timezone.now().date()

    def clean(self):
        cleaned_data = super().clean()
        date = cleaned_data.get("date")
        supervisor = cleaned_data.get("supervisor")
        portfolio = cleaned_data.get("portfolio")
        people_logged_in = cleaned_data.get("people_logged_in")

        # Validar data não pode ser futura
        if date and date > timezone.now().date():
            self.add_error("date", "A data não pode ser no futuro.")

        # Validar campos obrigatórios
        if not supervisor:
            self.add_error("supervisor", "Selecione um supervisor.")
        if not portfolio:
            self.add_error("portfolio", "Selecione uma carteira.")
        if people_logged_in is None or people_logged_in < 0:
            self.add_error("people_logged_in", "Insira um valor válido (≥ 0).")

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
        # Pré-preencher datas (últimos 30 dias)
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
