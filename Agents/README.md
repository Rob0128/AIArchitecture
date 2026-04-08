# Instructions for running the Agentic API locally

## 1. Install dependencies
pip install -r requirements.txt

## 2. Set environment variables
Copy .env.example to .env and fill in the values, or set them manually:
- APPINSIGHTS_INSTRUMENTATIONKEY (from Azure Portal after Terraform apply)
- FOUNDRY_RESOURCE_ID (from Azure Portal or Terraform output)
- AZURE_REGION (default: UK West)

## 3. Run the API
uvicorn main:app --reload

## 4. Endpoints
- GET /         - Health check
- POST /agent   - Handles agent requests (payload: JSON)

## 5. Deployment
- Use the provided GitHub Actions workflow for CI/CD to Azure App Service.

## 6. Infrastructure
- Terraform code is in infra/ (run terraform init/apply there)

---

# TODO
- Implement the actual Foundry API call in main.py
- Add tests
- Secure the /agent endpoint as needed
