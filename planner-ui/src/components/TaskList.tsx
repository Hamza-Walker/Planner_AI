'use client';

import { useQuery } from '@tanstack/react-query';
import { getTasks } from '@/lib/api';
import { Task, CATEGORY_ICONS } from '@/lib/types';
import { Clock, Flag } from 'lucide-react';

const categoryColors: Record<string, string> = {
  work: 'bg-blue-100 text-blue-700 border-blue-200',
  personal: 'bg-green-100 text-green-700 border-green-200',
  health: 'bg-red-100 text-red-700 border-red-200',
  learning: 'bg-purple-100 text-purple-700 border-purple-200',
};

function TaskCard({ task }: { task: Task }) {
  const color = categoryColors[task.category] || 'bg-gray-100 text-gray-700';
  const icon = CATEGORY_ICONS[task.category] || '📌';
  
  // Priority stars
  const stars = '★'.repeat(task.priority) + '☆'.repeat(5 - task.priority);

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <h4 className="font-medium text-gray-900">{task.title}</h4>
          <div className="flex items-center gap-3 mt-2 text-sm">
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>
              {icon} {task.category}
            </span>
            <span className="text-yellow-500" title={`Priority: ${task.priority}`}>
              {stars}
            </span>
            <span className="flex items-center text-gray-500">
              <Clock className="w-3 h-3 mr-1" />
              {task.estimated_duration} min
            </span>
          </div>
        </div>
        {task.priority <= 2 && (
          <span title="High Priority">
            <Flag className="w-5 h-5 text-red-500" />
          </span>
        )}
      </div>
    </div>
  );
}

export function TaskList() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['tasks'],
    queryFn: () => getTasks(20),
    refetchInterval: 10000, // Poll every 10 seconds
  });

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="font-semibold text-gray-900 mb-4">📋 Recent Tasks</h3>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="animate-pulse">
              <div className="h-16 bg-gray-200 rounded-lg"></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="font-semibold text-gray-900 mb-4">📋 Recent Tasks</h3>
        <p className="text-gray-500 text-sm">Unable to load tasks</p>
      </div>
    );
  }

  const tasks = data?.tasks || [];

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900">📋 Recent Tasks</h3>
        <span className="text-sm text-gray-500">{data?.total ?? 0} total</span>
      </div>
      
      {tasks.length === 0 ? (
        <div className="text-center py-8 text-gray-500">
          <p>No tasks yet</p>
          <p className="text-sm mt-1">Submit some notes to extract tasks</p>
        </div>
      ) : (
        <div className="space-y-3 max-h-96 overflow-y-auto">
          {tasks.map((task, index) => (
            <TaskCard key={`${task.title}-${index}`} task={task} />
          ))}
        </div>
      )}
    </div>
  );
}
