from django.conf import settings

from .models import DocumentSetup


def document_feature(request):
    enabled = settings.SYNTHETIC_DOCUMENTS_ENABLED
    return {
        "synthetic_documents_enabled": enabled,
        "document_setup_available": (
            enabled
            and request.user.is_authenticated
            and not DocumentSetup.objects.filter(pk=1).exists()
        ),
    }
