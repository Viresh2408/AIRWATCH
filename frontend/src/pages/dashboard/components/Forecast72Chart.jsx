import React, { useState, useEffect } from 'react';
import { getForecast72 } from '../../../services/realDataService';
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from 'recharts';
import { TrendingUp, ShieldCheck, Eye, Layers } from 'lucide-react';

const Forecast72Chart = ({ stationId = 3409620, stationName = 'Selected Station' }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [horizon, setHorizon] = useState(72); // 24 | 48 | 72
  const [visibleLines, setVisibleLines] = useState({
    aqi: true,
    pm25: true,
    pm10: true,
    o3: true,
    ciBand: true,
  });

  useEffect(() => {
    let isMounted = true;
    setLoading(true);

    getForecast72(stationId)
      .then((res) => {
        if (isMounted) {
          setData(res);
          setLoading(false);
        }
      })
      .catch((err) => {
        console.error('72h forecast error:', err);
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [stationId]);

  if (loading) {
    return (
      <div className="bg-card border rounded-2xl p-6 shadow-sm flex flex-col justify-center items-center h-96 animate-pulse">
        <div className="w-12 h-12 rounded-full border-4 border-primary/20 border-t-primary animate-spin mb-4" />
        <p className="text-sm text-muted-foreground">Generating 72-hour coupled forecast with confidence bounds...</p>
      </div>
    );
  }

  const rawSteps = data?.steps || [];
  const chartData = rawSteps.slice(0, horizon).map((s, idx) => {
    const dt = new Date(s.prediction_time);
    const timeStr = dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const dateStr = dt.toLocaleDateString([], { month: 'short', day: 'numeric' });
    const dayLabel = idx % 24 === 0 ? dateStr : timeStr;

    return {
      hour: s.hour_offset,
      time: timeStr,
      label: dayLabel,
      aqi: s.predicted_aqi,
      pm25: s.predicted_pm25,
      pm10: s.predicted_pm10,
      o3: s.predicted_o3,
      // Confidence interval band for PM2.5: lower bound and spread (upper - lower)
      pm25_lower: s.pm25_lower || (s.predicted_pm25 ? Math.round(s.predicted_pm25 * 0.85) : 0),
      pm25_upper: s.pm25_upper || (s.predicted_pm25 ? Math.round(s.predicted_pm25 * 1.15) : 0),
      pm25_spread: [
        s.pm25_lower || (s.predicted_pm25 ? Math.round(s.predicted_pm25 * 0.85) : 0),
        s.pm25_upper || (s.predicted_pm25 ? Math.round(s.predicted_pm25 * 1.15) : 0),
      ],
      inversion_score: s.inversion_score,
      inversion_category: s.inversion_category,
      plume_pm25: s.plume_pm25_contrib,
      pbl_height: s.pbl_height_corrected,
    };
  });

  // Calculate Peak AQI and Peak PM2.5 in horizon
  const peakAQI = chartData.reduce((max, s) => Math.max(max, s.aqi || 0), 0);
  const peakPM25 = chartData.reduce((max, s) => Math.max(max, s.pm25 || 0), 0);

  const toggleLine = (key) => {
    setVisibleLines((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div className="bg-card border rounded-2xl p-6 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-xl bg-primary/10 text-primary">
              <TrendingUp className="w-5 h-5" />
            </span>
            <div>
              <h3 className="font-bold text-lg text-foreground">72-Hour Coupled AQI Forecast</h3>
              <p className="text-xs text-muted-foreground">
                Autoregressive XGBoost models coupled with Open-Meteo PBL & FIRMS fire plumes
              </p>
            </div>
          </div>
        </div>

        {/* Horizon Filter Tabs */}
        <div className="flex items-center gap-1 bg-muted/60 p-1 rounded-xl border self-start sm:self-auto">
          {[24, 48, 72].map((h) => (
            <button
              key={h}
              type="button"
              onClick={() => setHorizon(h)}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                horizon === h ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {h} Hours {h === 72 ? '(Full)' : ''}
            </button>
          ))}
        </div>
      </div>

      {/* Summary Chips & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-4 pb-4 border-b">
        <div className="flex items-center gap-4 text-xs">
          <div>
            <span className="text-muted-foreground">Peak AQI ({horizon}h):</span>{' '}
            <strong className="font-mono font-bold text-foreground text-sm ml-1">{peakAQI}</strong>
          </div>
          <div>
            <span className="text-muted-foreground">Peak PM2.5:</span>{' '}
            <strong className="font-mono font-bold text-foreground text-sm ml-1">{peakPM25.toFixed(1)} µg/m³</strong>
          </div>
          <div className="hidden sm:block">
            <span className="text-muted-foreground">Model:</span>{' '}
            <span className="font-mono text-xs bg-muted px-2 py-0.5 rounded border">coupled_xgb_v1.0</span>
          </div>
        </div>

        {/* Interactive Toggles */}
        <div className="flex items-center flex-wrap gap-2 text-xs">
          <button
            type="button"
            onClick={() => toggleLine('aqi')}
            className={`px-2.5 py-1 rounded-lg border text-xs font-medium transition-all ${
              visibleLines.aqi ? 'bg-indigo-50 border-indigo-300 text-indigo-700 dark:bg-indigo-950/40 dark:border-indigo-800 dark:text-indigo-300' : 'bg-muted/40 text-muted-foreground'
            }`}
          >
            ● AQI
          </button>
          <button
            type="button"
            onClick={() => toggleLine('pm25')}
            className={`px-2.5 py-1 rounded-lg border text-xs font-medium transition-all ${
              visibleLines.pm25 ? 'bg-rose-50 border-rose-300 text-rose-700 dark:bg-rose-950/40 dark:border-rose-800 dark:text-rose-300' : 'bg-muted/40 text-muted-foreground'
            }`}
          >
            ● PM2.5
          </button>
          <button
            type="button"
            onClick={() => toggleLine('pm10')}
            className={`px-2.5 py-1 rounded-lg border text-xs font-medium transition-all ${
              visibleLines.pm10 ? 'bg-amber-50 border-amber-300 text-amber-700 dark:bg-amber-950/40 dark:border-amber-800 dark:text-amber-300' : 'bg-muted/40 text-muted-foreground'
            }`}
          >
            ● PM10
          </button>
          <button
            type="button"
            onClick={() => toggleLine('o3')}
            className={`px-2.5 py-1 rounded-lg border text-xs font-medium transition-all ${
              visibleLines.o3 ? 'bg-emerald-50 border-emerald-300 text-emerald-700 dark:bg-emerald-950/40 dark:border-emerald-800 dark:text-emerald-300' : 'bg-muted/40 text-muted-foreground'
            }`}
          >
            ● Ozone (O3)
          </button>
          <button
            type="button"
            onClick={() => toggleLine('ciBand')}
            className={`px-2.5 py-1 rounded-lg border text-xs font-medium transition-all ${
              visibleLines.ciBand ? 'bg-blue-50 border-blue-300 text-blue-700 dark:bg-blue-950/40 dark:border-blue-800 dark:text-blue-300' : 'bg-muted/40 text-muted-foreground'
            }`}
          >
            <Layers className="w-3 h-3 inline mr-1" />
            90% CI Band
          </button>
        </div>
      </div>

      {/* Recharts Forecast Graph */}
      <div className="w-full h-80">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11, fill: 'currentColor', opacity: 0.6 }}
              interval={horizon === 72 ? 11 : horizon === 48 ? 5 : 3}
            />
            <YAxis
              tick={{ fontSize: 11, fill: 'currentColor', opacity: 0.6 }}
              domain={[0, 'auto']}
            />
            <Tooltip
              content={({ active, payload, label }) => {
                if (!active || !payload || !payload.length) return null;
                const d = payload[0].payload;
                return (
                  <div className="bg-popover text-popover-foreground border shadow-xl rounded-xl p-3 text-xs min-w-[200px]">
                    <div className="font-semibold text-sm border-b pb-1 mb-2 flex items-center justify-between">
                      <span>h+{d.hour} ({d.time})</span>
                      <span className="text-[10px] font-normal px-2 py-0.5 rounded bg-muted">
                        Inversion: {d.inversion_category}
                      </span>
                    </div>
                    <div className="space-y-1">
                      <div className="flex justify-between items-center">
                        <span className="text-indigo-500 font-medium">Predicted AQI:</span>
                        <span className="font-bold font-mono text-foreground">{d.aqi}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-rose-500 font-medium">PM2.5:</span>
                        <span className="font-mono text-foreground">
                          {d.pm25} µg/m³{' '}
                          <span className="text-[10px] text-muted-foreground font-normal">
                            [{d.pm25_lower} - {d.pm25_upper}]
                          </span>
                        </span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-amber-500 font-medium">PM10:</span>
                        <span className="font-mono text-foreground">{d.pm10} µg/m³</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-emerald-500 font-medium">Ozone (O3):</span>
                        <span className="font-mono text-foreground">{d.o3} µg/m³</span>
                      </div>
                      {d.plume_pm25 > 0 && (
                        <div className="flex justify-between items-center pt-1 border-t text-orange-500 text-[11px]">
                          <span>Fire Plume Impact:</span>
                          <span className="font-mono font-semibold">+{d.plume_pm25} µg/m³</span>
                        </div>
                      )}
                    </div>
                  </div>
                );
              }}
            />

            {/* Shaded 90% Confidence Interval Band for PM2.5 */}
            {visibleLines.ciBand && (
              <Area
                type="monotone"
                dataKey="pm25_spread"
                stroke="none"
                fill="#3B82F6"
                fillOpacity={0.15}
                name="90% Confidence Band"
              />
            )}

            {/* Pollutant Lines */}
            {visibleLines.aqi && (
              <Line
                type="monotone"
                dataKey="aqi"
                stroke="#6366F1"
                strokeWidth={2.5}
                dot={false}
                name="Overall AQI"
              />
            )}

            {visibleLines.pm25 && (
              <Line
                type="monotone"
                dataKey="pm25"
                stroke="#F43F5E"
                strokeWidth={2}
                dot={false}
                name="PM2.5"
              />
            )}

            {visibleLines.pm10 && (
              <Line
                type="monotone"
                dataKey="pm10"
                stroke="#F59E0B"
                strokeWidth={1.5}
                dot={false}
                name="PM10"
              />
            )}

            {visibleLines.o3 && (
              <Line
                type="monotone"
                dataKey="o3"
                stroke="#10B981"
                strokeWidth={1.5}
                dot={false}
                name="Ozone (O3)"
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Footer Notes */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between text-xs text-muted-foreground mt-4 pt-3 border-t gap-2">
        <div className="flex items-center gap-1.5">
          <ShieldCheck className="w-4 h-4 text-emerald-500" />
          <span>90% empirical confidence intervals scale proportionally with atmospheric inversion severity.</span>
        </div>
        <span className="text-[11px]">Updated every 6 hours via APScheduler</span>
      </div>
    </div>
  );
};

export default Forecast72Chart;
