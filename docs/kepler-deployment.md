# Kepler Deployment Guide

This guide explains how to deploy and manage Kepler (Kubernetes-based Efficient Power Level Exporter) in the Planner_AI cluster.

## What is Kepler?

Kepler is a tool that measures the **actual energy consumption** of Kubernetes pods and nodes using:
- eBPF to monitor CPU/GPU usage per pod
- Hardware performance counters (when available)
- Power estimation models (for environments like Minikube)

It exports metrics to Prometheus including:
- `kepler_container_joules_total` - Total energy consumption per container
- `kepler_node_platform_joules_total` - Total platform energy
- `kepler_process_*` - Process-level metrics

## Installation

### Prerequisites
- Kubernetes cluster (Minikube, Kind, or production cluster)
- Helm 3.x installed
- kubectl configured

### Install Kepler

```bash
# Add Kepler Helm repository
helm repo add kepler https://sustainable-computing-io.github.io/kepler-helm-chart
helm repo update

# Create dedicated namespace
kubectl create namespace kepler-system

# Install Kepler
helm install kepler kepler/kepler \
  --namespace kepler-system \
  --values k8s/kepler-values.yaml
```

### Verify Installation

```bash
# Check pod status
kubectl get pods -n kepler-system

# Check logs
kubectl logs -n kepler-system -l app.kubernetes.io/name=kepler

# Verify metrics endpoint
kubectl port-forward -n kepler-system svc/kepler 9103:9103
curl http://localhost:9103/metrics | grep kepler_container
```

## Configuration

The Kepler configuration is stored in `k8s/kepler-values.yaml`:

```yaml
# Service Monitor disabled (using pod annotations instead)
serviceMonitor:
  enabled: false

# Prometheus scraping via annotations
service:
  type: ClusterIP
  port: 9103
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "9103"
    prometheus.io/path: "/metrics"

# Resource limits
resources:
  limits:
    cpu: 500m
    memory: 500Mi
  requests:
    cpu: 100m
    memory: 128Mi
```

## Prometheus Integration

Kepler metrics are automatically scraped by Prometheus. The scrape configuration is in `observability/prometheus/prometheus.yml`:

```yaml
- job_name: "kepler"
  metrics_path: /metrics
  static_configs:
    - targets: ["kepler.kepler-system.svc.cluster.local:9103"]
  scrape_interval: 5s
```

### Update Prometheus Config

```bash
# Update ConfigMap
kubectl create configmap prometheus-config \
  --from-file=observability/prometheus/prometheus.yml \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart Prometheus
kubectl rollout restart deployment prometheus
```

## Key Metrics

### Container Energy Metrics
- `kepler_container_joules_total` - Total energy per container
- `kepler_container_core_joules_total` - CPU core energy
- `kepler_container_dram_joules_total` - Memory energy
- `kepler_container_package_joules_total` - Package energy

### Node Energy Metrics
- `kepler_node_platform_joules_total` - Total platform energy
- `kepler_node_core_joules_total` - Total CPU core energy
- `kepler_node_dram_joules_total` - Total memory energy

### Process Metrics
- `kepler_process_cpu_time_ms` - CPU time per process
- `kepler_process_total_energy_millijoules` - Process energy consumption

## Grafana Dashboards

Import Kepler dashboards from the official repository:
- https://github.com/sustainable-computing-io/kepler/tree/main/grafana-dashboards

Or create custom dashboards using the metrics above.

## Troubleshooting

### Pod Not Starting

Check logs:
```bash
kubectl logs -n kepler-system <pod-name>
```

Common issues:
- **Missing privileges**: Kepler needs privileged mode for eBPF
- **Missing kernel modules**: Some features require specific kernel modules
- **Resource limits**: Increase memory/CPU if pod is OOMKilled

### No Metrics in Prometheus

1. Check Kepler service:
```bash
kubectl get svc -n kepler-system
```

2. Test metrics endpoint:
```bash
kubectl port-forward -n kepler-system svc/kepler 9103:9103
curl http://localhost:9103/metrics
```

3. Check Prometheus targets:
```bash
kubectl port-forward svc/prometheus 9090:9090
# Visit http://localhost:9090/targets
```

### Minikube Limitations

On Minikube, Kepler uses **power estimation models** instead of hardware counters because:
- No access to hardware PMU (Performance Monitoring Unit)
- eBPF perf events may not be fully supported

This is normal and Kepler will still provide useful energy estimates.

## Maintenance

### Upgrade Kepler

```bash
# Update Helm repo
helm repo update

# Upgrade release
helm upgrade kepler kepler/kepler \
  --namespace kepler-system \
  --values k8s/kepler-values.yaml
```

### Uninstall Kepler

```bash
# Uninstall Helm release
helm uninstall kepler -n kepler-system

# Delete namespace (optional)
kubectl delete namespace kepler-system
```

## Resources

- [Kepler GitHub](https://github.com/sustainable-computing-io/kepler)
- [Kepler Helm Chart](https://github.com/sustainable-computing-io/kepler-helm-chart)
- [Kepler Documentation](https://sustainable-computing.io/)
- [eBPF Introduction](https://ebpf.io/)
