# FastAPI agentic application with Azure AI Foundry tracing
from fastapi import FastAPI, Request
import logging
import os

from azure.identity import DefaultAzureCredential
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import (
    SystemMessage,
    UserMessage,
)
from azure.core.settings import settings as azure_settings
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace


# Configure OpenTelemetry -> Application Insights
AI_CONN_STR = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
if AI_CONN_STR:
    configure_azure_monitor(
        connection_string=AI_CONN_STR,
    )

# Enable azure SDK tracing via OpenTelemetry
azure_settings.tracing_implementation = "opentelemetry"

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

app = FastAPI()

credential = DefaultAzureCredential()

FOUNDRY_ENDPOINT = os.getenv("FOUNDRY_ENDPOINT", "")
DEPLOYMENT_NAME = os.getenv(
    "FOUNDRY_DEPLOYMENT_NAME", "DeepSeek-V3-0324"
)


def get_inference_client():
    return ChatCompletionsClient(
        endpoint=FOUNDRY_ENDPOINT,
        credential=credential,
        credential_scopes=[
            "https://cognitiveservices.azure.com/.default"
        ],
    )


def call_foundry_agent(input_data):
    prompt = input_data.get("prompt", "")
    if not prompt:
        return {"error": "No prompt provided"}
    try:
        client = get_inference_client()
        response = client.complete(
            model=DEPLOYMENT_NAME,
            messages=[
                SystemMessage(
                    content="You are a helpful assistant."
                ),
                UserMessage(content=prompt),
            ],
            max_tokens=1024,
        )
        return {
            "result": response.choices[0].message.content
        }
    except Exception as e:
        logger.error(f"Foundry API call failed: {e}")
        return {"error": str(e)}


@app.get("/")
def root():
    logger.info("Root endpoint called.")
    return {"message": "Agentic API is running."}


@app.post("/agent")
async def agent_endpoint(request: Request):
    with tracer.start_as_current_span("agent_request"):
        data = await request.json()
        logger.info("Agent endpoint called.")
        result = call_foundry_agent(data)
        return result
