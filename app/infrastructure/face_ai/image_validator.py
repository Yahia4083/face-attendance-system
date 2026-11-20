"""Image validation helpers for face enrollment."""

from pathlib import Path


class ImageValidator:
    """Validate image extension and size."""

    ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}
    MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024

    def validate(self, *, filename: str, image_bytes: bytes) -> None:
        extension = self._extract_extension(filename)
        if extension not in self.ALLOWED_EXTENSIONS:
            raise ValueError("Invalid image format. Allowed formats: jpg, jpeg, png")

        if len(image_bytes) == 0:
            raise ValueError(f"Invalid image file: {filename}")

        if len(image_bytes) > self.MAX_IMAGE_SIZE_BYTES:
            raise ValueError("Image file too large. Maximum allowed size is 5 MB")

    @staticmethod
    def _extract_extension(filename: str) -> str:
        suffix = Path(filename).suffix.lower().replace(".", "")
        return suffix
