"""Persistent Cloudinary storage for Django image fields."""

from pathlib import PurePosixPath
from urllib.request import urlopen

from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class CloudinaryMediaStorage(Storage):
    """Store image fields in Cloudinary while keeping local names in the database."""

    def _save(self, name, content):
        from cloudinary import uploader

        # Django's ImageField has already normalized and validated the name.
        # Keep its upload_to directory when forming the Cloudinary public ID.
        path = PurePosixPath(name)
        parent = "" if str(path.parent) == "." else f"{path.parent}/"
        public_id = f"{parent}{path.stem}-{self._new_file_suffix()}"
        if hasattr(content, "seek"):
            content.seek(0)
        result = uploader.upload(
            content,
            public_id=public_id,
            resource_type="image",
            overwrite=False,
            unique_filename=False,
        )
        extension = result.get("format") or path.suffix.lstrip(".")
        return f"{result['public_id']}.{extension}" if extension else result["public_id"]

    @staticmethod
    def _new_file_suffix():
        import uuid

        return uuid.uuid4().hex

    def _open(self, name, mode="rb"):
        if mode not in ("rb", "r"):
            raise ValueError("Cloudinary media files are read-only through this storage.")
        with urlopen(self.url(name), timeout=20) as response:
            return ContentFile(response.read(), name=name)

    def _public_id_and_format(self, name):
        path = PurePosixPath(name)
        return str(path.with_suffix("")), path.suffix.lstrip(".") or None

    def delete(self, name):
        from cloudinary import uploader

        public_id, _format = self._public_id_and_format(name)
        uploader.destroy(public_id, resource_type="image", invalidate=True)

    def exists(self, name):
        # _save always adds a random suffix, so a new upload cannot collide.
        return False

    def url(self, name):
        from cloudinary.utils import cloudinary_url

        public_id, image_format = self._public_id_and_format(name)
        url, _options = cloudinary_url(
            public_id,
            format=image_format,
            resource_type="image",
            secure=True,
        )
        return url
