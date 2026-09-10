import React, { useState, useEffect, useMemo } from 'react';
import Icon from '../../../components/AppIcon';
import { getAqiHistory, getStations } from '../../../utils/api';

const DEFAULT_STATION_OPTIONS = [
  { id: 3409620, name: 'Anand Vihar, Delhi' },
  { id: 3409621, name: 'ITO, Delhi' },
  { id: 3409622, name: 'Punjabi Bagh, Delhi' },
  { id: 3409623, name: 'RK Puram, Delhi' },
  { id: 3409624, name: 'Dwarka Sector 8, Delhi' },
  { id: 3409625, name: 'Noida Sector 62, NCR' },
  { id: 3409626, name: 'Gurugram Sector 51, NCR' },
];

function computeStats(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const n = sorted.length;
  const mean = values.reduce((s, v) => s + v, 0) / n;
  const median = n % 2 === 0 ? (sorted[n / 2 - 1] + sorted[n / 2]) / 2 : sorted[Math.floor(n / 2)];
  const variance = values.reduce((s, v) => s + (v - mean) ** 2, 0) / n;
  const std = Math.sqrt(variance);
  const p25 = sorted[Math.floor(n * 0.25)];
  const p75 = sorted[Math.floor(n * 0.75)];

  const good = values.filter((v) => v <= 50).length;
  const satisfactory = values.filter((v) => v > 50 && v <= 100).length;
  const moderate = values.filter((v) => v > 100 && v <= 200).length;
  const poor = values.filter((v) => v > 200 && v <= 300).length;
  const veryPoor = values.filter((v) => v > 300 && v <= 400).length;
  const severe = values.filter((v) => v > 400).length;

  return {
    mean: mean.toFixed(1), median: median.toFixed(1),
    std: std.toFixed(1), min: sorted[0], max: sorted[n - 1],
    p25: p25.toFixed(1), p75: p75.toFixed(1),
    range: (sorted[n - 1] - sorted[0]).toFixed(1),
    compliance: ((good + satisfactory) / n * 100).toFixed(1),
    distribution: { good, satisfactory, moderate, poor, veryPoor, severe, total: n },
  };
}

const StatisticalSummary = () => {
  const [stationOptions, setStationOptions] = useState(DEFAULT_STATION_OPTIONS);
  const [stationId, setStationId] = useState(3409620);
  const [hours, setHours] = useState(720);
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getStations().then(stations => {
      if (stations && stations.length > 0) {
        setStationOptions(stations.map(s => ({ id: s.id, name: s.name.split(' - ')[0] })));
        if (!stations.some(s => s.id === stationId)) {
          setStationId(stations[0].id);
        }
      }
    }).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    getAqiHistory(stationId, hours)
      .then(setData)
      .catch(() => setData([]))
      .finally(() => setLoading(false));
  }, [stationId, hours]);

  const stats = useMemo(() => computeStats(data.map((d) => d.overall_aqi)), [data]);

  return (
    <div className="bg-card border border-border rounded-xl p-6">
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <Icon name="BarChart3" size={16} className="text-primary" />
          </div>
          <h3 className="text-lg font-semibold text-foreground">Statistical Summary</h3>
        </div>
        <div className="flex gap-2">
          <select
            value={stationId}
            onChange={(e) => setStationId(Number(e.target.value))}
            className="px-3 py-1.5 text-sm border border-border rounded-lg bg-background"
          >
            {STATION_OPTIONS.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <select
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            className="px-3 py-1.5 text-sm border border-border rounded-lg bg-background"
          >
            <option value={168}>7 days</option>
            <option value={720}>30 days</option>
            <option value={2160}>90 days</option>
            <option value={8760}>1 year</option>
          </select>
        </div>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      ) : !stats ? (
        <div className="h-64 flex items-center justify-center text-muted-foreground">No data available</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Descriptive stats */}
          <div>
            <h4 className="font-semibold text-foreground mb-3 flex items-center gap-2">
              <Icon name="Calculator" size={15} /> Descriptive Statistics
            </h4>
            <div className="grid grid-cols-2 gap-3">
              {[
                ['Mean AQI', stats.mean],
                ['Median AQI', stats.median],
                ['Std Deviation', stats.std],
                ['Range', stats.range],
                ['25th Percentile', stats.p25],
                ['75th Percentile', stats.p75],
                ['Min', stats.min],
                ['Max', stats.max],
              ].map(([label, val]) => (
                <div key={label} className="bg-muted/50 rounded-lg p-3">
                  <div className="text-xs text-muted-foreground">{label}</div>
                  <div className="text-lg font-semibold text-foreground">{val}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Distribution */}
          <div>
            <h4 className="font-semibold text-foreground mb-3 flex items-center gap-2">
              <Icon name="Shield" size={15} /> AQI Distribution ({stats.distribution.total} hours)
            </h4>
            <div style={{ display: 'grid', gap: '0.5rem' }}>
              {[
                ['Good (0–50)',         stats.distribution.good,         '#16a34a'],
                ['Satisfactory (51–100)', stats.distribution.satisfactory, '#65a30d'],
                ['Moderate (101–200)',  stats.distribution.moderate,     '#ca8a04'],
                ['Poor (201–300)',      stats.distribution.poor,         '#ea580c'],
                ['Very Poor (301–400)', stats.distribution.veryPoor,     '#dc2626'],
                ['Severe (400+)',       stats.distribution.severe,       '#7c3aed'],
              ].map(([label, count, hexColor]) => {
                const pct = ((count / stats.distribution.total) * 100).toFixed(1);
                const textColor = hexColor;
                return (
                  <div key={label} style={{ display: 'grid', gridTemplateColumns: '140px 1fr 80px', gap: '0.75rem', alignItems: 'center' }}>
                    <div className="text-sm text-muted-foreground">{label}</div>
                    <div className="bg-muted rounded-full h-2" style={{ minWidth: 0 }}>
                      <div className="h-2 rounded-full" style={{ width: `${pct}%`, backgroundColor: hexColor, minWidth: count > 0 ? '4px' : 0 }} />
                    </div>
                    <div className="text-sm font-medium text-right" style={{ color: textColor }}>{count} ({pct}%)</div>
                  </div>
                );
              })}
            </div>
            <div className="mt-4 p-3 bg-muted/50 rounded-lg flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Compliance Rate (Good + Satisfactory)</span>
              <span className={`text-lg font-bold ${Number(stats.compliance) >= 60 ? 'text-green-600' : 'text-destructive'}`}>
                {stats.compliance}%
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default StatisticalSummary;
