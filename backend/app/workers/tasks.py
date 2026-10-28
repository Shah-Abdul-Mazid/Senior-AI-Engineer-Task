"""Celery tasks for asynchronous document OCR, AI extraction, and indexing."""
import asyncio
from uuid import UUID
from app.workers.celery_app import celery_app
from app.services.document_service import document_service


@celery_app.task(bind=True, max_retries=3)
def process_document_task(self, document_id_str: str):
    """Celery background worker task for document pipeline."""
    try:
        doc_id = UUID(document_id_str)
        # Run async pipeline in sync Celery worker
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(document_service.process_document_pipeline(doc_id))
        else:
            asyncio.run(document_service.process_document_pipeline(doc_id))
        return {"status": "success", "document_id": document_id_str}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10)
