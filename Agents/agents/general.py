"""General sub-agent - summarizes and labels unclassified
emails."""
import json
import logging

from azure.ai.inference.models import (
    SystemMessage,
    UserMessage,
)

logger = logging.getLogger(__name__)

GENERAL_SYSTEM = """You are an email assistant.
Summarize this email in 1-2 sentences and suggest
appropriate labels.

Respond with JSON:
{"summary": "...", "labels": ["label1", "label2"]}"""


class GeneralAgent:
    def handle(
        self, client, model, graph_client,
        email_id, subject, body, sender,
    ):
        try:
            response = client.complete(
                model=model,
                messages=[
                    SystemMessage(content=GENERAL_SYSTEM),
                    UserMessage(
                        content=(
                            f"From: {sender}\n"
                            f"Subject: {subject}\n\n"
                            f"{body[:3000]}"
                        )
                    ),
                ],
                max_tokens=256,
            )
            text = response.choices[0].message.content
            result = json.loads(text)
            return {
                "action": "general_processed",
                "data": result,
            }
        except Exception as e:
            logger.error(f"General agent failed: {e}")
            return {
                "action": "general_error",
                "error": str(e),
            }
