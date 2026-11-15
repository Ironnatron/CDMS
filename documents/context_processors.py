from django.conf import settings


def document_feature(request):
    return {"synthetic_documents_enabled": settings.SYNTHETIC_DOCUMENTS_ENABLED}
