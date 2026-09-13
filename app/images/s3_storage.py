"""
S3-compatible object storage backend for uploaded chat images.

Works with AWS S3 as well as any S3-compatible service (Cloudflare
R2, Backblaze B2, MinIO, DigitalOcean Spaces) by pointing
`settings.s3_endpoint_url` at the provider's endpoint.

This exists because `LocalObjectStorage` writes to the container's
local filesystem, which is fine for a single-box `docker compose`
deployment but breaks the moment you run more than one API/worker
replica (each has its own disk) or deploy to a platform with an
ephemeral filesystem (Railway, Render, Fly, most container PaaS).
Production deployments with more than one replica, or without a
persistent attached volume, should set `STORAGE_BACKEND=s3`.

Uses boto3's sync client wrapped in `asyncio.to_thread` rather than
an async S3 client (aiobotocore) to avoid pinning a second, often
version-fragile, botocore dependency tree — chat image uploads are
low-frequency enough (one HTTP round trip per image) that the thread
hop cost is negligible.
"""

from __future__ import annotations

import asyncio
import io


class S3ObjectStorage:

    def __init__(
        self,
        bucket: str,
        region: str | None = None,
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        public_base_url: str | None = None,
    ):
        import boto3

        self.bucket = bucket

        # public_base_url lets you front the bucket with a CDN
        # (CloudFront, R2's public bucket URL, etc.) instead of
        # generating a raw S3 URL for every image.
        self.public_base_url = (
            public_base_url.rstrip("/")
            if public_base_url
            else None
        )

        self._client = boto3.client(
            "s3",
            region_name=region or None,
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key_id or None,
            aws_secret_access_key=secret_access_key or None,
        )

    async def upload(self, file, key):

        def _put():
            data = file.read() if hasattr(file, "read") else file
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
            )

        await asyncio.to_thread(_put)

        return key

    async def delete(self, key):

        def _delete():
            self._client.delete_object(
                Bucket=self.bucket,
                Key=key,
            )

        await asyncio.to_thread(_delete)

    async def get_url(self, key):

        if self.public_base_url:
            return f"{self.public_base_url}/{key}"

        def _presign():
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=604800,  # 7 days — matches typical chat-history retention UX
            )

        return await asyncio.to_thread(_presign)

    async def read(self, key) -> bytes:

        def _get():
            obj = self._client.get_object(
                Bucket=self.bucket,
                Key=key,
            )
            return obj["Body"].read()

        return await asyncio.to_thread(_get)
