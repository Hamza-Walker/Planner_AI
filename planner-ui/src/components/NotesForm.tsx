'use client';

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { submitNotes } from '@/lib/api';
import { Send, Loader2 } from 'lucide-react';

export function NotesForm() {
  const [notes, setNotes] = useState('');
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: submitNotes,
    onSuccess: () => {
      setNotes('');
      // Refetch tasks after submission
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['queue'] });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (notes.trim()) {
      mutation.mutate(notes);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="font-semibold text-gray-900 mb-4">📝 Submit Daily Notes</h3>
      
      <form onSubmit={handleSubmit}>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder={"Enter your daily notes here...\n\nExample:\n- Finish the quarterly report for Sarah (urgent!)\n- Call mom back about Sunday dinner\n- Schedule dentist appointment\n- Read chapter 5 of Clean Code\n- Go for a 30 min run"}
          className="w-full h-40 p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent resize-none text-gray-900"
          disabled={mutation.isPending}
        />
        
        <div className="mt-4 flex items-center justify-between">
          <button
            type="submit"
            disabled={mutation.isPending || !notes.trim()}
            className="inline-flex items-center px-4 py-2 bg-green-600 text-white font-medium rounded-lg hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {mutation.isPending ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Processing...
              </>
            ) : (
              <>
                <Send className="w-4 h-4 mr-2" />
                Submit Notes
              </>
            )}
          </button>

          {mutation.isSuccess && mutation.data && (
            <span className={`text-sm font-medium ${
              mutation.data.status === 'processed' 
                ? 'text-green-600' 
                : 'text-orange-600'
            }`}>
              {mutation.data.status === 'processed' 
                ? `✅ Processed (${mutation.data.tasks?.length ?? 0} tasks extracted)` 
                : `⏸️ Queued (position: ${mutation.data.queue_size})`}
            </span>
          )}

          {mutation.isError && (
            <span className="text-sm text-red-600">
              ❌ Error: {mutation.error.message}
            </span>
          )}
        </div>
      </form>
    </div>
  );
}
