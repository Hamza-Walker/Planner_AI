'use client';

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getQueueItems, deleteQueueItem } from '@/lib/api';
import { Clock, AlertCircle, CheckCircle, Loader2, Trash2 } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

export function QueueList() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ['queue-items'],
    queryFn: () => getQueueItems(10),
    refetchInterval: 3000,
  });

  const handleDelete = async (id: string) => {
    try {
      await deleteQueueItem(id);
      queryClient.invalidateQueries({ queryKey: ['queue-items'] });
    } catch (e) {
      console.error('Failed to delete queue item', e);
    }
  };

  if (isLoading) return null;
  if (error) return null;

  const items = data?.items || [];
  if (items.length === 0) return null;

  return (
    <div className="bg-white rounded-lg shadow p-6 mt-6">
      <h3 className="font-semibold text-gray-900 mb-4 flex items-center">
        <Clock className="w-5 h-5 mr-2 text-blue-500" />
        Queue Status
      </h3>

      <div className="space-y-3">
        {items.map((item) => (
          <div
            key={item.id}
            className="flex items-center justify-between p-3 bg-gray-50 rounded-md border border-gray-100"
          >
            <div className="flex-1 min-w-0 mr-4">
              <p className="text-sm font-medium text-gray-900 truncate">
                {item.notes}
              </p>
              <div className="flex items-center mt-1 text-xs text-gray-500">
                <span className="capitalize px-2 py-0.5 rounded-full bg-gray-200 text-gray-700 mr-2">
                  {item.status}
                </span>
                <span>
                  {item.created_at && formatDistanceToNow(new Date(item.created_at), { addSuffix: true })}
                </span>
                {item.attempts > 0 && (
                  <span className="ml-2">
                    (Attempt {item.attempts}/{item.max_attempts})
                  </span>
                )}
              </div>
            </div>

            <div className="flex-shrink-0 flex items-center gap-2">
              <button
                onClick={() => handleDelete(item.id)}
                className="text-gray-400 hover:text-red-500 transition-colors"
                title="Delete"
              >
                <Trash2 className="w-4 h-4" />
              </button>
              
              {item.status === 'processing' && (
                <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />
              )}
              {item.status === 'completed' && (
                <CheckCircle className="w-5 h-5 text-green-500" />
              )}
              {item.status === 'failed' && (
                <AlertCircle className="w-5 h-5 text-red-500" />
              )}
              {item.status === 'dead' && (
                <AlertCircle className="w-5 h-5 text-red-700" />
              )}
              {item.status === 'pending' && (
                <Clock className="w-5 h-5 text-gray-400" />
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
