"""Router agent - classifies emails into categories."""
import json
import logging

from azure.ai.inference.models import (
    SystemMessage,
    UserMessage,
)

logger = logging.getLogger(__name__)

ROUTER_SYSTEM = """You are an email classifier.
Given an email's subject, body, and sender, classify it
into exactly ONE of these categories: {categories}

Respond with ONLY a JSON object: {{"category": "<name>"}}
No other text."""


class RouterAgent:
    def __init__(self, categories):
        self.categories = categories

    def classify(
        self, client, model, subject, body, sender
    ):
        prompt = (
            f"From: {sender}\n"
            f"Subject: {subject}\n\n"
            f"Body:\n{body[:2000]}"
        )
        try:
            response = client.complete(
                model=model,
                messages=[
                    SystemMessage(
                        content=ROUTER_SYSTEM.format(
                            categories=", ".join(
                                self.categories
                            )
                        )
                    ),
                    UserMessage(content=prompt),
                ],
                max_tokens=50,
            )
            text = response.choices[0].message.content
            result = json.loads(text)
            category = result.get("category", "general")
            if category not in self.categories:
                return "general"
            return category
        except Exception as e:
            logger.error(
                f"Router classification failed: {e}"
            )
            return "general"
