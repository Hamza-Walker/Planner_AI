# Energy-Aware AI Implementation - Progress Tracker

> Based on Session 1 & Session 2 class notes  
> Last updated: January 6, 2026

---

## Summary

This document tracks the implementation progress of carbon/cost-aware features from the 7th session exercises. The goal is to integrate energy-aware scheduling, dynamic model selection, and sustainability monitoring into the Planner_AI project.

---

## ✅ Completed Tasks

### 1. Energy Signal Infrastructure
- [x] **Price Simulator Service** (`10-redeploy-adapt/price_simulator.py`)
  - Electricity price oscillation (€0.40-€0.90, 3-minute cycles)
  - Solar availability toggle (10-minute intervals)
  - Prometheus metrics exposed (`/metrics`)
  - REST API endpoint (`/status`)
  - Manual solar toggle (`/switch_solar`)

- [x] **Energy Status Fetcher** (`src/energy/price_signal.py`)
  - `EnergyStatus` dataclass with price and solar fields
  - `fetch_energy_status()` function to query the price simulator
  - Error handling with graceful degradation

### 2. Energy Policy Layer
- [x] **Policy Implementation** (`src/energy/policy.py`)
  - `EnergyPolicy` class with configurable threshold (default €0.70)
  - `should_process_now()` - determines if workload should run immediately
  - `llm_tier()` - returns "large" or "small" based on energy status
  - Fail-open behavior when energy signal unavailable
  - Solar availability takes priority over price

### 3. Dynamic Model Selection (Strategy 1)
- [x] **Backend Integration** (`src/api/main.py`)
  - Energy-aware `/notes` endpoint
  - Queue-based deferred processing when energy is expensive
  - Background worker that polls energy status
  - `/queue` endpoint to check queue status and energy state

- [x] **LLM Client Tier Support** (`src/llm/llm_client.py`)
  - `model_tier` parameter ("small" / "large")
  - Environment variables for model names (`LLM_MODEL_SMALL`, `LLM_MODEL_LARGE`)

- [x] **Task Extractor/Classifier Integration**
  - `TaskExtractor.extract()` accepts `llm_tier` parameter
  - `TaskClassifier.classify()` accepts `llm_tier` parameter

### 4. Kubernetes Deployment Manifests
- [x] **Backend Deployment** (`k8s/backend-deployment.yaml`)
  - Environment variables for energy configuration
  - `ENERGY_STATUS_URL`, `ENERGY_PRICE_THRESHOLD_EUR`, `ENERGY_FAIL_OPEN`
  - Added Model Tier variables (`LLM_MODEL_LARGE`, `LLM_MODEL_SMALL`)

- [x] **Price Simulator Deployment** (`10-redeploy-adapt/k8s/power_simulator_deploy.yaml`)
  - Service exposed on port 8000
  - Prometheus scrape annotations
  - NoExecute tolerations for rescheduling

### 5. Multi-Node Scheduling (Strategy 2)
- [x] **Energy Scheduler Script** (`10-redeploy-adapt/energy_scheduler.sh`)
  - Monitors electricity prices and solar availability
  - Applies/removes taints based on conditions
  - Supports 3-node topology (solar, GPU, no-GPU)

- [x] **Helm Chart** (`10-redeploy-adapt/helm_scheduling/`)
  - `Chart.yaml` - chart metadata
  - `values.yaml` - configurable values
  - `templates/scheduler_config.yaml` - ConfigMap for scheduler script
  - `templates/scheduler_rbac.yaml` - RBAC for kubectl access
  - `templates/scheduler_sidecar_deploy.yaml` - scheduler deployment

### 6. Monitoring Infrastructure
- [x] **Prometheus Configuration** (`10-redeploy-adapt/k8s/prometheus.yaml`)
  - Scraping price simulator metrics
  - Scraping Kepler metrics
  - Push gateway integration for CodeCarbon

- [x] **Grafana Setup** (`10-redeploy-adapt/k8s/grafana.yaml`)
  - Dashboard visualization support

- [x] **CodeCarbon Integration** (`10-redeploy-adapt/backend.py`)
  - EmissionsTracker with Prometheus push gateway
  - SIGTERM handler for graceful metric push on eviction

- [x] **Kepler Configuration** (documented in README)
  - Helm installation instructions
  - Prometheus job configuration
  - RBAC for cluster-wide metrics

### 7. Main Planner_AI Backend Integration
- [x] **Integrate CodeCarbon into main backend** (`src/api/main.py`) ✅ *Completed Dec 31, 2025*
  - Added EmissionsTracker with Prometheus push gateway
  - Added SIGTERM/SIGINT handlers for graceful metric push on shutdown
  - Configurable via `PROMETHEUS_PUSH_URL` environment variable

### 8. Kubernetes Manifests for Main App
- [x] **Add tolerations to main backend deployment** (`k8s/backend-deployment.yaml`) ✅ *Completed Dec 31, 2025*
  - Added `energy-role` tolerations with `NoExecute` effect
  - Added Prometheus scrape annotations
  - Added `PROMETHEUS_PUSH_URL` environment variable

### 9. LLM Client Implementation
- [x] **Actual LLM API calls** (`src/llm/llm_client.py`) ✅ *Completed Jan 6, 2026*
  - Integrated with local Ollama provider (`src/llm/providers/ollama_provider.py`)
  - Configured for Minikube `host.minikube.internal` access
  - Implemented actual model switching (Tier Large: `qwen:14b`, Tier Small: `llama3.2`)
  - Added robust JSON sanitization (regex) for chatty models

### 10. Durable Queue Implementation
- [x] **PostgreSQL-backed Durable Queue** ✅ *Completed Jan 6, 2026*
  - PostgreSQL K8s manifests (`k8s/postgres.yaml`)
  - Deployment with PVC for persistent storage
  - Secret for credentials
  - ClusterIP Service for internal access
  - Database schema (`src/storage/schema.sql`)
  - `queue_items` table with status tracking
  - Retry logic with configurable max attempts
  - Dead letter queue for failed items
  - PostgreSQL functions for atomic dequeue operations
  - Stale item recovery for crashed workers
  - Database connection module (`src/storage/db.py`)
  - Async connection pool using `asyncpg`
  - Auto-initialization of schema on startup
  - Health check endpoint integration
  - Durable queue module (`src/storage/durable_queue.py`)
  - `DurableQueue` class with full queue operations
  - `enqueue()`, `dequeue()`, `complete()`, `fail()` methods
  - `recover_stale()` for crashed worker recovery
  - Dead letter queue management
  - Main API integration (`src/api/main.py`)
  - Feature flag `USE_DURABLE_QUEUE` for gradual rollout
  - Background worker for queue processing
  - Stale recovery worker
  - New endpoints: `/queue/items`, `/queue/dead`, `/queue/items/{id}/retry`, `/queue/purge`
  - Updated backend deployment (`k8s/backend-deployment.yaml`)
  - `DATABASE_URL` environment variable
  - `USE_DURABLE_QUEUE` feature flag

### 11. Electricity Maps API Integration
- [x] **Real Carbon Intensity Data** ✅ *Completed Jan 6, 2026*
  - Created `src/energy/electricity_maps.py` for API integration
  - Updated `src/energy/price_signal.py` to prioritize Electricity Maps
  - Carbon intensity to price mapping heuristic
  - Fallback to local simulator when API unavailable
  - API key configuration in K8s deployment

### 12. Frontend Queue & Energy Display
- [x] **Queue Status Component** ✅ *Completed Jan 6, 2026*
  - `QueueList.tsx` - displays pending, processing, completed items
  - Real-time updates every 3 seconds
  - `/queue/items` endpoint integration

- [x] **Energy Status Component Fixes** ✅ *Completed Jan 6, 2026*
  - Fixed `electricity_price_eur` field mapping
  - Added data source indicator (Electricity Maps / Simulator)
  - Queue polling reduced to 1 second for responsiveness

### 13. Carbon Page UI Improvements
- [x] **Enhanced Carbon Dashboard** ✅ *Completed Jan 7, 2026*
  - Redesigned layout with grid system and removed "Deployment Profile" redundancy
  - Integrated real-time Price, Solar, and Model status into a single "Live Status" card
  - Fixed `0.0` values for CO2 emissions and runtime by patching backend CodeCarbon logic
  - Added "Energy Savings" impact card
  - Improved styling consistency with Tailwind CSS

---

## ❌ Not Yet Implemented

### 14. Google Calendar Integration (High Priority)
- [x] **OAuth2 Authentication Setup** ✅ *Completed Jan 7, 2026*
  - Configure Google Cloud Console credentials (done)
  - Implement OAuth2 flow for user authorization (backend ready, frontend ready)
  - Secure token storage and refresh (`google_credentials` table + encryption)

- [x] **Calendar API Integration** ✅ *Completed Jan 7, 2026*
  - Fetch existing appointments from Google Calendar
  - Display appointments on calendar page
  - Create/update/delete events via API
  - Verified two-way sync (UI <-> Google Calendar)
  - Fixed Timezone Mismatch: Backend now fetches calendar timezone to ensure events appear at correct local time (e.g., 1PM vs 13:00 UTC).
  - Upgraded to React Big Calendar with Week/Month/Day/Agenda views
  - Range-based fetching: Frontend requests entire week, backend fetches all GCal events for that period

- [x] **Drag & Drop Scheduling** ✅ *Completed Jan 7, 2026*
  - Implemented drag-and-drop for task rescheduling using react-big-calendar DnD addon
  - Event resize support (drag start/end times)
  - Sync changes back to Google Calendar via `update_event()` method
  - Manual event creation via slot selection (click empty calendar space)
  - Backend endpoints: `POST /schedule/move`, `POST /tasks/create`
  - Automatic calendar refresh after modifications

### 15. AI Scheduling Intelligence (High Priority)
- [ ] **Context-Aware Scheduling**
  - Detect existing appointments on the given day
  - Identify school hours / working hours
  - Recognize recurring patterns (e.g., weekly meetings)

- [ ] **Conflict Detection & Resolution**
  - Check for overlapping time slots
  - Suggest alternative times for conflicts
  - Respect user-defined constraints (e.g., no meetings before 9am)

- [ ] **Enhanced Task Extraction**
  - Extract location from task descriptions
  - Detect urgency and priority automatically
  - Identify task dependencies
  - **[KNOWN ISSUE]**: LLM extraction works but scheduler defaults tasks without fixed_time to focus_start (09:00). This is by design (UserPreferences.focus_start default), not an extraction bug. Manual calendar creation bypasses this.

- [ ] **User Preferences Learning**
  - Learn preferred time slots for different task categories
  - Adapt to user's schedule patterns
  - Consider travel time between appointments

### 16. Dashboard UI Improvements (Medium Priority)
- [x] **Recent Tasks Component** ✅ *Completed Jan 7, 2026*
  - Better visual design for task cards
  - Show task status (pending, completed, scheduled)
  - Quick actions: Added Clear button to remove all recent tasks from dashboard
  - Real-time polling (10 second intervals)

- [x] **Queue Status Component** ✅ *Completed Jan 7, 2026*
  - Visual queue item cards with status indicators
  - Delete button (trash icon) for dead/failed items
  - Status badges (pending, processing, completed, failed, dead)
  - Attempt counter for retry tracking

- [ ] **Dashboard Layout**
  - Responsive design improvements
  - Better information hierarchy
  - Add summary statistics cards

- [ ] **Overall UI Polish**
  - Consistent styling across components
  - Loading states and error handling
  - Accessibility improvements

### 17. Calendar Page Enhancements (Medium Priority)
- [x] **Visual Calendar View** ✅ *Completed Jan 7, 2026*
  - Week/month/day/agenda view toggle (React Big Calendar)
  - Time slot visualization with 30-minute intervals
  - Color coding by task category
  - Event tooltips showing category
  - Drag-and-drop event movement and resizing

- [x] **Google Calendar Sync UI** ✅ *Completed Jan 7, 2026*
  - Connection status indicator (green badge with email when connected)
  - Disconnect button for OAuth logout
  - "Connect Google Calendar" button when not authenticated
  - Auto-sync on calendar view navigation
  - Error handling for API failures (graceful degradation)

### 18. Production-Ready Features (Lower Priority)
- [x] **Kepler Deployment for Main Cluster** ✅ *Completed Jan 7, 2026*
  - Installed Kepler via Helm in dedicated `kepler-system` namespace
  - Created `k8s/kepler-values.yaml` for configuration
  - Integrated with Prometheus for metrics scraping
  - Added comprehensive deployment guide (`docs/kepler-deployment.md`)
  - Verified metrics collection (container/node energy metrics)


- [x] **Grafana Dashboards**
  - Create custom dashboards for Planner_AI metrics
  - Combine energy metrics with task processing stats
  - Cost calculation panels (energy × price)

### 19. Documentation & Testing
- [x] **Update main README.md** ✅ *Completed Jan 7, 2026*
  - Documented all energy-aware features (dynamic model selection, queue system, carbon tracking)
  - Added comprehensive setup instructions for price simulator
  - Included Kepler/Helm/Prometheus/CodeCarbon setup with step-by-step guide
  - Detailed instructions for building Docker images (backend, frontend, price simulator)
  - Complete pod deployment workflow with verification steps
  - Added Google Calendar OAuth setup instructions
  - Troubleshooting section for common issues
  - Development workflow and local testing guide
 

- [ ] **Integration Tests**
  - Test energy policy behavior
  - Test queue behavior under different price conditions
  - Test model tier selection

### 20. Advanced Features (from Session 2)
- [x] **Horizontal Auto-scaling**
  - Scale replicas based on energy availability
  - Reduce capacity during expensive periods

- [x] **Batch Processing Support**
  - Queue non-urgent tasks for overnight processing
  - Schedule batch jobs during low-carbon periods

- [x] **Carbon Intensity API Integration**
  - Replace/supplement price simulator with real data
  - Integrate with Electricity Maps API
  - Region-aware scheduling

---

## 📋 Recommended Next Steps

1.  **High Priority - AI Context Improvements**
    - Add calendar context to task scheduling (don't book over existing meetings)
    - Implement conflict detection and smart suggestions
    - Learn user preferences for optimal scheduling

2.  **Medium Priority - Enhanced Energy Policy**
    - Fine-tune model selection thresholds
    - Add "medium" tier for balanced scenarios
    - Implement adaptive learning based on actual performance

3.  **Low Priority - UI Polish**
    - Dashboard layout refinements
    - Add summary statistics cards
    - Improve accessibility (ARIA labels, keyboard navigation)

---

## 📁 File Reference

| Component | File(s) | Status |
|-----------|---------|--------|
| Price Simulator | `10-redeploy-adapt/price_simulator.py` | ✅ Complete |
| Energy Policy | `src/energy/policy.py`, `price_signal.py` | ✅ Complete |
| Electricity Maps | `src/energy/electricity_maps.py` | ✅ Complete |
| Main API | `src/api/main.py` | ✅ Durable Queue + CodeCarbon |
| LLM Client | `src/llm/llm_client.py` | ✅ Complete (Ollama) |
| Energy Scheduler | `10-redeploy-adapt/energy_scheduler.sh` | ✅ Complete |
| Helm Chart | `10-redeploy-adapt/helm_scheduling/` | ✅ Complete |
| K8s Deployment | `k8s/backend-deployment.yaml` | ✅ DB URL + Tolerations |
| PostgreSQL K8s | `k8s/postgres.yaml` | ✅ Complete |
| DB Schema | `src/storage/schema.sql` | ✅ Complete |
| DB Connection | `src/storage/db.py` | ✅ Complete |
| Durable Queue | `src/storage/durable_queue.py` | ✅ Complete |
| Prometheus | `10-redeploy-adapt/k8s/prometheus.yaml` | ✅ Complete |
| Grafana | `10-redeploy-adapt/k8s/grafana.yaml` | ✅ Complete |
| QueueList UI | `planner-ui/src/components/QueueList.tsx` | ✅ Complete (with Delete) |
| EnergyStatus UI | `planner-ui/src/components/EnergyStatus.tsx` | ✅ Complete |
| TaskList UI | `planner-ui/src/components/TaskList.tsx` | ✅ Complete (with Clear) |
| Calendar Integration | `src/integration/calendar_integration.py` | ✅ Complete (with update_event) |
| Calendar Page | `planner-ui/src/app/calendar/page.tsx` | ✅ Complete (React Big Calendar + DnD) |
| Carbon Page | `planner-ui/src/app/carbon/page.tsx` | ✅ Complete |
| Kepler Deployment | `k8s/kepler-values.yaml`, `docs/kepler-deployment.md` | ✅ Complete |

---

##  Resources

- [Electricity Maps](https://app.electricitymaps.com/map/live/fifteen_minutes)
- [Electricity Maps API Portal](https://api-portal.electricitymaps.com/)
- [Google Calendar API](https://developers.google.com/calendar/api/quickstart/python)
- [CodeCarbon Documentation](https://mlco2.github.io/codecarbon/)
- [Kepler Project](https://github.com/sustainable-computing-io/kepler)
- [React DnD for Drag & Drop](https://react-dnd.github.io/react-dnd/)
- [3Blue1Brown (Math Intuition)](https://www.youtube.com/c/3blue1brown)
- [OpenCode AI](https://opencode.ai/)
