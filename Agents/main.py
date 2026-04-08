# FastAPI skeleton for agentic application with Azure Foundry and Application Insights
from fastapi import FastAPI, Request
import logging
import os

from opencensus.ext.azure.log_exporter import AzureLogHandler
from opencensus.ext.azure.trace_exporter import AzureExporter
from opencensus.trace.samplers import ProbabilitySampler
from opencensus.trace.tracer import Tracer
from azure.identity import DefaultAzureCredential


app = FastAPI()


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

# Placeholder for Foundry integration



# Helper to get Azure AD token using DefaultAzureCredential
def get_azure_ad_token(scope="https://management.azure.com/.default"):
    try:
        credential = DefaultAzureCredential()
        token = credential.get_token(scope)
        return token.token
    except Exception as e:
        logger.error(f"Failed to get Azure AD token: {e}")
        return None



def call_foundry_agent(input_data):
    # TODO: Implement call to Azure Foundry using SDK or REST API
    # Use os.getenv("FOUNDRY_RESOURCE_ID") and os.getenv("AZURE_REGION")
    # Example usage of get_azure_ad_token():
    token = get_azure_ad_token()
    if not token:
        return {"error": "Could not acquire Azure AD token"}
    # ...continue with Foundry API call using the token...
    return {"result": "Foundry response placeholder (token acquired)"}



@app.get("/")
def root():
    logger.info("Root endpoint called.")
    return {"message": "Agentic API is running."}



@app.post("/agent")
def agent_endpoint(request: Request):
    with tracer.span(name="agent_request"):
        data = request.json()
        logger.info(
            "Agent endpoint called.",
            extra={"custom_dimensions": data}
        )
        result = call_foundry_agent(data)
        return result
