"""Invoice sub-agent - extracts invoice details and drafts
a confirmation reply."""
import json
import logging

from azure.ai.inference.models import (
    SystemMessage,
    UserMessage,
)

logger = logging.getLogger(__name__)

INVOICE_SYSTEM = """You are an invoice processing assistant.
Extract these fields from the email:
- invoice_number
- amount
- currency
- due_date
- vendor_name

Then draft a short professional reply confirming receipt.

Respond with JSON:
{"extracted": {fields}, "reply_draft": "..."}"""


class InvoiceAgent:
    def handle(
        self, client, model, graph_client,
        email_id, subject, body, sender,
    ):
        try:
            response = client.complete(
                model=model,
                messages=[
                    SystemMessage(content=INVOICE_SYSTEM),
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
                "action": "invoice_processed",
                "data": result,
            }
        except Exception as e:
            logger.error(f"Invoice agent failed: {e}")
            return {
                "action": "invoice_error",
                "error": str(e),
            }
