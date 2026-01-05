'use client';

import { useQuery } from '@tanstack/react-query';
import { getCarbonMetrics, getQueueStatus, getHealth } from '@/lib/api';
import { Leaf, Zap, Clock, Server, TrendingDown } from 'lucide-react';

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

  const { data: healthData } = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 10000,
  });

  const emissions = carbonData?.emissions_g ?? 0;
  const energy = carbonData?.energy_kwh ?? 0;
  const duration = carbonData?.duration_seconds ?? 0;
  const profile = healthData?.profile ?? 'unknown';
  const modelTier = queueData?.llm_tier ?? 'small';
  const price = queueData?.energy?.price_eur ?? 0;

  // Calculate estimated savings (assume large model uses 3x more energy)
  const estimatedSavingsPercent = modelTier === 'small' ? 66 : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center">
          <Leaf className="w-6 h-6 mr-2 text-green-600" />
          Carbon & Sustainability
        </h1>
        <p className="text-gray-600 mt-1">
          Track the environmental impact of your AI-powered task scheduling
        </p>
      </div>

      {/* Main metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Emissions */}
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-500">CO₂ Emissions</span>
            <Leaf className="w-5 h-5 text-green-500" />
          </div>
          <div className="text-3xl font-bold text-gray-900">
            {carbonLoading ? '...' : emissions.toFixed(4)}
            <span className="text-lg text-gray-500 ml-1">g</span>
          </div>
          <p className="text-xs text-gray-500 mt-2">
            Total CO₂ equivalent since server start
          </p>
        </div>

        {/* Energy */}
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-500">Energy Used</span>
            <Zap className="w-5 h-5 text-yellow-500" />
          </div>
          <div className="text-3xl font-bold text-gray-900">
            {carbonLoading ? '...' : (energy * 1000).toFixed(4)}
            <span className="text-lg text-gray-500 ml-1">Wh</span>
          </div>
          <p className="text-xs text-gray-500 mt-2">
            Total energy consumption
          </p>
        </div>

        {/* Duration */}
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-500">Runtime</span>
            <Clock className="w-5 h-5 text-blue-500" />
          </div>
          <div className="text-3xl font-bold text-gray-900">
            {carbonLoading ? '...' : Math.floor(duration / 60)}
            <span className="text-lg text-gray-500 ml-1">min</span>
          </div>
          <p className="text-xs text-gray-500 mt-2">
            CodeCarbon tracking duration
          </p>
        </div>
      </div>

      {/* Deployment Profile */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="font-semibold text-gray-900 mb-4 flex items-center">
          <Server className="w-5 h-5 mr-2 text-gray-500" />
          Deployment Profile
        </h2>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-gray-600">Active Profile</span>
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                profile === 'eco' 
                  ? 'bg-green-100 text-green-700' 
                  : profile === 'fast'
                  ? 'bg-blue-100 text-blue-700'
                  : 'bg-gray-100 text-gray-700'
              }`}>
                {profile === 'eco' ? '🌱 Eco' : profile === 'fast' ? '🚀 Fast' : profile}
              </span>
            </div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-gray-600">Current Model</span>
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                modelTier === 'large' 
                  ? 'bg-blue-100 text-blue-700' 
                  : 'bg-green-100 text-green-700'
              }`}>
                {modelTier === 'large' ? '🚀 Large (GPT-4)' : '🌱 Small (GPT-3.5)'}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-600">Energy Price</span>
              <span className="text-gray-900 font-medium">€{price.toFixed(2)}/kWh</span>
            </div>
          </div>

          <div className="bg-gray-50 rounded-lg p-4">
            <h3 className="text-sm font-medium text-gray-700 mb-2">Profile Settings</h3>
            <table className="w-full text-sm">
              <tbody>
                <tr>
                  <td className="text-gray-500 py-1">Price Threshold</td>
                  <td className="text-right font-medium">€0.70</td>
                </tr>
                <tr>
                  <td className="text-gray-500 py-1">Solar Priority</td>
                  <td className="text-right font-medium">Enabled</td>
                </tr>
                <tr>
                  <td className="text-gray-500 py-1">Queue Deferral</td>
                  <td className="text-right font-medium">When expensive</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Energy Savings */}
      <div className="bg-gradient-to-r from-green-50 to-emerald-50 rounded-lg shadow p-6 border border-green-200">
        <h2 className="font-semibold text-green-800 mb-4 flex items-center">
          <TrendingDown className="w-5 h-5 mr-2" />
          Energy-Aware Savings
        </h2>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <p className="text-green-700 mb-4">
              By using energy-aware model switching, Planner AI reduces computational 
              load during expensive energy periods.
            </p>
            <ul className="space-y-2 text-sm text-green-700">
              <li className="flex items-center">
                <span className="w-2 h-2 bg-green-500 rounded-full mr-2"></span>
                Uses smaller models when electricity is expensive
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-green-500 rounded-full mr-2"></span>
                Prioritizes processing when solar is available
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-green-500 rounded-full mr-2"></span>
                Queues non-urgent tasks for off-peak hours
              </li>
            </ul>
          </div>
          
          <div className="flex items-center justify-center">
            <div className="text-center">
              <div className="text-5xl font-bold text-green-600">
                {estimatedSavingsPercent}%
              </div>
              <div className="text-sm text-green-700 mt-1">
                Estimated energy savings
              </div>
              <div className="text-xs text-green-600 mt-2">
                (when using small model tier)
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* How it works */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="font-semibold text-gray-900 mb-4">How Energy-Aware Scheduling Works</h2>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="border border-gray-200 rounded-lg p-4">
            <div className="text-2xl mb-2">📊</div>
            <h3 className="font-medium text-gray-900">1. Monitor Energy</h3>
            <p className="text-sm text-gray-600 mt-1">
              Real-time electricity price and solar availability from grid API
            </p>
          </div>
          
          <div className="border border-gray-200 rounded-lg p-4">
            <div className="text-2xl mb-2">⚡</div>
            <h3 className="font-medium text-gray-900">2. Make Decisions</h3>
            <p className="text-sm text-gray-600 mt-1">
              Switch between large/small models based on €0.70 threshold
            </p>
          </div>
          
          <div className="border border-gray-200 rounded-lg p-4">
            <div className="text-2xl mb-2">🌱</div>
            <h3 className="font-medium text-gray-900">3. Reduce Impact</h3>
            <p className="text-sm text-gray-600 mt-1">
              Queue tasks during expensive periods, process when energy is cheap
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
