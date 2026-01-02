from __future__ import annotations
from abc import ABC, abstractmethod

class LLMProvider(ABC):
    @abstractmethod
    def generate(self, *, system: str, user: str) -> str:
        """
        Must return the model output as TEXT (we'll parse/validate JSON in LLMClient).
        """
        raise NotImplementedError
