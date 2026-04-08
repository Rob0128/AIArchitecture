# FastAPI skeleton for agentic application
from fastapi import FastAPI, Request
import logging
import os

from opencensus.ext.azure.log_exporter import AzureLogHandler
from opencensus.ext.azure.trace_exporter import AzureExporter
from opencensus.trace.samplers import ProbabilitySampler
from opencensus.trace.tracer import Tracer
from azure.identity import DefaultAzureCredential
from openai import AzureOpenAI


app = FastAPI()

credential = DefaultAzureCredential()

# Application Insights setup
APPINSIGHTS_KEY = os.getenv("APPINSIGHTS_INSTRUMENTATIONKEY")
if APPINSIGHTS_KEY:
    logger = logging.getLogger(__name__)
    logger.addHandler(
        AzureLogHandler(
            connection_string=(
                f'InstrumentationKey={APPINSIGHTS_KEY}'
            )
        )
    )
    tracer = Tracer(
        exporter=AzureExporter(
            connection_string=(
                f'InstrumentationKey={APPINSIGHTS_KEY}'
            )
        ),
        sampler=ProbabilitySampler(1.0),
    )
else:
    logger = logging.getLogger(__name__)
    tracer = Tracer()


FOUNDRY_ENDPOINT = os.getenv("FOUNDRY_ENDPOINT", "")
DEPLOYMENT_NAME = os.getenv(
    "FOUNDRY_DEPLOYMENT_NAME", "DeepSeek-V3-0324"
)


def get_openai_client():
    token = credential.get_token(
        "https://cognitiveservices.azure.com/.default"
    )
    client = AzureOpenAI(
        azure_endpoint=FOUNDRY_ENDPOINT,
        api_key=token.token,
        api_version="2024-12-01-preview",
    )
    return client


def call_foundry_agent(input_data):
    prompt = input_data.get("prompt", "")
    if not prompt:
        return {"error": "No prompt provided"}
    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant.",
                },
                {"role": "user", "content": prompt},
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
    with tracer.span(name="agent_request"):
        data = await request.json()
        logger.info(
            "Agent endpoint called.",
            extra={"custom_dimensions": data}
        )
        result = call_foundry_agent(data)
        return result
