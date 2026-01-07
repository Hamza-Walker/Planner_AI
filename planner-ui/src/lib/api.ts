// API client for FastAPI backend

import type {
  NotesResponse,
  QueueStatus,
  TasksResponse,
  ScheduleResponse,
  HealthResponse,
  CarbonMetrics,
  QueueItemsResponse,
} from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    throw new ApiError(response.status, `API error: ${response.statusText}`);
  }

  return response.json();
}

// POST /notes - Submit daily notes
export async function submitNotes(notes: string): Promise<NotesResponse> {
  return fetchApi<NotesResponse>('/notes', {
    method: 'POST',
    body: JSON.stringify({ notes }),
  });
}

// GET /queue - Get queue status and energy info
export async function getQueueStatus(): Promise<QueueStatus> {
  return fetchApi<QueueStatus>('/queue');
}

// GET /queue/items - Get recent queue items
export async function getQueueItems(limit: number = 20): Promise<QueueItemsResponse> {
  return fetchApi<QueueItemsResponse>(`/queue/items?limit=${limit}`);
}

export async function deleteQueueItem(id: string): Promise<any> {
    return fetchApi<any>(`/queue/items/${id}`, {
        method: 'DELETE',
    });
}

// GET /tasks - Get recent extracted tasks
export async function getTasks(limit: number = 20): Promise<TasksResponse> {
  return fetchApi<TasksResponse>(`/tasks?limit=${limit}`);
}

// GET /schedule - Get schedule for a range (default today)
export async function getSchedule(start?: string, end?: string): Promise<ScheduleResponse> {
  const params = new URLSearchParams();
  if (start) params.append('start_date', start);
  if (end) params.append('end_date', end);
  return fetchApi<ScheduleResponse>(`/schedule?${params.toString()}`);
}

// Legacy alias for compatibility
export async function getTodaySchedule(): Promise<ScheduleResponse> {
  return getSchedule();
}

// GET /health - Health check
export async function getHealth(): Promise<HealthResponse> {
  return fetchApi<HealthResponse>('/health');
}

// GET /metrics/carbon - Carbon emissions metrics
export async function getCarbonMetrics(): Promise<CarbonMetrics> {
  return fetchApi<CarbonMetrics>('/metrics/carbon');
}

export async function moveTask(payload: {
  task_id: string;
  new_start: string;
  new_end: string;
  source: string;
}): Promise<any> {
  return fetchApi<any>('/schedule/move', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function clearRecentTasks(): Promise<any> {
    return fetchApi<any>('/tasks/queue', {
        method: 'DELETE',
    });
}

export async function createTask(payload: {
    title: string;
    start_time: string;
    end_time: string;
    category?: string;
}): Promise<any> {
    return fetchApi<any>('/tasks/create', {
        method: 'POST',
        body: JSON.stringify(payload),
    });
}
