// API client for FastAPI backend

import type {
  NotesResponse,
  QueueStatus,
  TasksResponse,
  ScheduleResponse,
  HealthResponse,
  CarbonMetrics,
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

// GET /tasks - Get recent extracted tasks
export async function getTasks(limit: number = 20): Promise<TasksResponse> {
  return fetchApi<TasksResponse>(`/tasks?limit=${limit}`);
}

// GET /schedule - Get today's schedule
export async function getTodaySchedule(): Promise<ScheduleResponse> {
  return fetchApi<ScheduleResponse>('/schedule');
}

// GET /schedule/:date - Get schedule for a specific date
export async function getSchedule(date: string): Promise<ScheduleResponse> {
  return fetchApi<ScheduleResponse>(`/schedule/${date}`);
}

// GET /health - Health check
export async function getHealth(): Promise<HealthResponse> {
  return fetchApi<HealthResponse>('/health');
}

// GET /metrics/carbon - Carbon emissions metrics
export async function getCarbonMetrics(): Promise<CarbonMetrics> {
  return fetchApi<CarbonMetrics>('/metrics/carbon');
}
