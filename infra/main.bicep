// Topology B — full demo.
// Creates: Log Analytics, Container Apps environment, 3 container apps
// (neuro-san [internal], nsflow [public], invoice-api [public]) and a Static Web App.
// ACR is expected to already exist and hold the image (see deploy/AZURE_DEPLOY.md),
// because the container apps must be able to pull it at create time.

@description('Region for Container Apps + ACR. Co-located with Azure OpenAI.')
param location string = 'swedencentral'

@description('Static Web Apps is not offered in swedencentral; use a supported region.')
param swaLocation string = 'westeurope'

@description('Short prefix for resource names.')
param namePrefix string = 'invoice'

@description('Existing Azure Container Registry name (login server = <name>.azurecr.io).')
param acrName string

@description('Image repository:tag already pushed to the ACR.')
param imageTag string = 'invoice-app:latest'

@description('Existing Azure OpenAI endpoint, e.g. https://<res>.openai.azure.com/ or the cognitiveservices host.')
param azureOpenAiEndpoint string

@secure()
@description('Azure OpenAI API key.')
param azureOpenAiApiKey string

@description('Azure OpenAI deployment name, e.g. gpt-5.5.')
param azureOpenAiDeployment string

@description('Azure OpenAI API version, e.g. 2025-03-01-preview.')
param openAiApiVersion string = '2025-03-01-preview'

var acrLoginServer = '${acrName}.azurecr.io'
var image = '${acrLoginServer}/${imageTag}'

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: acrName
}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${namePrefix}-logs'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${namePrefix}-cae'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

// Shared ACR pull secret (admin creds) + Azure OpenAI secrets, applied per app.
var registryConfig = [
  {
    server: acrLoginServer
    username: acr.listCredentials().username
    passwordSecretRef: 'acr-password'
  }
]
var registrySecret = {
  name: 'acr-password'
  value: acr.listCredentials().passwords[0].value
}
var openAiSecret = {
  name: 'azure-openai-key'
  value: azureOpenAiApiKey
}
var openAiEnv = [
  { name: 'AZURE_OPENAI_ENDPOINT', value: azureOpenAiEndpoint }
  { name: 'AZURE_OPENAI_API_KEY', secretRef: 'azure-openai-key' }
  { name: 'AZURE_OPENAI_DEPLOYMENT_NAME', value: azureOpenAiDeployment }
  { name: 'OPENAI_API_VERSION', value: openAiApiVersion }
]

resource neuroSan 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-neuro-san'
  location: location
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      // Internal ingress: reachable only by other apps in the environment.
      ingress: { external: false, targetPort: 8080, transport: 'http' }
      registries: registryConfig
      secrets: [registrySecret, openAiSecret]
    }
    template: {
      containers: [
        {
          name: 'neuro-san'
          image: image
          command: ['python']
          args: ['-m', 'neuro_san.service.main_loop.server_main_loop', '--http_port', '8080']
          resources: { cpu: json('1.0'), memory: '2Gi' }
          env: concat(openAiEnv, [
            { name: 'AGENT_MANIFEST_FILE', value: '/app/registries/manifest.hocon' }
            { name: 'AGENT_TOOL_PATH', value: '/app/coded_tools' }
            { name: 'AGENT_TOOLBOX_INFO_FILE', value: '/app/neuro_san_studio/toolbox/toolbox_info.hocon' }
          ])
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}

resource nsflow 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-nsflow'
  location: location
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: { external: true, targetPort: 4173, transport: 'auto' }
      registries: registryConfig
      secrets: [registrySecret, openAiSecret]
    }
    template: {
      containers: [
        {
          name: 'nsflow'
          image: image
          command: ['python']
          args: ['-m', 'uvicorn', 'nsflow.backend.main:app', '--host', '0.0.0.0', '--port', '4173']
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: concat(openAiEnv, [
            { name: 'NSFLOW_HOST', value: '0.0.0.0' }
            { name: 'NSFLOW_PORT', value: '4173' }
            { name: 'NEURO_SAN_SERVER_CONNECTION', value: 'http' }
            // Name-based service discovery inside the environment; ingress maps 80 -> 8080.
            { name: 'NEURO_SAN_SERVER_HOST', value: neuroSan.name }
            { name: 'NEURO_SAN_SERVER_HTTP_PORT', value: '80' }
          ])
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}

resource invoiceApi 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-api'
  location: location
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      // External ingress with WebSocket support (transport auto negotiates HTTP/1.1 upgrade).
      ingress: {
        external: true
        targetPort: 8095
        transport: 'auto'
        corsPolicy: { allowedOrigins: ['*'], allowedMethods: ['*'], allowedHeaders: ['*'] }
      }
      registries: registryConfig
      secrets: [registrySecret]
    }
    template: {
      containers: [
        {
          name: 'invoice-api'
          image: image
          command: ['python']
          args: ['-m', 'uvicorn', 'apps.invoice_to_pay.backend.app.main:app', '--host', '0.0.0.0', '--port', '8095']
          resources: { cpu: json('0.5'), memory: '1Gi' }
        }
      ]
      // In-memory seed data: keep a single replica so state is consistent.
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}

resource swa 'Microsoft.Web/staticSites@2023-12-01' = {
  name: '${namePrefix}-frontend'
  location: swaLocation
  sku: { name: 'Standard', tier: 'Standard' }
  properties: {}
}

output nsflowUrl string = 'https://${nsflow.properties.configuration.ingress.fqdn}'
output invoiceApiUrl string = 'https://${invoiceApi.properties.configuration.ingress.fqdn}'
output invoiceApiWss string = 'wss://${invoiceApi.properties.configuration.ingress.fqdn}'
output swaName string = swa.name
output swaDefaultHostname string = swa.properties.defaultHostname
