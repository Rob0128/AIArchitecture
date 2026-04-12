"""Meeting sub-agent - extracts meeting details and drafts
an acknowledgement reply."""
import json
import logging

from azure.ai.inference.models import (
    SystemMessage,
    UserMessage,
)

logger = logging.getLogger(__name__)

MEETING_SYSTEM = """You are a meeting scheduling assistant.
Extract these fields from the email:
- proposed_date
- proposed_time
- duration
- location_or_link
- organizer

Then draft a short professional reply acknowledging
the meeting request.

Respond with JSON:
{"extracted": {fields}, "reply_draft": "..."}"""


class MeetingAgent:
    def handle(
        self, client, model, graph_client,
        email_id, subject, body, sender,
    ):
        try:
            response = client.complete(
                model=model,
                messages=[
                    SystemMessage(content=MEETING_SYSTEM),
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
                "action": "meeting_processed",
                "data": result,
            }
        except Exception as e:
            logger.error(f"Meeting agent failed: {e}")
            return {
                "action": "meeting_error",
                "error": str(e),
            }
