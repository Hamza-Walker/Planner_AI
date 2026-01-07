from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, REGISTRY


# we check if they are already registered to avoid errors during hot reloads or test runs
def get_or_create_metric(name, documentation, metric_type, **kwargs):
    try:
        # Try to create it
        return metric_type(name, documentation, **kwargs)
    except ValueError:
        # If it already exists, retrieve it from the registry
        return REGISTRY._names_to_collectors[name]


REQUESTS_TOTAL = get_or_create_metric(
    "planner_requests_total",
    "Total requests",
    Counter,
    labelnames=["endpoint", "status"],
)

REQUEST_LATENCY_SECONDS = get_or_create_metric(
    "planner_request_latency_seconds",
    "Request latency",
    Histogram,
    labelnames=["endpoint"],
)

TASKS_EXTRACTED_TOTAL = get_or_create_metric(
    "planner_tasks_extracted_total", "Total tasks extracted from notes", Counter
)

TASKS_SCHEDULED_TOTAL = get_or_create_metric(
    "planner_tasks_scheduled_total", "Total tasks scheduled", Counter
)

LLM_TIER_TOTAL = get_or_create_metric(
    "planner_llm_tier_total", "LLM tier usage", Counter, labelnames=["tier"]
)

QUEUE_DEPTH = get_or_create_metric(
    "planner_queue_depth", "Current items in queue", Gauge
)
