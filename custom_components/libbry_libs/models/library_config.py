from typing import Self


class LibraryConfig:
    def __init__(self, json_data: dict[str, any]):
        self.name = json_data["name"]
        self.branch_id = json_data.get("branchId", "")
        self.url = json_data["url"]

    @staticmethod
    def from_json(data: dict[str, dict[str, any]]) -> dict[str, Self]:
        return {k: LibraryConfig(v) for k, v in data.items()}

    @staticmethod
    def from_json_by_country(
        data: dict[str, dict[str, dict[str, any]]],
    ) -> dict[str, dict[str, Self]]:
        return {country: LibraryConfig.from_json(libraries) for country, libraries in data.items()}
