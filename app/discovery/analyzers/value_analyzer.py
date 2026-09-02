import re
from decimal import Decimal


class ValueAnalyzer:

    URL_PATTERN = re.compile(
        r"^https?://",
        re.IGNORECASE,
    )

    IMAGE_PATTERN = re.compile(
        r"\.(jpg|jpeg|png|webp|gif)(\?.*)?$",
        re.IGNORECASE,
    )

    EMAIL_PATTERN = re.compile(
        r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    )

    def analyze(
        self,
        samples: list[str],
        data_type: str,
    ) -> set[str]:

        detected = set()

        if not samples:
            return detected

        if all(self._is_numeric(x) for x in samples):
            detected.add("numeric")

        if all(self.URL_PATTERN.match(x) for x in samples):
            detected.add("url")

        if any(self.IMAGE_PATTERN.search(x) for x in samples):
            detected.add("image_path")

        if all(self.EMAIL_PATTERN.match(x) for x in samples):
            detected.add("email")

        if any(
            len(x) > 80
            for x in samples
        ):
            detected.add("long_text")

        return detected

    @staticmethod
    def _is_numeric(value: str) -> bool:

        try:
            Decimal(value)
            return True
        except Exception:
            return False
