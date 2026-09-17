"""Object storage for platform attachments (feedback screenshots today).

``dw_platform`` declares ``FeedbackAttachmentStoragePort`` and may not import a
storage SDK (import-linter), so the concrete adapter lives beside the
composition root that hands it over. It runs on its own bucket: an attachment a
user uploaded is not a knowledge artifact and should not share a lifecycle,
a retention rule or a blast radius with one.

The MinIO SDK is blocking, so every call runs in a worker thread.
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass

from minio import Minio
from minio.error import MinioException

from dw_kernel.errors import InfrastructureError, NotFoundError


@dataclass
class MinioAttachmentStorage:
    """Implements ``dw_platform.application.ports.FeedbackAttachmentStoragePort``."""

    client: Minio
    bucket: str

    def _put_sync(self, key: str, data: bytes, content_type: str) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
        self.client.put_object(
            self.bucket, key, io.BytesIO(data), length=len(data), content_type=content_type
        )

    def _get_sync(self, key: str) -> bytes:
        response = self.client.get_object(self.bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            await asyncio.to_thread(self._put_sync, key, data, content_type)
        except MinioException as exc:
            raise InfrastructureError(
                "attachment storage write failed", details={"key": key}
            ) from exc

    async def get(self, key: str) -> bytes:
        try:
            return await asyncio.to_thread(self._get_sync, key)
        except MinioException as exc:
            raise NotFoundError("attachment not found", details={"key": key}) from exc

    async def delete(self, key: str) -> None:
        # Best-effort by contract: this runs on the failure path of a write that
        # already aborted, and raising here would replace the real error with a
        # cleanup error.
        try:
            await asyncio.to_thread(self.client.remove_object, self.bucket, key)
        except MinioException as exc:
            raise InfrastructureError(
                "attachment storage delete failed", details={"key": key}
            ) from exc
