'use client';

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getSchedule, getTasks, moveTask, createTask } from '@/lib/api';
import { CATEGORY_ICONS } from '@/lib/types';
import { Calendar as CalendarIcon, CheckCircle, LogOut, Plus, X } from 'lucide-react';
import { useEffect, useState, useMemo, useCallback } from 'react';
import { Calendar, dateFnsLocalizer, Views } from 'react-big-calendar';
import withDragAndDrop from 'react-big-calendar/lib/addons/dragAndDrop';
import { format, parse, startOfWeek, getDay, addDays, startOfWeek as startOfWeekFns, endOfWeek as endOfWeekFns, addMinutes } from 'date-fns';
import { enUS } from 'date-fns/locale/en-US';
import 'react-big-calendar/lib/css/react-big-calendar.css';
import 'react-big-calendar/lib/addons/dragAndDrop/styles.css';

// Drag and Drop Context
const DnDCalendar = withDragAndDrop(Calendar);

// Fix for React Big Calendar with Next.js/date-fns
const locales = {
  'en-US': enUS,
};

const localizer = dateFnsLocalizer({
  format,
  parse,
  startOfWeek,
  getDay,
  locales,
});

const categoryColors: Record<string, string> = {
  work: '#3b82f6', // blue-500
  personal: '#22c55e', // green-500
  health: '#ef4444', // red-500
  learning: '#a855f7', // purple-500
  default: '#6b7280', // gray-500
};

export default function CalendarPage() {
  const [view, setView] = useState<any>(Views.WEEK);
  const [date, setDate] = useState(new Date());

  // Calculate range based on view/date
  const { startStr, endStr } = useMemo(() => {
    let start = date;
    let end = date;

    if (view === Views.WEEK) {
      start = startOfWeekFns(date);
      end = endOfWeekFns(date);
    } else if (view === Views.MONTH) {
       // Simplification: just fetch +/- 1 month to be safe or use date math
       // For now, let's keep it tight to avoid loading too much
       start = new Date(date.getFullYear(), date.getMonth(), 1);
       end = new Date(date.getFullYear(), date.getMonth() + 1, 0);
    } 

    return {
        startStr: format(start, 'yyyy-MM-dd'),
        endStr: format(end, 'yyyy-MM-dd')
    };
  }, [view, date]);

  const { data: scheduleData, isLoading: scheduleLoading } = useQuery({
    queryKey: ['schedule', startStr, endStr],
    queryFn: () => getSchedule(startStr, endStr),
    refetchInterval: 10000,
  });

  const { data: tasksData, isLoading: tasksLoading } = useQuery({
    queryKey: ['tasks'],
    queryFn: () => getTasks(20),
    refetchInterval: 10000,
  });

  // Google Calendar Status
  const { data: authStatus, refetch: refetchAuth } = useQuery({
    queryKey: ['googleAuthStatus'],
    queryFn: async () => {
      const res = await fetch('http://localhost:8000/auth/google/status');
      if (!res.ok) return { connected: false };
      return res.json();
    },
  });

  // Handle OAuth callback params
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('success') === 'true') {
      window.history.replaceState({}, '', window.location.pathname);
      refetchAuth();
      alert('Successfully connected to Google Calendar!');
    } else if (params.get('error')) {
      alert(`Failed to connect: ${params.get('error')}`);
    }
  }, [refetchAuth]);

  const handleDisconnect = async () => {
    if (!confirm('Are you sure you want to disconnect Google Calendar?')) return;
    try {
      await fetch('http://localhost:8000/auth/google/disconnect', { method: 'POST' });
      refetchAuth();
    } catch (e) {
      alert('Failed to disconnect');
    }
  };

  const queryClient = useQueryClient();

  const handleMoveOrResize = useCallback(async ({ event, start, end }: any) => {
    try {
        await moveTask({
            task_id: event.resource?.task?.id || event.title,
            new_start: start.toISOString(),
            new_end: end.toISOString(),
            source: event.resource?.source || 'planner'
        });
        queryClient.invalidateQueries({ queryKey: ['schedule'] });
    } catch (e) {
        console.error("Move/Resize failed", e);
        alert("Failed to update task");
    }
  }, [queryClient]);

  const onEventResize = useCallback((data: any) => {
     handleMoveOrResize(data);
  }, [handleMoveOrResize]);

  const onEventDrop = useCallback((data: any) => {
     handleMoveOrResize(data);
  }, [handleMoveOrResize]);
  
  // Manual Creation
  const handleSelectSlot = useCallback(async ({ start, end }: any) => {
    const title = prompt("New Event Title:");
    if (title) {
        try {
            await createTask({
                title,
                start_time: start.toISOString(),
                end_time: end.toISOString(),
                category: 'work'
            });
            queryClient.invalidateQueries({ queryKey: ['schedule'] });
        } catch(e) {
            alert("Failed to create event");
        }
    }
  }, [queryClient]);

  // Transform schedule slots into Calendar Events
  const events = useMemo(() => {
    // New API format returns { slots: [...] } directly or inside schedule?
    // Based on updated backend, it returns { range: {...}, slots: [...] }
    const slots = (scheduleData as any)?.slots || [];
    
    return slots.map((slot: any, idx: number) => {
      // Use ISO strings if available (new backend), fallback to legacy
      let start: Date, end: Date;

      if (slot.start_iso) {
           start = new Date(slot.start_iso);
           end = new Date(slot.end_iso);
      } else {
           // Fallback for old data or today-only data
           const scheduleDateStr = (scheduleData as any)?.date || format(new Date(), 'yyyy-MM-dd');
           start = new Date(`${scheduleDateStr}T${slot.start_time}:00`);
           end = new Date(`${scheduleDateStr}T${slot.end_time}:00`);
      }

      if (isNaN(start.getTime())) start = new Date();
      if (isNaN(end.getTime())) end = new Date();
      
      const isGoogle = slot.source === 'google';

      return {
        id: slot.calendar_event_id || `local-${idx}`,
        title: slot.task?.title || 'Untitled',
        start,
        end,
        resource: { ...slot.task, source: slot.source },
        allDay: false,
        isGoogle,
      };
    });
  }, [scheduleData]);

  // Event Styling
  const eventPropGetter = (event: any) => {
    const category = event.resource?.category || 'default';
    let backgroundColor = categoryColors[category] || categoryColors.default;
    
    // Dim Google Events slightly or style differently
    if (event.isGoogle) {
        // Maybe make them striped or a specific Google Blue?
        // For now, let's keep category colors but maybe add a border
    }

    return {
      style: {
        backgroundColor,
        borderRadius: '4px',
        opacity: event.isGoogle ? 1.0 : 0.8, // Make Google events solid, AI events slightly transparent?
        color: 'white',
        border: event.isGoogle ? '2px solid rgba(255,255,255,0.3)' : '0px',
        display: 'block',
      },
    };
  };

  const isLoading = scheduleLoading || tasksLoading;
  const tasks = tasksData?.tasks || [];

  return (
    <div className="space-y-6 h-[calc(100vh-120px)] flex flex-col">
      {/* Header Area */}
      <div className="flex-none">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center">
              <CalendarIcon className="w-6 h-6 mr-2" />
              Smart Calendar
            </h1>
            <p className="text-gray-600 mt-1">
              Showing {startStr} to {endStr}
            </p>
          </div>

          <div className="flex gap-2 items-center">
            {/* Google Status */}
            <div className="mr-4">
              {authStatus?.connected ? (
                <div className="flex items-center text-sm text-green-700 bg-green-50 px-3 py-1 rounded-full border border-green-200">
                  <CheckCircle className="w-4 h-4 mr-2" />
                  <span className="mr-2">Synced: {authStatus.email}</span>
                  <button 
                    onClick={handleDisconnect}
                    className="text-red-600 hover:text-red-800 ml-2 border-l border-green-200 pl-2"
                    title="Disconnect"
                  >
                    <LogOut className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <a
                  href="http://localhost:8000/auth/google/login"
                  className="flex items-center text-sm text-blue-700 bg-blue-50 px-3 py-1 rounded-full border border-blue-200 hover:bg-blue-100 transition-colors"
                >
                  <CalendarIcon className="w-4 h-4 mr-2" />
                  Connect Google Calendar
                </a>
              )}
            </div>
            
            {/* Legend */}
            {Object.entries(categoryColors).map(([cat, color]) => (
                 cat !== 'default' && (
                  <span key={cat} className="flex items-center text-xs text-gray-600">
                    <span className="w-3 h-3 rounded-full mr-1" style={{ backgroundColor: color }}></span>
                    <span className="capitalize">{cat}</span>
                  </span>
                 )
            ))}
          </div>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-4 gap-6 min-h-0">
        
        {/* Calendar Column (Takes up 3/4 space) */}
        <div className="lg:col-span-3 bg-white rounded-xl shadow-sm border border-gray-200 p-4 flex flex-col overflow-hidden">
          {isLoading ? (
            <div className="h-full flex items-center justify-center text-gray-400">Loading Calendar...</div>
          ) : (
            <DnDCalendar
              localizer={localizer}
              events={events}
              startAccessor={(event: any) => event.start}
              endAccessor={(event: any) => event.end}
              style={{ height: '100%' }}
              view={view}
              onView={setView}
              date={date}
              onNavigate={setDate}
              eventPropGetter={eventPropGetter}
              tooltipAccessor={(e: any) => `${e.title} (${e.resource?.category})`}
              views={[Views.MONTH, Views.WEEK, Views.DAY, Views.AGENDA]}
              defaultView={Views.WEEK}
              min={new Date(0, 0, 0, 6, 0, 0)} // Start at 6 AM
              max={new Date(0, 0, 0, 23, 0, 0)} // End at 11 PM
              step={30} // 30 min slots
              timeslots={2}
              selectable
              onSelectSlot={handleSelectSlot}
              resizable
              onEventDrop={onEventDrop}
              onEventResize={onEventResize}
            />
          )}
        </div>

        {/* Sidebar: Unscheduled Tasks */}
        <div className="lg:col-span-1 bg-white rounded-xl shadow-sm border border-gray-200 p-4 overflow-y-auto">
          <h2 className="font-semibold text-gray-900 mb-4 flex items-center">
             📋 Unscheduled Tasks
          </h2>
          {tasks.length === 0 ? (
             <p className="text-sm text-gray-400">No pending tasks.</p>
          ) : (
            <div className="space-y-3">
              {tasks.map((task: any, idx: number) => {
                const icon = CATEGORY_ICONS[task.category as keyof typeof CATEGORY_ICONS] || '📌';
                return (
                  <div key={idx} className="border border-gray-100 rounded-lg p-3 hover:bg-gray-50 transition-colors">
                    <div className="font-medium text-gray-900 text-sm">
                      {icon} {task.title}
                    </div>
                    {task.description && (
                       <p className="text-xs text-gray-500 mt-1 line-clamp-2">{task.description}</p>
                    )}
                    <div className="text-xs text-gray-400 mt-2 flex justify-between">
                      <span>{task.estimated_duration_min || 30} min</span>
                      <span className="capitalize text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded">
                        Priority {task.priority}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
