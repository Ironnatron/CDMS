from pathlib import Path

from django import forms
from django.contrib.auth import get_user_model

from .models import Document, DocumentRole

MAX_DOCUMENT_SIZE = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".txt"}


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["title", "file"]
        widgets = {"file": forms.ClearableFileInput(attrs={"accept": ".pdf,.txt"})}

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if upload.size > MAX_DOCUMENT_SIZE:
            raise forms.ValidationError("The file must be 5 MB or smaller.")
        if upload.size == 0:
            raise forms.ValidationError("The file must not be empty.")
        if Path(upload.name).suffix.lower() not in ALLOWED_EXTENSIONS:
            raise forms.ValidationError("Only PDF and TXT files are allowed.")
        return upload


class RoleForm(forms.Form):
    username = forms.CharField(max_length=150)
    role = forms.ChoiceField(choices=DocumentRole.Role.choices)

    def clean_username(self):
        username = self.cleaned_data["username"]
        try:
            return get_user_model().objects.get(username=username, is_active=True)
        except get_user_model().DoesNotExist:
            raise forms.ValidationError("No active account has that username.")
