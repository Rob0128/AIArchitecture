# FastAPI agentic email application with Azure AI Foundry tracing
from fastapi import FastAPI, Request, BackgroundTasks
import logging
import os
import json

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


def process_email(email_id: str):
    """Fetch an email, classify it, dispatch to sub-agent."""
    with otel_tracer.start_as_current_span("process_email"):
        email = gmail_client.get_email(email_id)
        if not email:
            logger.error(
                f"Could not fetch email {email_id}"
            )
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
            f"Processing email from {sender}: {subject}"
        )

        # Step 1: Router classifies the email
        client = get_inference_client()
        category = router_agent.classify(
            client, DEPLOYMENT_NAME,
            subject, body, sender,
        )

        logger.info(f"Email classified as: {category}")

        # Step 2: Dispatch to sub-agent
        agent = SUB_AGENTS.get(
            category, SUB_AGENTS["general"]
        )
        result = agent.handle(
            client, DEPLOYMENT_NAME, gmail_client,
            email_id, subject, body, sender,
        )

        # Mark as read so next poll skips it
        gmail_client.mark_as_read(email_id)

        logger.info(
            f"Agent '{category}' result: "
            f"{json.dumps(result)[:200]}"
        )

        return result


@app.get("/")
def root():
    return {"message": "Agentic Email API is running."}


@app.post("/check-emails")
async def check_emails(
    background_tasks: BackgroundTasks,
):
    """Poll Gmail for unread emails and process them."""
    unread = gmail_client.get_unread_emails()
    for msg in unread:
        background_tasks.add_task(
            process_email, msg["id"]
        )
    return {
        "queued": len(unread),
        "message_ids": [m["id"] for m in unread],
    }


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
