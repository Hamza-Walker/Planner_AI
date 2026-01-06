'use client';

import { useQuery } from '@tanstack/react-query';
import { getQueueStatus } from '@/lib/api';
import { Sun, Cloud, Zap, Clock } from 'lucide-react';

export function EnergyStatus() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['queue'],
    queryFn: getQueueStatus,
    refetchInterval: 5000, // Poll every 5 seconds
  });

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-6 animate-pulse">
        <div className="h-4 bg-gray-200 rounded w-1/2 mb-4"></div>
        <div className="h-8 bg-gray-200 rounded w-3/4"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 rounded-lg shadow p-6 border border-red-200">
        <h3 className="font-semibold text-red-700">⚠️ Backend Offline</h3>
        <p className="text-sm text-red-600 mt-1">
          Start the FastAPI server on port 8000
        </p>
      </div>
    );
  }

  const price = data?.energy?.electricity_price_eur ?? 0;
  const solarAvailable = data?.energy?.solar_available ?? false;
  const modelTier = data?.llm_tier ?? 'small';
  const queueSize = data?.queue_size ?? 0;
  const processNow = data?.process_now ?? false;
  const energySource = (data?.energy as any)?.source ?? 'unknown';

  // Price percentage (assume max €1.50)
  const pricePercent = Math.min((price / 1.5) * 100, 100);
  const priceColor = price > 0.7 ? 'bg-red-500' : price > 0.4 ? 'bg-yellow-500' : 'bg-green-500';

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="font-semibold text-gray-900 mb-4 flex items-center">
        <Zap className="w-5 h-5 mr-2 text-yellow-500" />
        Energy Status
      </h3>

      <div className="space-y-4">
        {/* Price */}
        <div>
          <div className="flex justify-between text-sm mb-1">
            <span className="text-gray-600">Electricity Price</span>
            <span className="font-medium">€{price.toFixed(2)}/kWh</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2.5">
            <div
              className={`h-2.5 rounded-full ${priceColor}`}
              style={{ width: `${pricePercent}%` }}
            ></div>
          </div>
          <div className="text-xs text-gray-500 mt-1">
            Threshold: €0.70 (current: {pricePercent.toFixed(0)}%)
          </div>
        </div>

        {/* Solar */}
        <div className="flex items-center justify-between">
          <span className="text-gray-600 text-sm">Solar</span>
          <span className={`flex items-center text-sm font-medium ${solarAvailable ? 'text-yellow-600' : 'text-gray-500'}`}>
            {solarAvailable ? (
              <>
                <Sun className="w-4 h-4 mr-1" /> Available
              </>
            ) : (
              <>
                <Cloud className="w-4 h-4 mr-1" /> Unavailable
              </>
            )}
          </span>
        </div>

        {/* Model Tier */}
        <div className="flex items-center justify-between">
          <span className="text-gray-600 text-sm">Model Tier</span>
          <span className={`px-2 py-1 rounded text-xs font-medium ${
            modelTier === 'large' 
              ? 'bg-blue-100 text-blue-700' 
              : 'bg-green-100 text-green-700'
          }`}>
            {modelTier === 'large' ? '🚀 Large (Llama 3.2)' : '🌱 Small (Llama 3.2)'}
          </span>
        </div>

        {/* Queue */}
        <div className="flex items-center justify-between">
          <span className="text-gray-600 text-sm">Queue</span>
          <span className="flex items-center text-sm">
            <Clock className="w-4 h-4 mr-1 text-gray-500" />
            {queueSize} tasks
          </span>
        </div>

        {/* Process Status */}
        <div className="flex items-center justify-between pt-2 border-t">
          <span className="text-gray-600 text-sm">Status</span>
          <span className={`flex items-center text-sm font-medium ${
            processNow ? 'text-green-600' : 'text-orange-600'
          }`}>
            {processNow ? '✅ Processing Now' : '⏸️ Queuing Tasks'}
          </span>
        </div>

        {/* Data Source */}
        <div className="flex items-center justify-between text-xs text-gray-400">
          <span>Data Source</span>
          <span className={`px-2 py-0.5 rounded ${
            energySource === 'electricity_maps' 
              ? 'bg-green-100 text-green-700' 
              : 'bg-gray-100 text-gray-600'
          }`}>
            {energySource === 'electricity_maps' ? '🌍 Electricity Maps' : '🔌 Local Simulator'}
          </span>
        </div>
      </div>
    </div>
  );
}
