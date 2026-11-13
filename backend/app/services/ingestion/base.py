from abc import ABC, abstractmethod
from typing import Any, List, Dict
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class ProviderStatus(Enum):
    LIVE = "LIVE"
    AUTHENTICATED = "AUTHENTICATED"
    PUBLIC_VISUAL = "PUBLIC-VISUAL"
    STUB = "STUB"
    UNAVAILABLE = "UNAVAILABLE"

class BaseProvider(ABC):
    """
    Abstract Base Class for Data Ingestion Providers.
    Isolates external source dependencies from internal pipeline logic.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def status(self) -> ProviderStatus:
        pass

    async def execute(self) -> List[Dict[str, Any]]:
        """
        Executes the full fetch, parse, and validate flow.
        Gracefully handles errors to prevent halting the entire pipeline.
        """
        if self.status in [ProviderStatus.STUB, ProviderStatus.UNAVAILABLE]:
            logger.warning(f"[{self.name}] Provider is {self.status.value}. Skipping ingestion.")
            return []
            
        if self.status == ProviderStatus.AUTHENTICATED and not self.has_credentials():
            logger.warning(f"[{self.name}] Provider is AUTHENTICATED but lacks credentials. Skipping ingestion.")
            return []

        try:
            raw_data = await self.fetch_data()
            parsed_data = self.parse_data(raw_data)
            valid_data = self.validate_data(parsed_data)
            return valid_data
        except Exception as e:
            logger.error(f"[{self.name}] Ingestion failed: {e}")
            return []

    @abstractmethod
    async def fetch_data(self) -> Any:
        """Fetches raw data from the external source."""
        pass

    @abstractmethod
    def parse_data(self, raw_data: Any) -> List[Dict[str, Any]]:
        """Parses raw payload into intermediate dictionaries."""
        pass

    def validate_data(self, parsed_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validates bounds. Override in subclasses if custom logic is needed."""
        return parsed_data
        
    def has_credentials(self) -> bool:
        """Override in authenticated subclasses to check for API keys in the environment."""
        return True
