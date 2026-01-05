'use client';

import { useQuery } from '@tanstack/react-query';
import { getTodaySchedule, getTasks } from '@/lib/api';
import { CATEGORY_ICONS } from '@/lib/types';
import { Calendar, Clock } from 'lucide-react';

const categoryColors: Record<string, string> = {
  work: 'bg-blue-500 border-blue-600',
  personal: 'bg-green-500 border-green-600',
  health: 'bg-red-500 border-red-600',
  learning: 'bg-purple-500 border-purple-600',
};

// Generate hours from 6 AM to 10 PM
const hours = Array.from({ length: 17 }, (_, i) => i + 6);

export default function CalendarPage() {
  const { data: scheduleData, isLoading: scheduleLoading } = useQuery({
    queryKey: ['schedule'],
    queryFn: getTodaySchedule,
    refetchInterval: 10000,
  });

  const { data: tasksData, isLoading: tasksLoading } = useQuery({
    queryKey: ['tasks'],
    queryFn: () => getTasks(20),
    refetchInterval: 10000,
  });

  const isLoading = scheduleLoading || tasksLoading;

  // Get scheduled slots
  const slots = scheduleData?.schedule?.slots || [];
  const tasks = tasksData?.tasks || [];

  // Create a map of tasks by their scheduled time
  const tasksByHour: Record<number, typeof slots> = {};
  slots.forEach((slot) => {
    const hour = parseInt(slot.start_time.split(':')[0], 10);
    if (!tasksByHour[hour]) {
      tasksByHour[hour] = [];
    }
    tasksByHour[hour].push(slot);
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center">
            <Calendar className="w-6 h-6 mr-2" />
            Calendar
          </h1>
          <p className="text-gray-600 mt-1">
            Today&apos;s schedule: {scheduleData?.date || 'Loading...'}
          </p>
        </div>
        <div className="flex gap-2">
          {Object.entries(categoryColors).map(([category, color]) => (
            <span key={category} className="flex items-center text-xs text-gray-600">
              <span className={`w-3 h-3 rounded mr-1 ${color}`}></span>
              {category}
            </span>
          ))}
        </div>
      </div>

      {/* Timeline */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-gray-500">Loading schedule...</div>
        ) : slots.length === 0 && tasks.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            <Calendar className="w-12 h-12 mx-auto mb-4 text-gray-300" />
            <p>No scheduled tasks for today</p>
            <p className="text-sm mt-1">Submit notes on the Dashboard to generate a schedule</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {hours.map((hour) => {
              const hourTasks = tasksByHour[hour] || [];
              const hourStr = `${hour.toString().padStart(2, '0')}:00`;
              
              return (
                <div key={hour} className="flex">
                  {/* Hour label */}
                  <div className="w-20 flex-shrink-0 py-4 px-4 text-sm text-gray-500 border-r border-gray-100">
                    {hourStr}
                  </div>
                  
                  {/* Tasks for this hour */}
                  <div className="flex-1 py-2 px-4 min-h-[60px]">
                    {hourTasks.map((slot, idx) => {
                      const category = slot.task?.category || 'work';
                      const color = categoryColors[category] || 'bg-gray-500 border-gray-600';
                      const icon = CATEGORY_ICONS[category as keyof typeof CATEGORY_ICONS] || '📌';
                      
                      return (
                        <div
                          key={idx}
                          className={`${color} text-white rounded-lg p-3 mb-2 border-l-4`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-medium">
                              {icon} {slot.task?.title || 'Task'}
                            </span>
                            <span className="text-xs opacity-80 flex items-center">
                              <Clock className="w-3 h-3 mr-1" />
                              {slot.start_time} - {slot.end_time}
                            </span>
                          </div>
                          {slot.task?.estimated_duration && (
                            <div className="text-xs mt-1 opacity-80">
                              {slot.task.estimated_duration} min • Priority {slot.task.priority}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Unscheduled tasks */}
      {tasks.length > 0 && slots.length === 0 && (
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="font-semibold text-gray-900 mb-4">📋 Extracted Tasks (Unscheduled)</h2>
          <p className="text-sm text-gray-500 mb-4">
            These tasks were extracted but not yet scheduled. Run the scheduler to place them on the calendar.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {tasks.slice(0, 10).map((task, idx) => {
              const icon = CATEGORY_ICONS[task.category as keyof typeof CATEGORY_ICONS] || '📌';
              return (
                <div key={idx} className="border border-gray-200 rounded-lg p-3">
                  <div className="font-medium text-gray-900">
                    {icon} {task.title}
                  </div>
                  <div className="text-sm text-gray-500 mt-1">
                    {task.estimated_duration} min • Priority {task.priority}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
