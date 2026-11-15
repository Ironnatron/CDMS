from django import forms

from .models import Task


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "description", "status", "due_date"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "due_date": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
        }
