// TypeScript types matching Pydantic models in src/planner_ai/models.py

export type TaskCategory = 'work' | 'personal' | 'health' | 'learning';

export interface Task {
  title: string;
  category: TaskCategory;
  priority: number; // 1-5
  estimated_duration: number; // minutes
  deadline?: string | null;
  created_at?: string;
}

export interface ScheduledTask {
  task: Task;
  start_time: string;
  end_time: string;
  calendar_slot?: string;
}

export interface Schedule {
  date: string;
  slots: ScheduledTask[];
}

export interface EnergyStatus {
  price_eur: number;
  solar_available: boolean;
  timestamp: string;
}

export interface QueueStatus {
  queue_size: number;
  process_now: boolean;
  llm_tier: 'large' | 'small';
  energy: EnergyStatus | null;
}

export interface NotesResponse {
  status: 'processed' | 'queued';
  llm_tier: 'large' | 'small';
  queue_size?: number;
  energy: EnergyStatus | null;
  tasks?: Task[];
  schedule?: Schedule;
}

export interface TasksResponse {
  tasks: Task[];
  total: number;
}

export interface ScheduleResponse {
  date: string;
  schedule: Schedule | Record<string, never>;
}

export interface HealthResponse {
  status: string;
  profile: string;
  queue_size: number;
}

export interface CarbonMetrics {
  emissions_kg: number;
  emissions_g: number;
  energy_kwh: number;
  duration_seconds: number;
  project_name: string;
  error?: string;
}

// UI helper types
export const CATEGORY_COLORS: Record<TaskCategory, string> = {
  work: 'bg-blue-500',
  personal: 'bg-green-500',
  health: 'bg-red-500',
  learning: 'bg-purple-500',
};

export const CATEGORY_ICONS: Record<TaskCategory, string> = {
  work: '💼',
  personal: '👤',
  health: '🏥',
  learning: '📚',
};
