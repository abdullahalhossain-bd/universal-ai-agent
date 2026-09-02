import os
import shutil


class LocalObjectStorage:

    def __init__(self, base_path: str):

        self.base_path = base_path

        os.makedirs(
            base_path,
            exist_ok=True,
        )

    async def upload(
        self,
        file,
        key,
    ):

        full_path = os.path.join(
            self.base_path,
            key,
        )

        os.makedirs(
            os.path.dirname(full_path),
            exist_ok=True,
        )

        with open(full_path, "wb") as f:

            shutil.copyfileobj(
                file,
                f,
            )

        return key

    async def delete(
        self,
        key,
    ):

        full_path = os.path.join(
            self.base_path,
            key,
        )

        if os.path.exists(full_path):
            os.remove(full_path)

    async def get_url(
        self,
        key,
    ):

        return f"/local-media/{key}"

    async def read(
        self,
        key,
    ) -> bytes:

        full_path = os.path.join(
            self.base_path,
            key,
        )

        with open(full_path, "rb") as f:
            return f.read()