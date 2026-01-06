from __future__ import annotations
import json
from llm.providers.base import LLMProvider

class MockProvider(LLMProvider):
    def generate(self, *, system: str, user: str, model: str | None = None) -> str:
        """
        Returns dummy JSON responses based on the prompt content.
        """
        # Check if it's an extraction request (look for keywords in user prompt)
        if "Extract tasks" in user:
            return json.dumps({
                "tasks": [
                    {
                        "title": "Finish the quarterly report",
                        "description": "Complete the financial section for Sarah",
                        "estimated_duration_min": 60,
                        "deadline": None
                    },
                    {
                        "title": "Call mom",
                        "description": "Ask about Sunday dinner",
                        "estimated_duration_min": 15,
                        "deadline": None
                    },
                    {
                        "title": "Go for a run",
                        "description": "30 min jog in the park",
                        "estimated_duration_min": 30,
                        "deadline": None
                    }
                ]
            })
        
        # Check if it's a classification request
        if "Classify this task" in user:
            # Simple keyword matching for demo purposes
            lower_user = user.lower()
            category = "work"
            if "mom" in lower_user or "dinner" in lower_user:
                category = "personal"
            elif "run" in lower_user or "gym" in lower_user:
                category = "health"
            elif "read" in lower_user or "study" in lower_user:
                category = "learning"
                
            return json.dumps({
                "category": category,
                "priority": 3,
                "confidence": 0.95
            })

        # Default fallback
        return "{}"
