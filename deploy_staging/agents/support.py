"""Support sub-agent - handles customer support emails,
drafts a helpful reply."""
import json
import logging

from azure.ai.inference.models import (
    SystemMessage,
    UserMessage,
)

logger = logging.getLogger(__name__)

SUPPORT_SYSTEM = """You are a customer support assistant.
Analyze the support request and:
- Identify the issue category (billing, technical, general)
- Assess urgency (low, medium, high)
- Draft a helpful, empathetic reply

Respond with JSON:
{"issue_category": "...", "urgency": "...",
 "summary": "...", "reply_draft": "..."}"""


class SupportAgent:
    def handle(
        self, client, model, graph_client,
        email_id, subject, body, sender,
    ):
        try:
            response = client.complete(
                model=model,
                messages=[
                    SystemMessage(content=SUPPORT_SYSTEM),
                    UserMessage(
                        content=(
                            f"From: {sender}\n"
                            f"Subject: {subject}\n\n"
                            f"{body[:3000]}"
                        )
                    ),
                ],
                max_tokens=512,
            )
            text = response.choices[0].message.content
            result = json.loads(text)
            reply = result.get("reply_draft", "")
            if reply:
                graph_client.reply_to_email(
                    email_id, f"<p>{reply}</p>"
                )
            return {
                "action": "support_processed",
                "data": result,
            }
        except Exception as e:
            logger.error(f"Support agent failed: {e}")
            return {
                "action": "support_error",
                "error": str(e),
            }
