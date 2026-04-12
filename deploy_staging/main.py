# FastAPI agentic email application with Azure AI Foundry tracing
from fastapi import FastAPI, Request, BackgroundTasks
import logging
import os
import json
from datetime import datetime, timezone
from collections import OrderedDict

from azure.identity import DefaultAzureCredential
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import (
    SystemMessage,
    UserMessage,
)
from azure.ai.inference.tracing import AIInferenceInstrumentor
from azure.core.settings import settings as azure_settings
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace

from gmail_client import GmailClient
from agents.router import RouterAgent
from agents.invoice import InvoiceAgent
from agents.meeting import MeetingAgent
from agents.support import SupportAgent
from agents.general import GeneralAgent


# Configure OpenTelemetry -> Application Insights
AI_CONN_STR = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
if AI_CONN_STR:
    configure_azure_monitor(
        connection_string=AI_CONN_STR,
    )

# Enable azure SDK tracing via OpenTelemetry
azure_settings.tracing_implementation = "opentelemetry"

# Instrument azure-ai-inference to emit GenAI spans
AIInferenceInstrumentor().instrument()

logger = logging.getLogger(__name__)
otel_tracer = trace.get_tracer(__name__)

app = FastAPI()

credential = DefaultAzureCredential()

FOUNDRY_ENDPOINT = os.getenv("FOUNDRY_ENDPOINT", "")
DEPLOYMENT_NAME = os.getenv(
    "FOUNDRY_DEPLOYMENT_NAME", "DeepSeek-V3-0324"
)
GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "")
GMAIL_REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN", "")


def get_inference_client():
    return ChatCompletionsClient(
        endpoint=FOUNDRY_ENDPOINT,
        credential=credential,
        credential_scopes=[
            "https://cognitiveservices.azure.com/.default"
        ],
    )


# Initialize Gmail client and sub-agents
gmail_client = GmailClient(
    client_id=GMAIL_CLIENT_ID,
    client_secret=GMAIL_CLIENT_SECRET,
    refresh_token=GMAIL_REFRESH_TOKEN,
)

SUB_AGENTS = {
    "invoice": InvoiceAgent(),
    "meeting": MeetingAgent(),
    "support": SupportAgent(),
    "general": GeneralAgent(),
}

router_agent = RouterAgent(list(SUB_AGENTS.keys()))

# In-memory store for email processing results (keeps last 100)
MAX_RESULTS = 100
email_results = OrderedDict()

REPLY_SYSTEM = (
    "You are a helpful email assistant replying on behalf "
    "of the user. Write a concise, professional reply to "
    "the email below. Use plain HTML for formatting. "
    "Do NOT include a subject line, only the reply body."
)


def _generate_reply(
    client, subject, body, sender, category, agent_result
):
    """Use the LLM to draft a contextual reply."""
    context = json.dumps(agent_result, default=str)[:500]
    response = client.complete(
        model=DEPLOYMENT_NAME,
        messages=[
            SystemMessage(content=REPLY_SYSTEM),
            UserMessage(
                content=(
                    f"From: {sender}\n"
                    f"Subject: {subject}\n"
                    f"Category: {category}\n"
                    f"Agent analysis: {context}\n\n"
                    f"Original email:\n{body[:3000]}"
                )
            ),
        ],
        max_tokens=512,
    )
    return response.choices[0].message.content


def process_email(email_id: str):
    """Fetch an email, classify it, dispatch to sub-agent."""
    with otel_tracer.start_as_current_span("process_email"):
        try:
            email = gmail_client.get_email(email_id)
            if not email:
                logger.error(
                    f"Could not fetch email {email_id}"
                )
                email_results[email_id] = {
                    "status": "error",
                    "error": "Could not fetch email",
                    "timestamp": datetime.now(
                        timezone.utc
                    ).isoformat(),
                }
                return

            subject = email.get("subject", "")
            body = (
                email.get("body", {}).get("content", "")
            )
            sender = (
                email.get("from", {})
                .get("emailAddress", {})
                .get("address", "")
            )

            logger.info(
                "Processing email from %s: %s",
                sender, subject,
            )

            # Step 1: Router classifies the email
            client = get_inference_client()
            category = router_agent.classify(
                client, DEPLOYMENT_NAME,
                subject, body, sender,
            )

            logger.info(
                "Email classified as: %s", category
            )

            # Step 2: Dispatch to sub-agent
            agent = SUB_AGENTS.get(
                category, SUB_AGENTS["general"]
            )
            result = agent.handle(
                client, DEPLOYMENT_NAME, gmail_client,
                email_id, subject, body, sender,
            )

            # Auto-reply to emails from specific senders
            if any(
                s in sender for s in AUTO_REPLY_SENDERS
            ):
                try:
                    reply_text = _generate_reply(
                        client, subject, body, sender,
                        category, result,
                    )
                    if not reply_text:
                        reply_text = "<p>Hello!</p>"
                except Exception as reply_err:
                    logger.warning(
                        "LLM reply generation failed "
                        "(%s), using fallback", reply_err,
                    )
                    reply_text = "<p>Hello!</p>"
                sent = gmail_client.reply_to_email(
                    email_id, reply_text,
                )
                result["auto_replied"] = sent
                logger.info(
                    "Auto-reply to %s: sent=%s",
                    sender, sent,
                )

            # Mark as read so next poll skips it
            gmail_client.mark_as_read(email_id)

            logger.info(
                "Agent '%s' result: %s",
                category, json.dumps(result)[:200],
            )

            # Store result for the /results endpoint
            email_results[email_id] = {
                "status": "processed",
                "category": category,
                "sender": sender,
                "subject": subject,
                "agent_result": result,
                "timestamp": datetime.now(
                    timezone.utc
                ).isoformat(),
            }

        except Exception as e:
            logger.exception(
                "Failed to process email %s", email_id
            )
            email_results[email_id] = {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now(
                    timezone.utc
                ).isoformat(),
            }

        # Trim to max size
        while len(email_results) > MAX_RESULTS:
            email_results.popitem(last=False)

        return email_results.get(email_id)


@app.get("/")
def root():
    return {"message": "Agentic Email API is running."}


@app.get("/results")
def get_results():
    """Return recent email processing results."""
    return {
        "count": len(email_results),
        "results": list(email_results.values()),
    }


# Senders that always get an auto-reply (read or unread)
AUTO_REPLY_SENDERS = [
    "robertjohnhill1@gmail.com",
]


@app.post("/check-emails")
async def check_emails(
    background_tasks: BackgroundTasks,
):
    """Poll Gmail for unread emails and process them.
    Also checks priority senders regardless of read status."""
    already_queued = set()

    # 1. Regular unread batch
    unread = gmail_client.get_unread_emails()
    for msg in unread:
        if msg["id"] not in email_results:
            background_tasks.add_task(
                process_email, msg["id"]
            )
            already_queued.add(msg["id"])

    # 2. Priority senders — pick up even if already read
    for sender_addr in AUTO_REPLY_SENDERS:
        priority_msgs = gmail_client.search_emails(
            f"from:{sender_addr} newer_than:7d",
            max_results=10,
        )
        for msg in priority_msgs:
            mid = msg["id"]
            if mid not in already_queued and mid not in email_results:
                background_tasks.add_task(
                    process_email, mid
                )
                already_queued.add(mid)

    return {
        "queued": len(already_queued),
        "message_ids": list(already_queued),
    }


@app.get("/debug-gmail")
async def debug_gmail():
    """Debug endpoint to test Gmail connection."""
    import requests as req
    try:
        token = gmail_client._get_token()
        # Search all emails from priority senders in last 7d
        search_results = {}
        for s in AUTO_REPLY_SENDERS:
            resp = req.get(
                "https://gmail.googleapis.com/gmail/v1"
                "/users/me/messages",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "q": f"from:{s} newer_than:7d",
                    "maxResults": 5,
                },
                timeout=30,
            )
            search_results[s] = resp.json()
        resp = req.get(
            "https://gmail.googleapis.com/gmail/v1"
            "/users/me/messages",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": "is:unread", "maxResults": 5},
            timeout=30,
        )
        return {
            "unread": resp.json(),
            "priority_sender_search": search_results,
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/process")
async def manual_process(request: Request):
    """Manually trigger processing for an email ID."""
    with otel_tracer.start_as_current_span(
        "manual_process"
    ):
        data = await request.json()
        email_id = data.get("email_id")
        if not email_id:
            return {"error": "email_id required"}
        result = process_email(email_id)
        return result or {"status": "processed"}


@app.post("/agent")
async def agent_endpoint(request: Request):
    """Direct prompt endpoint (kept for testing)."""
    with otel_tracer.start_as_current_span(
        "agent_request"
    ):
        data = await request.json()
        prompt = data.get("prompt", "")
        if not prompt:
            return {"error": "No prompt provided"}
        try:
            client = get_inference_client()
            response = client.complete(
                model=DEPLOYMENT_NAME,
                messages=[
                    SystemMessage(
                        content=(
                            "You are a helpful assistant."
                        )
                    ),
                    UserMessage(content=prompt),
                ],
                max_tokens=1024,
            )
            return {
                "result": (
                    response.choices[0].message.content
                )
            }
        except Exception as e:
            logger.error(f"Agent call failed: {e}")
            return {"error": str(e)}
