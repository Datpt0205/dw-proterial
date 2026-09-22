"""MinIO/S3 object storage adapter. The MinIO SDK is blocking, so calls run in
a worker thread. Keys are tenant-prefixed by the gateway."""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass

from minio import Minio
from minio.error import MinioException

from dw_kernel.errors import InfrastructureError, NotFoundError


@dataclass
class MinioObjectStorageAdapter:
    """Implements ``ObjectStoragePort``."""

    client: Minio
    bucket: str

    def _put_sync(self, key: str, data: bytes, content_type: str) -> str:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
        self.client.put_object(
            self.bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return f"s3://{self.bucket}/{key}"

    def _get_sync(self, key: str) -> bytes:
        response = self.client.get_object(self.bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    async def put_object(self, key: str, data: bytes, content_type: str) -> str:
        try:
            return await asyncio.to_thread(self._put_sync, key, data, content_type)
        except MinioException as exc:
            raise InfrastructureError("object storage write failed", details={"key": key}) from exc

    async def get_object(self, key: str) -> bytes:
        try:
            return await asyncio.to_thread(self._get_sync, key)
        except MinioException as exc:
            raise NotFoundError(
                "artifact not found in object storage", details={"key": key}
            ) from exc

    def _list_sync(self, prefix: str) -> list[str]:
        return [obj.object_name for obj in self.client.list_objects(self.bucket, prefix=prefix)]

    async def list_objects(self, prefix: str) -> list[str]:
        try:
            return await asyncio.to_thread(self._list_sync, prefix)
        except MinioException as exc:
            raise InfrastructureError(
                "object storage list failed", details={"prefix": prefix}
            ) from exc

    async def delete_object(self, key: str) -> None:
        try:
            await asyncio.to_thread(self.client.remove_object, self.bucket, key)
        except MinioException as exc:
            raise InfrastructureError("object storage delete failed", details={"key": key}) from exc
