# Terraform configuration for Azure resources for the agentic application

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 3.0.0"
    }
  }
  required_version = ">= 1.1.0"

  backend "azurerm" {
    resource_group_name  = "AITest"
    storage_account_name = "agentictfstate"
    container_name       = "tfstate"
    key                  = "agentic.tfstate"
  }
}

provider "azurerm" {
  features {}
  subscription_id = "1ca634f9-21d0-436e-8620-086ad4a697d4"
}

variable "location" {
  default = "UK West"
}

variable "resource_group_name" {
  default = "AITest"
}

variable "foundry_resource_name" {
  default = "AIfoundrytest3332"
}

# Reference existing Foundry resource
data "azurerm_resource_group" "foundry_rg" {
  name = var.resource_group_name
}

variable "foundry_resource_type" {
  description = "The Azure resource type for the Foundry instance"
  default     = "Microsoft.MachineLearningServices/workspaces"
}

locals {
  foundry_resource_id = "/subscriptions/1ca634f9-21d0-436e-8620-086ad4a697d4/resourceGroups/${var.resource_group_name}/providers/${var.foundry_resource_type}/${var.foundry_resource_name}"
}

# Create Application Insights
resource "azurerm_application_insights" "appinsights" {
  name                = "agentic-appinsights"
  location            = var.location
  resource_group_name = var.resource_group_name
  application_type    = "web"
}

# App Service Plan (cheapest Linux tier)
resource "azurerm_service_plan" "agentic_plan" {
  name                = "agentic-appservice-plan"
  location            = var.location
  resource_group_name = var.resource_group_name
  os_type             = "Linux"
  sku_name            = "B1"
}

# Virtual Network
resource "azurerm_virtual_network" "agentic_vnet" {
  name                = "agentic-vnet"
  address_space       = ["10.0.0.0/16"]
  location            = var.location
  resource_group_name = var.resource_group_name
}

resource "azurerm_subnet" "agentic_subnet" {
  name                 = "agentic-subnet"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.agentic_vnet.name
  address_prefixes     = ["10.0.1.0/24"]
}

# Linux Web App (Python 3.11)
resource "azurerm_linux_web_app" "agentic_app" {
  name                = "agentic-appservice"
  location            = var.location
  resource_group_name = var.resource_group_name
  service_plan_id     = azurerm_service_plan.agentic_plan.id
  app_settings = {
    "APPINSIGHTS_INSTRUMENTATIONKEY" = azurerm_application_insights.appinsights.instrumentation_key
    "FOUNDRY_RESOURCE_ID"             = local.foundry_resource_id
    "AZURE_REGION"                    = var.location
    "SCM_DO_BUILD_DURING_DEPLOYMENT"  = "true"
    "ENABLE_ORYX_BUILD"                = "true"
  }
  site_config {
    app_command_line = "gunicorn -w 2 -k uvicorn.workers.UvicornWorker main:app"
    application_stack {
      python_version = "3.11"
    }
  }
}

# Private Endpoint for App Service
resource "azurerm_private_endpoint" "agentic_pe" {
  name                = "agentic-appservice-pe"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = azurerm_subnet.agentic_subnet.id
  private_service_connection {
    name                           = "agentic-appservice-psc"
    private_connection_resource_id = azurerm_linux_web_app.agentic_app.id
    subresource_names              = ["sites"]
    is_manual_connection           = false
  }
}

# NSG for subnet
resource "azurerm_network_security_group" "agentic_nsg" {
  name                = "agentic-nsg"
  location            = var.location
  resource_group_name = var.resource_group_name
}

resource "azurerm_subnet_network_security_group_association" "agentic_nsg_assoc" {
  subnet_id                 = azurerm_subnet.agentic_subnet.id
  network_security_group_id = azurerm_network_security_group.agentic_nsg.id
}

output "app_service_default_hostname" {
  value = azurerm_linux_web_app.agentic_app.default_hostname
}

output "app_insights_instrumentation_key" {
  value     = azurerm_application_insights.appinsights.instrumentation_key
  sensitive = true
}

output "foundry_resource_id" {
  value = local.foundry_resource_id
}
