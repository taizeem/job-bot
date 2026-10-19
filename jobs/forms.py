from django import forms
from .models import Application, Resume


class ResumeUploadForm(forms.ModelForm):
    """Form to handle candidate PDF resume uploads with validation."""

    class Meta:
        model = Resume
        fields = ["name", "file"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none text-slate-800",
                    "placeholder": "e.g. Alex Mercer - Senior Python Engineer",
                }
            ),
            "file": forms.FileInput(
                attrs={
                    "class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 cursor-pointer",
                    "accept": ".pdf,application/pdf",
                }
            ),
        }

    def clean_file(self):
        file = self.cleaned_data.get("file")
        if file:
            if not file.name.lower().endswith(".pdf"):
                raise forms.ValidationError("Only PDF files are supported. Please upload a valid .pdf resume.")
            # 10MB file limit
            if file.size > 10 * 1024 * 1024:
                raise forms.ValidationError("File size exceeds 10MB limit. Please upload a smaller PDF.")
        return file


class ApplicationStatusUpdateForm(forms.ModelForm):
    """Form to update application status from the dashboard."""

    class Meta:
        model = Application
        fields = ["status", "notes"]
        widgets = {
            "status": forms.Select(
                attrs={
                    "class": "px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 text-slate-800 bg-white text-sm"
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 text-slate-800 text-sm",
                    "rows": 3,
                    "placeholder": "Add interview notes, recruiter details, or next steps...",
                }
            ),
        }