# Azure deployment — Topology B (full demo)

Deploys the invoice-to-pay stack to Azure:

| Component | Azure resource | Ingress | Port |
|-----------|----------------|---------|------|
| Invoice React frontend | Static Web App (`westeurope`) | public | — |
| Invoice FastAPI backend | Container App `invoice-api` | public (+ WebSocket) | 8095 |
| NSFlow UI | Container App `invoice-nsflow` | public | 4173 |
| Neuro-SAN agent server | Container App `invoice-neuro-san` | internal only | 8080 |

All three Python services run the **same image** (`deploy/app.Dockerfile`) with different start commands. Azure OpenAI (existing, Sweden Central) is reused.

> **Region note:** Static Web Apps is not offered in `swedencentral`, so the SWA goes to `westeurope`; everything else stays in `swedencentral` next to Azure OpenAI.

> **Bicep is unvalidated in this environment** — run `az bicep build -f infra/main.bicep` first to catch syntax issues before deploying.

## Prerequisites

```bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"
az extension add --name containerapp --upgrade
```

## 1. Resource group + ACR, then build the image

```bash
RG=rg-invoice-demo
LOC=swedencentral
ACR=invoiceacr$RANDOM          # must be globally unique, lowercase

az group create -n $RG -l $LOC

az acr create -n $ACR -g $RG --sku Basic --admin-enabled true

# Build the multi-service image in ACR (no local Docker needed)
az acr build -r $ACR -t invoice-app:latest -f deploy/app.Dockerfile .
```

## 2. Deploy environment + container apps + SWA (Bicep)

```bash
az bicep build -f infra/main.bicep        # validate

az deployment group create \
  -g $RG \
  -f infra/main.bicep \
  -p acrName=$ACR \
  -p azureOpenAiEndpoint="https://54138-molqqca8-swedencentral.cognitiveservices.azure.com/" \
  -p azureOpenAiApiKey="<AZURE_OPENAI_API_KEY>" \
  -p azureOpenAiDeployment="gpt-5.5" \
  -p openAiApiVersion="2025-03-01-preview"
```

Capture the outputs:

```bash
az deployment group show -g $RG -n main --query properties.outputs
# -> invoiceApiUrl (https), invoiceApiWss (wss), nsflowUrl, swaName, swaDefaultHostname
```

## 3. Wire the frontend to the backend and deploy it

The Vite app reads `VITE_API_BASE` / `VITE_WS_BASE` **at build time**, so they must point at the deployed backend.

Get the SWA deployment token and set GitHub repo secrets, then let the workflow build+deploy:

```bash
SWA_TOKEN=$(az staticwebapp secrets list -n invoice-frontend -g $RG --query properties.apiKey -o tsv)

# In the GitHub repo (Anjin-san-ai/Invoice_policy_app_insurance) -> Settings -> Secrets:
#   AZURE_STATIC_WEB_APPS_API_TOKEN = $SWA_TOKEN
#   VITE_API_BASE = <invoiceApiUrl>      e.g. https://invoice-api.<hash>.swedencentral.azurecontainerapps.io
#   VITE_WS_BASE  = <invoiceApiWss>      e.g. wss://invoice-api.<hash>.swedencentral.azurecontainerapps.io
```

Push to `main` (or run the **Deploy invoice frontend to Azure Static Web Apps** workflow manually). `.github/workflows/azure-swa.yml` builds `apps/invoice_to_pay/frontend` and uploads `dist/`.

## 4. Verify

```bash
curl -s <invoiceApiUrl>/api/health
curl -s <invoiceApiUrl>/api/invoices/INVREC-000001 | head -c 200
open https://<swaDefaultHostname>       # dashboard + live WebSocket stream
open <nsflowUrl>                          # select apps/invoice_to_pay, chat with the network
```

## Notes & gotchas

- **Secrets:** the Azure OpenAI key is stored as a Container App secret. For production use a Key Vault reference instead of passing the key on the CLI, and rotate any key that has been shared.
- **CORS:** `invoice-api` allows all origins for the demo. Lock this to the SWA hostname for production.
- **State is in-memory** (seed data regenerated per replica). Apps are pinned to `minReplicas=1 / maxReplicas=1` so the dashboard stays consistent. Add a database before scaling out.
- **NSFlow → Neuro-SAN** uses in-environment name-based discovery (`NEURO_SAN_SERVER_HOST=invoice-neuro-san`, port `80`); Neuro-SAN has no public ingress.
- **ACR auth** uses admin credentials for simplicity. For production switch the container apps to a managed identity with the `AcrPull` role.
- **NSFlow `--reload`:** the container command runs uvicorn **without** `--reload`, avoiding the watch-loop that breaks `ns run` on a local checkout.
