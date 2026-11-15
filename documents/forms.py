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
    role = forms.ChoiceField(
        choices=[
            (role.value, role.label)
            for role in DocumentRole.Role
            if role != DocumentRole.Role.SUPERADMIN
        ]
    )

    def clean_username(self):
        username = self.cleaned_data["username"]
        try:
            return get_user_model().objects.get(username=username, is_active=True)
        except get_user_model().DoesNotExist:
            raise forms.ValidationError("No active account has that username.")


class SuperadminSetupForm(forms.Form):
    setup_token = forms.CharField(
        label="One-time setup secret",
        strip=False,
        max_length=256,
        widget=forms.PasswordInput(attrs={"autocomplete": "off"}),
    )
