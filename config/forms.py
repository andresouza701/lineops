from pathlib import Path
from uuid import uuid4

from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import get_valid_filename


class UploadForm(forms.Form):
    file = forms.FileField(label="Arquivo (CSV ou XLSX)")

    allowed_extensions = {".csv", ".xlsx"}
    max_upload_size = 25 * 1024 * 1024  # 25 MB

    def clean_file(self):
        uploaded_file = self.cleaned_data.get("file")
        if not uploaded_file:
            raise ValidationError("Nenhum arquivo foi enviado.")

        extension = Path(uploaded_file.name).suffix.lower()
        if extension not in self.allowed_extensions:
            raise ValidationError("Envie um arquivo CSV ou XLSX.")

        if uploaded_file.size > self.max_upload_size:
            raise ValidationError("Arquivo muito grande. Limite de 25 MB.")

        sample = uploaded_file.read(2048)
        uploaded_file.seek(0)
        if extension == ".xlsx" and not sample.startswith(b"PK\x03\x04"):
            raise ValidationError("Arquivo XLSX invalido ou corrompido.")
        if extension == ".csv" and b"\x00" in sample:
            raise ValidationError("Arquivo CSV invalido.")

        # Sanitize user-provided filenames and avoid path traversal/collisions.
        stem = get_valid_filename(Path(uploaded_file.name).stem) or "upload"
        uploaded_file.name = f"{stem}-{uuid4().hex[:8]}{extension}"
        return uploaded_file
