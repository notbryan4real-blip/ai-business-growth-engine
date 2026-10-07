"""Provider-neutral prospect discovery contract."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from agents.prospecting.models import Prospect


@dataclass(frozen=True)
class SearchCriteria:
    category: str
    location: str
    limit: int = 20


class ProspectSource(ABC):
    @abstractmethod
    def search(self, criteria: SearchCriteria) -> list[Prospect]:
        """Return normalized prospects from an external source."""
        raise NotImplementedError
