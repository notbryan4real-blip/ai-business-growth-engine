"""Provider contracts for local-business prospect discovery.

The discovery engine should support multiple providers so a single upstream
API outage does not stop prospecting. Provider implementations should return
normalized Prospect-compatible dictionaries and never persist credentials.
"""

from __future__ import annotations

from typing import Protocol


class LocalBusinessProvider(Protocol):
    def search(self, category: str, location: str, limit: int = 20) -> list[dict]:
        """Return normalized local-business records."""
        ...
