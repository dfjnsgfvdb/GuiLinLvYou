import json
from pathlib import Path


class EntityNormalizeService:
    def __init__(
        self,
        scenic_alias_path: str = "data/dictionaries/scenic_spot_alias.json",
        location_alias_path: str = "data/dictionaries/location_alias.json",
    ):
        self.scenic_alias = self._load_alias(scenic_alias_path)
        self.location_alias = self._load_alias(location_alias_path)
        self.scenic_reverse = self._build_reverse(self.scenic_alias)
        self.location_reverse = self._build_reverse(self.location_alias)

    def normalize_scenic_spots(self, values: list[str]) -> list[str]:
        return self._normalize(values, self.scenic_reverse)

    def normalize_locations(self, values: list[str]) -> list[str]:
        return self._normalize(values, self.location_reverse)

    def find_scenic_spots(self, text: str) -> list[str]:
        return self._find_alias(text, self.scenic_alias)

    def find_locations(self, text: str) -> list[str]:
        return self._find_alias(text, self.location_alias)

    @staticmethod
    def _load_alias(path: str) -> dict[str, list[str]]:
        file_path = Path(path)
        if not file_path.exists():
            return {}
        return json.loads(file_path.read_text(encoding="utf-8"))

    @staticmethod
    def _build_reverse(alias_map: dict[str, list[str]]) -> dict[str, str]:
        reverse = {}
        for standard, aliases in alias_map.items():
            reverse[standard] = standard
            for alias in aliases:
                reverse[alias] = standard
        return reverse

    @staticmethod
    def _normalize(values: list[str], reverse: dict[str, str]) -> list[str]:
        result = []
        for value in values:
            standard = reverse.get(value, value)
            if standard and standard not in result:
                result.append(standard)
        return result

    @staticmethod
    def _find_alias(text: str, alias_map: dict[str, list[str]]) -> list[str]:
        result = []
        for standard, aliases in alias_map.items():
            candidates = [standard, *aliases]
            if any(alias and alias in text for alias in candidates):
                result.append(standard)
        return result
