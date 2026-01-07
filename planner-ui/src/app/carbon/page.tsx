'use client';

import { useQuery } from '@tanstack/react-query';
import { getCarbonMetrics, getQueueStatus } from '@/lib/api';
import { Leaf, Zap, Clock, Sun, TrendingDown, Activity, Cpu } from 'lucide-react';

export default function CarbonPage() {
  const { data: carbonData, isLoading: carbonLoading } = useQuery({
    queryKey: ['carbon'],
    queryFn: getCarbonMetrics,
    refetchInterval: 10000,
  });

  const { data: queueData } = useQuery({
    queryKey: ['queue'],
    queryFn: getQueueStatus,
    refetchInterval: 5000,
  });

  const emissions = carbonData?.emissions_g ?? 0;
  const energy = carbonData?.energy_kwh ?? 0;
  const duration = carbonData?.duration_seconds ?? 0;
  const modelTier = queueData?.llm_tier ?? 'small';
  const price = queueData?.energy?.electricity_price_eur ?? 0;
  const solarAvailable = queueData?.energy?.solar_available ?? false;
  const energySource = queueData?.energy?.source ?? 'unknown';

  // Price tier helpers
  const getPriceStatus = (p: number) => {
    if (p < 0.50) return { label: 'Low', color: 'green', bg: 'bg-green-500' };
    if (p <= 0.70) return { label: 'Moderate', color: 'yellow', bg: 'bg-yellow-500' };
    return { label: 'High', color: 'red', bg: 'bg-red-500' };
  };

  const priceStatus = getPriceStatus(price);

  return (
    <div className="max-w-5xl mx-auto space-y-8 p-6">
      {/* Header */}
      <div className="text-center">
        <h1 className="text-3xl font-bold text-gray-900 flex items-center justify-center gap-3">
          <Leaf className="w-8 h-8 text-green-600" />
          Energy Dashboard
        </h1>
        <p className="text-gray-500 mt-2">
          Real-time energy monitoring and carbon tracking
        </p>
      </div>

      {/* Main Grid: Price + Status */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Live Price - Takes 2 columns */}
        <div className="lg:col-span-2 bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500 uppercase tracking-wide">Current Price</p>
              <div className="flex items-baseline gap-2 mt-2">
                <span className={`text-5xl font-bold ${
                  priceStatus.color === 'green' ? 'text-green-600' :
                  priceStatus.color === 'yellow' ? 'text-amber-500' : 'text-red-600'
                }`}>
                  €{price.toFixed(2)}
                </span>
                <span className="text-gray-400 text-lg">/kWh</span>
              </div>
              <div className="flex items-center gap-3 mt-3">
                <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
                  priceStatus.color === 'green' ? 'bg-green-100 text-green-700' :
                  priceStatus.color === 'yellow' ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'
                }`}>
                  {priceStatus.label}
                </span>
                <span className="text-xs text-gray-400">
                  Threshold: €0.70
                </span>
              </div>
            </div>
            
            <div className="text-right space-y-2">
              {/* Solar Status */}
              <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm ${
                solarAvailable 
                  ? 'bg-amber-50 text-amber-700' 
                  : 'bg-gray-50 text-gray-500'
              }`}>
                <Sun className={`w-4 h-4 ${solarAvailable ? 'text-amber-500' : 'text-gray-400'}`} />
                {solarAvailable ? 'Solar Active' : 'No Solar'}
              </div>
              
              {/* Model Status */}
              <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm ${
                modelTier === 'large' 
                  ? 'bg-blue-50 text-blue-700' 
                  : 'bg-green-50 text-green-700'
              }`}>
                <Cpu className="w-4 h-4" />
                {modelTier === 'large' ? 'Large Model' : 'Small Model'}
              </div>
            </div>
          </div>
          
          {/* Price Bar */}
          <div className="mt-6">
            <div className="flex justify-between text-xs text-gray-400 mb-1">
              <span>€0.00</span>
              <span>€0.50</span>
              <span>€0.70</span>
              <span>€1.00</span>
            </div>
            <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
              <div 
                className={`h-full transition-all duration-500 ${priceStatus.bg}`}
                style={{ width: `${Math.min(price * 100, 100)}%` }}
              />
            </div>
          </div>
          
          <div className="mt-4 pt-4 border-t border-gray-100 flex items-center justify-between text-xs text-gray-400">
            <span>Source: {energySource === 'electricity_maps' ? 'Electricity Maps API' : energySource}</span>
            <span className="flex items-center gap-1">
              <Activity className="w-3 h-3" />
              Live
            </span>
          </div>
        </div>

        {/* Savings Card */}
        <div className="bg-gradient-to-br from-green-50 to-emerald-50 rounded-2xl shadow-sm border border-green-100 p-6">
          <div className="flex items-center gap-2 mb-4">
            <TrendingDown className="w-5 h-5 text-green-600" />
            <p className="text-sm font-medium text-green-800">Energy Savings</p>
          </div>
          
          <div className="text-center py-4">
            <div className="text-5xl font-bold text-green-600">
              {modelTier === 'small' ? '66' : '0'}%
            </div>
            <p className="text-sm text-green-700 mt-2">
              {modelTier === 'small' 
                ? 'Using efficient model' 
                : 'Full power mode'}
            </p>
          </div>
          
          <div className="mt-4 pt-4 border-t border-green-200/50 space-y-2">
            <div className="flex items-center gap-2 text-xs text-green-700">
              <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
              Smaller models when expensive
            </div>
            <div className="flex items-center gap-2 text-xs text-green-700">
              <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
              Solar priority enabled
            </div>
          </div>
        </div>
      </div>

      {/* Carbon Metrics Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Emissions */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
          <div className="flex items-center justify-between mb-4">
            <Leaf className="w-8 h-8 text-green-500 bg-green-50 p-1.5 rounded-lg" />
            <span className="text-xs text-gray-400 uppercase tracking-wide">Emissions</span>
          </div>
          <div className="text-3xl font-bold text-gray-900">
            {carbonLoading ? '—' : emissions.toFixed(4)}
            <span className="text-base font-normal text-gray-400 ml-1">g CO₂</span>
          </div>
          <p className="text-xs text-gray-500 mt-2">Since server start</p>
        </div>

        {/* Energy */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
          <div className="flex items-center justify-between mb-4">
            <Zap className="w-8 h-8 text-amber-500 bg-amber-50 p-1.5 rounded-lg" />
            <span className="text-xs text-gray-400 uppercase tracking-wide">Energy</span>
          </div>
          <div className="text-3xl font-bold text-gray-900">
            {carbonLoading ? '—' : (energy * 1000).toFixed(2)}
            <span className="text-base font-normal text-gray-400 ml-1">Wh</span>
          </div>
          <p className="text-xs text-gray-500 mt-2">Total consumption</p>
        </div>

        {/* Runtime */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
          <div className="flex items-center justify-between mb-4">
            <Clock className="w-8 h-8 text-blue-500 bg-blue-50 p-1.5 rounded-lg" />
            <span className="text-xs text-gray-400 uppercase tracking-wide">Uptime</span>
          </div>
          <div className="text-3xl font-bold text-gray-900">
            {carbonLoading ? '—' : Math.floor(duration / 60)}
            <span className="text-base font-normal text-gray-400 ml-1">min</span>
          </div>
          <p className="text-xs text-gray-500 mt-2">Tracking duration</p>
        </div>
      </div>

      {/* How It Works - Compact */}
      <div className="bg-gray-50 rounded-2xl p-6">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-4">How It Works</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-full bg-white shadow-sm flex items-center justify-center text-sm font-bold text-gray-600">1</div>
            <div>
              <p className="font-medium text-gray-800 text-sm">Monitor</p>
              <p className="text-xs text-gray-500">Real-time grid data</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-full bg-white shadow-sm flex items-center justify-center text-sm font-bold text-gray-600">2</div>
            <div>
              <p className="font-medium text-gray-800 text-sm">Adapt</p>
              <p className="text-xs text-gray-500">Switch models by price</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-full bg-white shadow-sm flex items-center justify-center text-sm font-bold text-gray-600">3</div>
            <div>
              <p className="font-medium text-gray-800 text-sm">Save</p>
              <p className="text-xs text-gray-500">Reduce carbon footprint</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
