import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../../components/ui/Header';
import AQIStationCard from './components/AQIStationCard';
import AQIStatusIndicator from '../../components/ui/AQIStatusIndicator';
import QuickActions from './components/QuickActions';
import AlertsPanel from './components/AlertsPanel';
import InversionGauge from './components/InversionGauge';
import PlumeDispersionMap from './components/PlumeDispersionMap';
import Forecast72Chart from './components/Forecast72Chart';
import CouplingExplainabilityPanel from './components/CouplingExplainabilityPanel';
import { useAirQuality } from '../../context/AirQualityContext';
import { Activity, Flame, ShieldAlert, Cpu, Sparkles, RefreshCw } from 'lucide-react';

const Dashboard = () => {
  const navigate = useNavigate();
  const { enrichedStations, averageAqi, loading, isRefreshing, error, lastUpdated, refresh } = useAirQuality();
  const [selectedStationId, setSelectedStationId] = useState(3409620);
  const [activeCouplingTab, setActiveCouplingTab] = useState('forecast72');

  useEffect(() => {
    if (enrichedStations && enrichedStations.length > 0) {
      if (!enrichedStations.some((s) => s.id === selectedStationId)) {
        setSelectedStationId(enrichedStations[0].id);
      }
    }
  }, [enrichedStations, selectedStationId]);

  const getAQICategory = (aqi) => {
    if (aqi <= 50) return 'Good';
    if (aqi <= 100) return 'Satisfactory';
    if (aqi <= 200) return 'Moderate';
    if (aqi <= 300) return 'Poor';
    if (aqi <= 400) return 'Very Poor';
    return 'Severe';
  };

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <div className="pt-16">
        <div className="max-w-7xl mx-auto px-6 py-8">

          {/* Page Header */}
          <div className="mb-8 relative overflow-hidden rounded-2xl bg-gradient-to-br from-white via-slate-50 to-blue-50/40 dark:from-slate-900 dark:via-slate-900/90 dark:to-blue-950/20 border border-slate-200/80 dark:border-slate-800 p-6 md:p-8 shadow-sm">
            <div className="absolute top-0 right-0 -mt-8 -mr-8 w-64 h-64 bg-blue-400/10 rounded-full blur-3xl pointer-events-none" />
            <div className="absolute bottom-0 left-1/3 -mb-12 w-48 h-48 bg-teal-400/10 rounded-full blur-3xl pointer-events-none" />

            <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
              <div className="space-y-2">
                <div className="flex items-center gap-3 flex-wrap">
                  <h1 className="text-3xl sm:text-4xl md:text-5xl font-black tracking-tight bg-gradient-to-r from-slate-950 via-blue-900 to-indigo-900 dark:from-white dark:via-blue-100 dark:to-teal-200 bg-clip-text text-transparent drop-shadow-sm">
                    AIRWATCH PRO
                  </h1>
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-bold tracking-wider uppercase bg-blue-600/10 text-blue-700 dark:bg-blue-400/10 dark:text-blue-300 border border-blue-600/20 shadow-xs">
                    <Sparkles className="w-3 h-3 text-blue-600 dark:text-blue-400" /> Live Intelligence
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <p className="text-lg sm:text-xl md:text-2xl font-extrabold tracking-tight bg-gradient-to-r from-blue-600 via-indigo-600 to-teal-500 bg-clip-text text-transparent">
                    See the Invisible. Predict the Unseen.
                  </p>
                </div>

                <p className="text-sm sm:text-base text-slate-600 dark:text-slate-300 max-w-3xl leading-relaxed font-normal">
                  <span className="font-semibold text-slate-900 dark:text-white">Delhi NCR’s</span> intelligent air quality platform, transforming{' '}
                  <span className="font-semibold text-slate-800 dark:text-slate-200">atmospheric science</span>,{' '}
                  <span className="font-semibold text-slate-800 dark:text-slate-200">weather intelligence</span>, and{' '}
                  <span className="font-semibold text-slate-800 dark:text-slate-200">pollution dynamics</span> into a clearer view of tomorrow’s air.
                </p>

                {lastUpdated && (
                  <div className="pt-1 flex items-center gap-2">
                    <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-500/20">
                      <span className="relative flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                      </span>
                      Live Synchronized · {lastUpdated.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata' })} IST
                    </span>
                  </div>
                )}
              </div>

              <button
                onClick={refresh}
                disabled={isRefreshing}
                className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-slate-700 dark:text-slate-200 bg-white/80 dark:bg-slate-800/80 hover:bg-white dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-xs hover:shadow-md transition-all self-start md:self-center shrink-0 disabled:opacity-70 active:scale-95"
              >
                <RefreshCw className={`w-4 h-4 text-blue-600 dark:text-blue-400 ${isRefreshing ? 'animate-spin' : ''}`} />
                {isRefreshing ? 'Refreshing...' : 'Refresh Telemetry'}
              </button>
            </div>
          </div>

          {/* Error banner */}
          {error && (
            <div className="mb-6 p-4 bg-destructive/10 border border-destructive/20 rounded-lg text-destructive text-sm">
              {error}
            </div>
          )}

          {/* AQI Overview */}
          {!loading && (
            <div className="mb-8">
              <AQIStatusIndicator
                className="max-w-md"
                averageAqi={averageAqi}
                aqiCategory={getAQICategory(averageAqi)}
              />
            </div>
          )}

          {/* Main Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-8">
            <div className="lg:col-span-2">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-semibold text-foreground">Monitoring Stations</h2>
              </div>

              {loading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {[...Array(6)].map((_, i) => (
                    <div key={i} className="h-48 bg-muted animate-pulse rounded-xl" />
                  ))}
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {enrichedStations.map((station) => (
                    <AQIStationCard
                      key={station.id}
                      station={station}
                      onClick={() => navigate(`/station-details/${station.id}`)}
                    />
                  ))}
                </div>
              )}
            </div>

            <div>
              <QuickActions />
            </div>
          </div>

          {/* Two-Way Coupling & Explainability Suite (SIH PS 26082) */}
          <div className="mb-10">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="p-2 rounded-xl bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
                    <Sparkles className="w-5 h-5" />
                  </span>
                  <h2 className="text-2xl font-bold text-foreground">
                    Atmospheric Intelligence & Forecasting Suite
                  </h2>
                  <span className="hidden sm:inline-flex text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-indigo-500/10 text-indigo-700 border border-indigo-500/20 dark:bg-indigo-950/40 dark:text-indigo-300 dark:border-indigo-800">
                    Physics-AI Coupled
                  </span>
                </div>
                <p className="text-sm text-muted-foreground mt-1">
                  Atmospheric boundary layer feedback, stubble-burning plume advection, and 72-hour multi-pollutant projections
                </p>
              </div>

              {/* Station Selector Dropdown */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground whitespace-nowrap">Station:</span>
                <select
                  value={selectedStationId}
                  onChange={(e) => setSelectedStationId(Number(e.target.value))}
                  className="bg-card border text-foreground text-xs rounded-xl px-3 py-2 font-medium focus:outline-none focus:ring-2 focus:ring-primary shadow-sm"
                >
                  {enrichedStations.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} (AQI {s.overall_aqi || s.currentAQI || '—'})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Navigation Tabs */}
            <div className="flex items-center gap-2 border-b mb-6 overflow-x-auto pb-1">
              {[
                { id: 'forecast72', label: '72-Hour Forecast', icon: Activity },
                { id: 'inversion', label: 'Inversion Gauge', icon: ShieldAlert },
                { id: 'plume', label: 'Fire Plume Dispersion', icon: Flame },
                { id: 'explainability', label: 'Feedback Explainability', icon: Cpu },
              ].map((tab) => {
                const Icon = tab.icon;
                const isActive = activeCouplingTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setActiveCouplingTab(tab.id)}
                    className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold rounded-t-xl transition-all border-b-2 whitespace-nowrap ${
                      isActive
                        ? 'border-primary text-primary bg-primary/5'
                        : 'border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/40'
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                    {tab.label}
                  </button>
                );
              })}
            </div>

            {/* Active Tab Component */}
            <div>
              {activeCouplingTab === 'forecast72' && (
                <Forecast72Chart stationId={selectedStationId} />
              )}
              {activeCouplingTab === 'inversion' && (
                <InversionGauge stationId={selectedStationId} />
              )}
              {activeCouplingTab === 'plume' && (
                <PlumeDispersionMap
                  selectedStationId={selectedStationId}
                  onSelectStation={(id) => setSelectedStationId(id)}
                />
              )}
              {activeCouplingTab === 'explainability' && (
                <CouplingExplainabilityPanel stationId={selectedStationId} />
              )}
            </div>
          </div>

          {/* Nav Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div
              onClick={() => navigate('/station-details/3409476')}
              className="bg-white border rounded-xl p-6 cursor-pointer hover:shadow-lg transition-all group"
            >
              <div className="flex items-center space-x-4 mb-4">
                <div className="w-12 h-12 rounded-xl bg-blue-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                  <div className="w-6 h-6 bg-blue-500 rounded" />
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900">Station Details</h3>
                  <p className="text-sm text-gray-600">Individual station analysis</p>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-2xl font-mono font-bold text-gray-900">{enrichedStations.length}</span>
                <span className="text-gray-500 group-hover:text-blue-500 transition-colors">→</span>
              </div>
            </div>

            <div
              onClick={() => navigate('/historical-analytics')}
              className="bg-white border rounded-xl p-6 cursor-pointer hover:shadow-lg transition-all group"
            >
              <div className="flex items-center space-x-4 mb-4">
                <div className="w-12 h-12 rounded-xl bg-green-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                  <div className="w-6 h-6 bg-green-500 rounded" />
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900">Historical Analytics</h3>
                  <p className="text-sm text-gray-600">Trends and predictions</p>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Real DB data</span>
                <span className="text-gray-500 group-hover:text-green-500 transition-colors">→</span>
              </div>
            </div>

            <div
              onClick={() => navigate('/alerts-management')}
              className="bg-white border rounded-xl p-6 cursor-pointer hover:shadow-lg transition-all group"
            >
              <div className="flex items-center space-x-4 mb-4">
                <div className="w-12 h-12 rounded-xl bg-amber-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                  <div className="w-6 h-6 bg-amber-500 rounded" />
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900">Alert Management</h3>
                  <p className="text-sm text-gray-600">Configure notifications</p>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-amber-600 font-medium">
                  {enrichedStations.filter((s) => s.overall_aqi > 100).length} active alerts
                </span>
                <span className="text-gray-500 group-hover:text-amber-500 transition-colors">→</span>
              </div>
            </div>
          </div>

          {/* Alerts Panel */}
          <AlertsPanel stations={enrichedStations} />
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
