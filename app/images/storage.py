class ObjectStorage:

    async def upload(
        self,
        file,
        key,
    ):
        raise NotImplementedError

    async def delete(
        self,
        key,
    ):
        raise NotImplementedError

    async def get_url(
        self,
        key,
    ):
        raise NotImplementedError

    async def read(
        self,
        key,
    ) -> bytes:
        raise NotImplementedError


_storage: "ObjectStorage | None" = None


def get_object_storage() -> "ObjectStorage":
    """
    Return the process-wide object storage backend for uploaded
    chat images.

    Backend is chosen by `settings.storage_backend`:
      - "local" (default): `LocalObjectStorage`, rooted at
        `settings.image_storage_path`. Fine for a single-box
        `docker compose` deployment with a persistent volume.
      - "s3": `S3ObjectStorage`, works with AWS S3 or any
        S3-compatible service (R2, Spaces, B2, MinIO). Required
        once you run more than one API/worker replica, or deploy
        to a platform without a persistent attached disk.

    Callers (the upload route, `VisionService`) only ever depend on
    this factory + the abstract interface above, never on a
    concrete backend class directly.
    """

    global _storage

    if _storage is not None:
        return _storage

    from app.core.config import settings

    if settings.storage_backend == "s3":

        from app.images.s3_storage import S3ObjectStorage

        if not settings.s3_bucket:
            raise RuntimeError(
                "STORAGE_BACKEND=s3 requires S3_BUCKET to be set."
            )

        _storage = S3ObjectStorage(
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            public_base_url=settings.s3_public_base_url,
        )

    else:

        from app.images.local_storage import LocalObjectStorage

        _storage = LocalObjectStorage(
            base_path=settings.image_storage_path,
        )

    return _storage