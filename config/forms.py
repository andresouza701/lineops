from pathlib import Path

from django import forms
from django.core.exceptions import ValidationError


class UploadForm(forms.Form):
    file = forms.FileField(label="Arquivo (CSV ou XLSX)")

    allowed_extensions = {".csv", ".xlsx"}
    max_upload_size = 25 * 1024 * 1024  # 25 MB

    def clean_file(self):
        uploaded_file = self.cleaned_data.get("file")
        extension = Path(uploaded_file.name).suffix.lower()
        if extension not in self.allowed_extensions:
            raise ValidationError("Envie um arquivo CSV ou XLSX.")

        if uploaded_file.size > self.max_upload_size:
            raise ValidationError("Arquivo muito grande. Limite de 25 MB.")
        return uploaded_file
