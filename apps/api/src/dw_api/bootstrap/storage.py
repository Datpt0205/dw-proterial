"""Object-storage wiring.

One MinIO client, two buckets with different jobs: knowledge artifacts (indexed,
retrievable, tenant-prefixed by the gateway) and platform attachments (opaque
blobs a user uploaded). Separate buckets so retention and blast radius stay
separate.
"""

from __future__ import annotations

from minio import Minio

from dw_api.adapters.attachment_storage import MinioAttachmentStorage
from dw_api.settings import ApiSettings
from dw_knowledge.ports import ObjectStoragePort
from dw_platform.application.ports import FeedbackAttachmentStoragePort


def build_minio_client(settings: ApiSettings) -> Minio | None:
    if not settings.s3_endpoint_url:
        return None
    endpoint = settings.s3_endpoint_url.replace("http://", "").replace("https://", "")
    return Minio(
        endpoint,
        access_key=settings.s3_access_key or "",
        secret_key=settings.s3_secret_key or "",
        secure=settings.s3_endpoint_url.startswith("https://"),
    )


def build_object_storage(client: Minio | None, settings: ApiSettings) -> ObjectStoragePort | None:
    if client is None:
        return None
    from dw_knowledge.adapters.minio_storage import MinioObjectStorageAdapter

    return MinioObjectStorageAdapter(client=client, bucket=settings.s3_bucket)


def build_attachment_storage(
    client: Minio | None, settings: ApiSettings
) -> FeedbackAttachmentStoragePort | None:
    if client is None:
        return None
    return MinioAttachmentStorage(client=client, bucket=settings.feedback_bucket)
