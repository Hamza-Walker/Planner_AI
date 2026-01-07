# Planner AI - UI

Web interface for the Planner AI project, built with Next.js 14, TypeScript, and Tailwind CSS.

## Features

- **Dashboard**: Submit daily notes, view energy status, and recent tasks.
- **Calendar**: Visual timeline of scheduled tasks.
- **Sustainability**: Track carbon emissions and energy-aware decisions.
## Requirements

To run this project locally, you need:

- Kubernetes cluster (tested with **Docker Desktop Kubernetes** or **Minikube**)
- kubectl
- Helm v3+
- Docker

Monitoring stack:
- Prometheus & Grafana installed via **kube-prometheus-stack (Helm chart)**

The backend exposes Prometheus metrics at `/metrics`.
## Prerequisites

- Node.js 18+
- Python backend running on port 8000

## Getting Started

1. Install dependencies:
   ```bash
   npm install
   ```

2. Run the development server:
   ```bash
   npm run dev
   ```

3. Open [http://localhost:3000](http://localhost:3000) with your browser.

## Configuration

The app expects the backend API to be available at `http://localhost:8000`.
To change this, create a `.env.local` file:

```
NEXT_PUBLIC_API_URL=http://your-api-url:8000
```

## Project Structure

- `src/app`: Next.js App Router pages
- `src/components`: React components
- `src/lib`: API client and types
