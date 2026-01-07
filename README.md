# 1.Project Definition

Planner_AI is a calendar task scheduling system that supports users in organizing daily activities based on unstructured textual input. The project focuses on the transformation of freeform daily notes and action logs into a structured calendar representation that can be directly used for planning and time management.

The system applies natural language processing techniques to identify tasks within text, followed by automated classification, prioritization, and scheduling according to user-defined routines and constraints. Planner_AI is implemented as a cloud-native application and is intended to be deployed and evaluated in a Kubernetes-based environment.

# 2.Overall Description

Planner_AI provides an end-to-end workflow for converting informal user input into scheduled calendar events. Users submit daily notes or action logs written in natural language, which may contain task descriptions, reminders, deadlines, or loosely defined activities.

The input is processed by a task extraction component that detects actionable items. These tasks are subsequently categorized (for example, work or personal) and ordered based on priority and contextual information. A scheduling module then assigns tasks to available calendar time slots while respecting predefined routines, availability constraints, and existing calendar events. The resulting schedule is synchronized with the user’s calendar system and presented as a structured daily or weekly plan.

# 3. Architecturally significant use cases

## Use-case 1. – Submit Daily Note
The user enters daily notes through the web interface and submits them to the system. The web interface forwards the input to the backend API, where basic validation is performed. After successful validation, the notes are accepted for further processing and the user receives a confirmation.

![Use-case 1.](docs/SeqUC1.png)

#### plantuml code for revision

@startuml
actor User
participant "Web UI" as UI
participant "Backend API" as API

User -> UI : Enter daily notes
UI -> API : POST /notes
API -> API : Validate input
API --> UI : Notes accepted
UI --> User : Confirmation
@enduml


## Use-case 2. – Extract Tasks from Notes

The backend API forwards the submitted notes to the task extraction service. This service uses a language model to identify actionable tasks within the text. The extracted tasks are then normalized into a structured format before being returned to the backend for further processing.

![Use-case 2.](docs/SeqUC2.png)

#### plantuml code for revision

@startuml
participant "Backend API" as API
participant "Task Extraction Service" as Extractor
participant "LLM Engine" as LLM

API -> Extractor : Process notes
Extractor -> LLM : Extract tasks from text
LLM --> Extractor : List of tasks
Extractor -> Extractor : Normalize tasks
Extractor --> API : Extracted tasks
@enduml


## Use-case 3. – Classify and Prioritize Task

The backend requests task classification and prioritization from the classification service. User preferences are loaded to provide additional context. A language model is used to assist with task categorization and priority assignment, after which the enriched task data is returned to the backend.

![Use-case 3.](docs/SeqUC3.png)

#### plantuml code for revision

@startuml
participant "Backend API" as API
participant "Task Classification Service" as Classifier
participant "LLM Engine" as LLM
participant "User Preferences Store" as Prefs

API -> Classifier : Classify tasks
Classifier -> Prefs : Load preferences
Prefs --> Classifier : Preferences
Classifier -> LLM : Classify and rank tasks
LLM --> Classifier : Classified tasks
Classifier --> API : Tasks with priority
@enduml


## Use-case 4. – Schedule Tasks into Calendar

The backend invokes the scheduling service to assign tasks to calendar time slots. The scheduler loads predefined user routines and retrieves existing calendar events. Based on this information, it computes a feasible schedule that respects availability constraints and avoids conflicts, and returns the scheduled tasks.

![Use-case 4.](docs/SeqUC4.png)

#### plantuml code for revision

@startuml
participant "Backend API" as API
participant "Scheduling Service" as Scheduler
participant "Calendar Service" as Calendar
participant "Routine Store" as Routines

API -> Scheduler : Schedule tasks
Scheduler -> Routines : Load routines
Routines --> Scheduler : Time windows
Scheduler -> Calendar : Get existing events
Calendar --> Scheduler : Calendar events
Scheduler -> Scheduler : Compute schedule
Scheduler --> API : Scheduled tasks
@enduml


## Use-case 5. – Synchronize with External Calendar

The backend initiates synchronization of scheduled tasks through the calendar integration service. The integration service communicates with an external calendar API to create or update calendar events. After synchronization is completed, the result is reported back to the backend.

![Use-case 5.](docs/SeqUC5.png)

#### plantuml code for revision

@startuml
participant "Backend API" as API
participant "Calendar Integration Service" as Integration
participant "External Calendar API" as ExternalCalendar

API -> Integration : Sync scheduled tasks
Integration -> ExternalCalendar : Create / Update events
ExternalCalendar --> Integration : Confirmation
Integration --> API : Sync result
@enduml

# 4. Component Diagram

## Components

- Web UIWeb UI
User-facing interface for submitting notes and viewing scheduled tasks.

- Backend API
Central orchestration component that coordinates processing, scheduling, and integration.

- Task Extraction Service
Extracts actionable tasks from unstructured text input.

- Task Classification Service
Categorizes tasks and assigns priorities using user preferences and AI support.

- Scheduling Service
Assigns tasks to calendar time slots based on routines and availability.

- LLM Engine
Provides language understanding capabilities for extraction and classification.

- User Preferences Store
Stores user-specific settings and preferences.

- Routine Store
Stores predefined routines and availability windows.

- Calendar Integration Service
Handles communication with external calendar systems.

- External Calendar API
Third-party calendar service (e.g., Google Calendar).


## Component Interaction Overview:

The Web UI serves as the entry point for user input and communicates exclusively with the Backend API. The Backend API acts as the central coordination component and delegates specific responsibilities to specialized services. Task extraction and classification services use a shared LLM engine for natural language processing, while scheduling logic is handled deterministically by the scheduling service. External calendar systems are accessed exclusively through a dedicated integration component, ensuring clear separation of concerns.

![Class Diagram](docs/ClassDiag.png)

#### plantuml code for revision

@startuml
package "Planner_AI System" {

  [Web UI] --> [Backend API]

  [Backend API] --> [Task Extraction Service]
  [Backend API] --> [Task Classification Service]
  [Backend API] --> [Scheduling Service]
  [Backend API] --> [Calendar Integration Service]

  [Task Extraction Service] --> [LLM Engine]
  [Task Classification Service] --> [LLM Engine]

  [Task Classification Service] --> [User Preferences Store]
  [Scheduling Service] --> [Routine Store]

  [Scheduling Service] --> [Calendar Integration Service]
}

[Calendar Integration Service] --> [External Calendar API]

@enduml

# 5. Deployment diagram

## Deployment View

The Planner_AI system is deployed as a set of containerized services running inside a Kubernetes cluster. Users interact with the system through a web browser, which accesses the application via an ingress controller. The Web UI and Backend API are deployed as separate pods, enabling independent scaling and deployment.

AI-related functionality is deployed as dedicated services that communicate with an external LLM API. Scheduling and integration logic are isolated in their own pods to maintain separation of concerns. User preferences and routines are stored in persistent storage within the cluster. External calendar systems are accessed through a dedicated integration service.

![Class Diagram](docs/DeploymentDiag.png)

#### plantuml code for revision

@startuml
node "Client Device" {
  component "Web Browser"
}

node "Kubernetes Cluster" {

  node "Ingress Controller" {
    component "HTTP Ingress"
  }

  node "Web UI Pod" {
    component "Web UI"
  }

  node "Backend API Pod" {
    component "Backend API"
  }

  node "AI Services Pod" {
    component "Task Extraction Service"
    component "Task Classification Service"
  }

  node "Scheduling Pod" {
    component "Scheduling Service"
  }

  node "Integration Pod" {
    component "Calendar Integration Service"
  }

  database "Persistent Storage" {
    component "User Preferences Store"
    component "Routine Store"
  }
}

node "External Services" {
  component "External Calendar API"
  component "LLM API"
}

"Web Browser" --> "HTTP Ingress"
"HTTP Ingress" --> "Web UI"
"Web UI" --> "Backend API"

"Backend API" --> "Task Extraction Service"
"Backend API" --> "Task Classification Service"
"Backend API" --> "Scheduling Service"
"Backend API" --> "Calendar Integration Service"

"Task Extraction Service" --> "LLM API"
"Task Classification Service" --> "LLM API"

"Task Classification Service" --> "User Preferences Store"
"Scheduling Service" --> "Routine Store"

"Calendar Integration Service" --> "External Calendar API"
@enduml

# 6. Deployment Instructions

## Prerequisites

Before deploying the Planner_AI system, ensure you have the following tools installed:

### Required Tools
- **Local Kubernetes Cluster**: One of the following:
  - [Minikube](https://minikube.sigs.k8s.io/docs/start/) (recommended for development)
  - [Kind](https://kind.sigs.k8s.io/docs/user/quick-start/) (Kubernetes in Docker)
  - [k3d](https://k3d.io/) (k3s in Docker)
- **kubectl**: [Kubernetes command-line tool](https://kubernetes.io/docs/tasks/tools/)
- **Docker**: [Container platform](https://docs.docker.com/get-docker/)
- **Helm 3.x**: [Kubernetes package manager](https://helm.sh/docs/intro/install/)
- **Node.js 20+**: For building the frontend (optional if using pre-built images)

### Verify Installation
```bash
# Check kubectl is configured
kubectl cluster-info

# Check Docker is running
docker --version

# Check Helm is installed
helm version
```

## Quick Start

### 1. Start Local Kubernetes Cluster

**For Minikube (Recommended):**
```bash
# Start with sufficient resources
minikube start --cpus=4 --memory=8192
```

**For Kind:**
```bash
kind create cluster --name planner-ai
```

**For k3d:**
```bash
k3d cluster create planner-ai
```

### 2. Set Up Docker Environment

**For Minikube:**
```bash
# Configure shell to use minikube's Docker daemon
eval $(minikube docker-env)
```

**For Kind/k3d:**
```bash
# Docker commands will build locally and images will be imported
```

### 3. Create Kubernetes Secrets

Create required secrets for the application:

```bash
# Google OAuth credentials (for Google Calendar integration)
kubectl create secret generic google-oauth-secret \
  --from-literal=client_id='YOUR_GOOGLE_CLIENT_ID' \
  --from-literal=client_secret='YOUR_GOOGLE_CLIENT_SECRET' \
  --from-literal=encryption_key=$(openssl rand -base64 32)

# Note: Get Google OAuth credentials from https://console.cloud.google.com/
# Enable Google Calendar API and create OAuth 2.0 credentials
```

### 4. Build Docker Images

#### Backend Image
```bash
# Build the backend image
docker build -t planner-ai-backend:latest -f Dockerfile .

# For Kind: Load into cluster
kind load docker-image planner-ai-backend:latest --name planner-ai

# For k3d: Import into cluster
k3d image import planner-ai-backend:latest --cluster planner-ai
```

#### Frontend Image
```bash
cd planner-ui

# Build the frontend image
docker build -t planner-ui:latest .

# For Kind: Load into cluster
kind load docker-image planner-ui:latest --name planner-ai

# For k3d: Import into cluster
k3d image import planner-ui:latest --cluster planner-ai

cd ..
```

#### Price Simulator Image (for energy monitoring)
```bash
# Build the price simulator
docker build -t price-simulator:latest -f Dockerfile.price .

# For Kind/k3d: Load into cluster
kind load docker-image price-simulator:latest --name planner-ai
```

### 5. Deploy Infrastructure Services

Deploy core infrastructure components:

```bash
# Deploy PostgreSQL database
kubectl apply -f k8s/postgres.yaml

# Deploy Prometheus monitoring
kubectl create configmap prometheus-config \
  --from-file=observability/prometheus/prometheus.yml
kubectl apply -f observability/prometheus/prometheus.yml

# Deploy Grafana dashboards
kubectl apply -f observability/grafana/grafana.yaml

# Deploy Pushgateway (for CodeCarbon metrics)
kubectl apply -f k8s/pushgateway.yaml

# Wait for databases to be ready
kubectl wait --for=condition=ready pod -l app=postgres --timeout=300s
```

### 6. Deploy Kepler (Energy Monitoring)

Install Kepler for real-time energy consumption metrics:

```bash
# Add Kepler Helm repository
helm repo add kepler https://sustainable-computing-io.github.io/kepler-helm-chart
helm repo update

# Create namespace
kubectl create namespace kepler-system

# Install Kepler
helm install kepler kepler/kepler \
  --namespace kepler-system \
  --values k8s/kepler-values.yaml

# Verify installation
kubectl get pods -n kepler-system
```

For detailed Kepler setup and troubleshooting, see [docs/kepler-deployment.md](docs/kepler-deployment.md).

### 7. Deploy Application Services

Deploy the main application components:

```bash
# Deploy price simulator (energy signal source)
kubectl apply -f k8s/price-simulator.yaml

# Deploy backend API
kubectl apply -f k8s/backend-deployment.yaml
kubectl apply -f k8s/backend-service.yaml

# Deploy frontend UI
kubectl apply -f k8s/frontend.yaml

# Deploy ingress (optional)
kubectl apply -f k8s/ingress.yaml

# Wait for deployments
kubectl wait --for=condition=ready pod -l app=planner-ai-backend --timeout=300s
kubectl wait --for=condition=ready pod -l app=planner-ui --timeout=300s
```

### 8. Verify Deployment

Check that all services are running:

```bash
# Check all pods
kubectl get pods

# Expected output:
# NAME                                  READY   STATUS    RESTARTS   AGE
# grafana-...                          1/1     Running   0          5m
# kepler-...                           1/1     Running   0          5m
# planner-ai-backend-...               1/1     Running   0          2m
# planner-ui-...                       1/1     Running   0          2m
# postgres-...                         1/1     Running   0          5m
# price-simulator-...                  1/1     Running   0          3m
# prometheus-...                       1/1     Running   0          5m
# pushgateway-...                      1/1     Running   0          5m

# Check services
kubectl get svc

# Check logs if needed
kubectl logs -l app=planner-ai-backend
kubectl logs -l app=planner-ui
```

## Accessing the Application

### Option A: Port Forwarding (Recommended for Development)

```bash
# Forward frontend (main UI)
kubectl port-forward svc/planner-ui 3000:3000

# In another terminal, forward backend API
kubectl port-forward svc/planner-ai-backend 8000:8000

# In another terminal, forward Grafana (monitoring dashboards)
kubectl port-forward svc/grafana 3001:3000
```

Then access:
- **Main Application**: http://localhost:3000
- **Backend API Docs**: http://localhost:8000/docs
- **Grafana Dashboards**: http://localhost:3001 (admin/admin)
- **Calendar Page**: http://localhost:3000/calendar
- **Carbon Dashboard**: http://localhost:3000/carbon

### Option B: Ingress (Production-like Access)

1. **Enable Ingress Controller** (Minikube only):
   ```bash
   minikube addons enable ingress
   ```

2. **Get Ingress IP**:
   ```bash
   # For Minikube
   minikube ip
   
   # For Kind/k3d
   kubectl get ingress
   ```

3. **Configure Local DNS**:
   Add to `/etc/hosts` (replace with your ingress IP):
   ```
   192.168.49.2 planner-ai.local
   ```

4. **Start Tunnel** (Minikube only):
   ```bash
   minikube tunnel
   ```

5. **Access Application**:
   - **Main UI**: http://planner-ai.local
   - **Backend API**: http://planner-ai.local/api
   - **Grafana**: http://planner-ai.local/grafana

## Energy-Aware Features

Planner_AI includes energy-aware scheduling and carbon tracking:

### Features

1. **Dynamic Model Selection**
   - Automatically switches between large (qwen:14b) and small (llama3.2) LLM models
   - Based on real-time electricity price and solar availability
   - Configurable price threshold (default: €0.70/kWh)

2. **Durable Queue System**
   - PostgreSQL-backed task queue
   - Defers expensive operations during high-energy periods
   - Automatic retry with exponential backoff
   - Dead letter queue for failed tasks

3. **Real-Time Energy Monitoring**
   - Electricity Maps API integration for carbon intensity
   - Price simulator for testing (oscillates €0.40-€0.90)
   - Solar availability signals
   - Kepler for actual pod energy consumption

4. **Carbon Tracking**
   - CodeCarbon integration for CO2 emissions
   - Real-time metrics via Prometheus
   - Grafana dashboards for visualization

### Configuration

Energy features are configured via environment variables in `k8s/backend-deployment.yaml`:

```yaml
# Energy Policy
- name: ENERGY_STATUS_URL
  value: "http://price-simulator:8000"
- name: ENERGY_PRICE_THRESHOLD_EUR
  value: "0.70"
- name: ENERGY_FAIL_OPEN
  value: "true"

# LLM Model Tiers
- name: LLM_MODEL_LARGE
  value: "qwen:14b"
- name: LLM_MODEL_SMALL
  value: "llama3.2"

# Electricity Maps API (for real carbon data)
- name: ELECTRICITY_MAPS_API_KEY
  value: "your-api-key-here"
```

### Monitoring Setup

Access monitoring dashboards:

```bash
# Forward Prometheus
kubectl port-forward svc/prometheus 9090:9090

# Forward Grafana
kubectl port-forward svc/grafana 3001:3000
```

Visit:
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3001 (admin/admin)

Import the Planner_AI dashboard from `observability/grafana/dashboard_planner_ai.json`.

## Google Calendar Integration

### Setup OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable **Google Calendar API**
4. Create **OAuth 2.0 Client ID** credentials:
   - Application type: Web application
   - Authorized redirect URIs: `http://localhost:8000/auth/google/callback`
5. Save the **Client ID** and **Client Secret**

### Update Kubernetes Secret

```bash
# Delete old secret
kubectl delete secret google-oauth-secret

# Create new secret with your credentials
kubectl create secret generic google-oauth-secret \
  --from-literal=client_id='YOUR_CLIENT_ID.apps.googleusercontent.com' \
  --from-literal=client_secret='YOUR_CLIENT_SECRET' \
  --from-literal=encryption_key=$(openssl rand -base64 32)

# Restart backend to pick up new credentials
kubectl rollout restart deployment planner-ai-backend
```

### Connect Your Calendar

1. Open the application: http://localhost:3000/calendar
2. Click **"Connect Google Calendar"**
3. Authorize access in the popup window
4. Your calendar events will now sync automatically

## Troubleshooting

### Pods Not Starting

```bash
# Check pod status and events
kubectl get pods
kubectl describe pod <pod-name>

# Check logs
kubectl logs <pod-name>

# Common issues:
# - Image not found: Rebuild and reload image
# - Missing secrets: Create google-oauth-secret
# - Resource limits: Increase cluster resources
```

### Database Connection Issues

```bash
# Check PostgreSQL is running
kubectl get pods -l app=postgres

# Test database connection
kubectl exec -it <backend-pod> -- env | grep DATABASE_URL

# Check database logs
kubectl logs <postgres-pod>
```

### Google Calendar Not Syncing

```bash
# Check OAuth secret exists
kubectl get secret google-oauth-secret

# Check backend logs for OAuth errors
kubectl logs -l app=planner-ai-backend | grep -i "google\|oauth"

# Verify redirect URI matches Google Console
# Should be: http://localhost:8000/auth/google/callback
```

### Kepler Not Collecting Metrics

```bash
# Check Kepler pod
kubectl get pods -n kepler-system

# Check logs
kubectl logs -n kepler-system -l app.kubernetes.io/name=kepler

# Test metrics endpoint
kubectl port-forward -n kepler-system svc/kepler 9103:9103
curl http://localhost:9103/metrics | grep kepler_container
```

### Energy Monitoring Not Working

```bash
# Check price simulator
kubectl get pods -l app=price-simulator
kubectl logs -l app=price-simulator

# Test energy status endpoint
kubectl port-forward svc/price-simulator 8001:8000
curl http://localhost:8001/status

# Check backend can reach price simulator
kubectl exec -it <backend-pod> -- curl http://price-simulator:8000/status
```

## Rebuilding After Code Changes

### Backend Changes

```bash
# Rebuild backend image
eval $(minikube docker-env)  # For Minikube
docker build -t planner-ai-backend:latest -f Dockerfile .

# Restart deployment
kubectl rollout restart deployment planner-ai-backend

# Watch rollout status
kubectl rollout status deployment planner-ai-backend
```

### Frontend Changes

```bash
# Rebuild frontend image
cd planner-ui
eval $(minikube docker-env)  # For Minikube
docker build -t planner-ui:latest .
cd ..

# Restart deployment
kubectl rollout restart deployment planner-ui

# Watch rollout status
kubectl rollout status deployment planner-ui
```

### Update ConfigMaps

```bash
# Update Prometheus config
kubectl create configmap prometheus-config \
  --from-file=observability/prometheus/prometheus.yml \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart Prometheus
kubectl rollout restart deployment prometheus
```

## Clean Up

### Remove Application

```bash
# Delete all application resources
kubectl delete -f k8s/
kubectl delete -f observability/prometheus/
kubectl delete -f observability/grafana/

# Delete Kepler
helm uninstall kepler -n kepler-system
kubectl delete namespace kepler-system

# Delete secrets
kubectl delete secret google-oauth-secret
```

### Stop Cluster

```bash
# Minikube
minikube stop
minikube delete

# Kind
kind delete cluster --name planner-ai

# k3d
k3d cluster delete planner-ai
```

## Development Workflow

### Local Development with Ollama

For LLM functionality, install Ollama locally:

```bash
# Install Ollama (macOS)
brew install ollama

# Start Ollama service
ollama serve

# Pull required models
ollama pull llama3.2
ollama pull qwen:14b
```

The backend is configured to access Ollama at `host.minikube.internal:11434`.

### Live Reload

For active development:

1. **Backend**: Use Python virtual environment
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   
   # Run locally
   uvicorn src.api.main:app --reload
   ```

2. **Frontend**: Use Next.js dev server
   ```bash
   cd planner-ui
   npm install
   npm run dev
   ```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest test/test_llm_client.py

# Run with coverage
pytest --cov=src test/
```

## Architecture Overview

### Components

- **Frontend (Next.js + React)**: Modern web interface with calendar views
- **Backend (FastAPI)**: REST API with modular routers
- **PostgreSQL**: Durable queue and credentials storage
- **Ollama**: Local LLM inference (llama3.2, qwen:14b)
- **Prometheus**: Metrics collection and alerting
- **Grafana**: Dashboard visualization
- **Kepler**: Real-time energy consumption monitoring
- **Price Simulator**: Energy price/solar signal generator

### Data Flow

1. User submits notes via web UI
2. Backend extracts tasks using LLM (tier based on energy price)
3. Tasks classified and prioritized
4. Scheduler assigns to calendar slots
5. Syncs with Google Calendar
6. Energy metrics tracked via CodeCarbon + Kepler
7. Metrics visualized in Grafana

## Additional Resources

- **Energy-Aware Features**: See [docs/todo.md](docs/todo.md)
- **Kepler Setup**: See [docs/kepler-deployment.md](docs/kepler-deployment.md)
- **UI Documentation**: See [docs/todolist-ui.md](docs/todolist-ui.md)
- **Google Calendar API**: https://developers.google.com/calendar/api
- **CodeCarbon**: https://mlco2.github.io/codecarbon/
- **Kepler**: https://sustainable-computing.io/

# 7. Demo Video

[Download Demo Video](https://github.com/user-attachments/assets/2fe21836-48b3-4905-ba90-8178aa3389ba)
```
