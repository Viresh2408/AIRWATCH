import React, { useState, useEffect } from 'react';
import {
  AreaChart, Area, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import Icon from '../../../components/AppIcon';
import { getAqiHistory, getStations } from '../../../utils/api';

const COLORS = {
  AQI: '#3B82F6', pm25: '#EF4444', pm10: '#F59E0B',
  no2: '#8B5CF6', so2: '#06B6D4', o3: '#10B981',
};

const TrendAnalysisChart = () => {
  const [stationOptions, setStationOptions] = useState([
    { id: 3409620, name: 'Anand Vihar, Delhi' },
    { id: 3409621, name: 'ITO, Delhi' },
    { id: 3409622, name: 'Punjabi Bagh, Delhi' },
    { id: 3409623, name: 'RK Puram, Delhi' },
    { id: 3409624, name: 'Dwarka Sector 8, Delhi' },
    { id: 3409625, name: 'Noida Sector 62, NCR' },
    { id: 3409626, name: 'Gurugram Sector 51, NCR' },
  ]);
  const [stationId, setStationId] = useState(3409620);
  const [hours, setHours] = useState(168);
  const [chartType, setChartType] = useState('area');
  const [pollutants, setPollutants] = useState(['AQI', 'pm25', 'pm10']);
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

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
    setError(null);
    getAqiHistory(stationId, hours)
      .then((rows) => {
        setData(
          rows.map((r) => ({
            time: new Date(r.datetime).toLocaleDateString('en-IN', {
              month: 'short', day: 'numeric', hour: '2-digit', timeZone: 'Asia/Kolkata',
            }),
            AQI: r.overall_aqi,
            ...Object.fromEntries(
              Object.entries(r.pollutants).map(([k, v]) => [k, parseFloat(v.toFixed(1))])
            ),
          }))
        );
      })
      .catch(() => setError('Failed to load trend data'))
      .finally(() => setLoading(false));
  }, [stationId, hours]);

  const togglePollutant = (p) =>
    setPollutants((prev) => prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]);

  const ChartComp = chartType === 'area' ? AreaChart : LineChart;
  const DataComp = chartType === 'area' ? Area : Line;

  const stats = data.length
    ? {
        avg: Math.round(data.reduce((s, d) => s + d.AQI, 0) / data.length),
        max: Math.max(...data.map((d) => d.AQI)),
        min: Math.min(...data.map((d) => d.AQI)),
      }
    : null;

  return (
    <div className="bg-card border border-border rounded-xl p-6">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <Icon name="TrendingUp" size={16} className="text-primary" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-foreground">Trend Analysis</h3>
            <p className="text-sm text-muted-foreground">Historical measured data</p>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          <select
            value={stationId}
            onChange={(e) => setStationId(Number(e.target.value))}
            className="px-3 py-1.5 text-sm border border-border rounded-lg bg-background"
          >
            {stationOptions.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          <select
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            className="px-3 py-1.5 text-sm border border-border rounded-lg bg-background"
          >
            <option value={24}>24 hours</option>
            <option value={72}>3 days</option>
            <option value={168}>7 days</option>
            <option value={720}>30 days</option>
            <option value={2160}>90 days</option>
          </select>
          <button
            onClick={() => setChartType(chartType === 'area' ? 'line' : 'area')}
            className="px-3 py-1.5 text-sm border border-border rounded-lg bg-background hover:bg-muted"
          >
            {chartType === 'area' ? 'Line' : 'Area'}
          </button>
        </div>
      </div>

      {/* Pollutant toggles */}
      <div className="flex gap-2 mb-4 flex-wrap">
        {Object.keys(COLORS).map((p) => (
          <button
            key={p}
            onClick={() => togglePollutant(p)}
            className={`px-3 py-1 text-xs rounded-full border transition-colors ${
              pollutants.includes(p)
                ? 'text-white border-transparent'
                : 'bg-background text-muted-foreground border-border'
            }`}
            style={pollutants.includes(p) ? { backgroundColor: COLORS[p], borderColor: COLORS[p] } : {}}
          >
            {p.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Chart Legend */}
      <div className="mb-4 p-3 bg-blue-50 border border-blue-100 rounded-lg">
        <p className="text-xs text-blue-800 font-medium mb-2">Chart Legend:</p>
        <div className="flex flex-wrap gap-4 text-xs text-blue-700">
          <span className="flex items-center gap-1">
            <span className="w-6 h-0.5 bg-blue-500 rounded"></span>
            AQI (Air Quality Index) - Overall air quality
          </span>
          <span className="flex items-center gap-1">
            <span className="w-6 h-0.5 bg-red-500 rounded"></span>
            PM2.5 - Fine particulate matter
          </span>
          <span className="flex items-center gap-1">
            <span className="w-6 h-0.5 bg-yellow-500 rounded"></span>
            PM10 - Coarse particulate matter
          </span>
        </div>
      </div>

      {loading ? (
        <div className="h-80 flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      ) : error ? (
        <div className="h-80 flex items-center justify-center text-destructive">{error}</div>
      ) : data.length === 0 ? (
        <div className="h-80 flex items-center justify-center text-muted-foreground">No data for this period</div>
      ) : (
        <ResponsiveContainer width="100%" height={380}>
          <ChartComp data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="time" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend />
            {pollutants.map((p) => (
              <DataComp
                key={p}
                type="monotone"
                dataKey={p}
                stroke={COLORS[p]}
                fill={chartType === 'area' ? `${COLORS[p]}30` : undefined}
                strokeWidth={2}
                dot={false}
              />
            ))}
          </ChartComp>
        </ResponsiveContainer>
      )}

      {stats && (
        <div className="grid grid-cols-3 gap-4 mt-6 pt-4 border-t border-border text-center">
          <div><div className="text-2xl font-bold">{stats.avg}</div><div className="text-sm text-muted-foreground">Avg AQI</div></div>
          <div><div className="text-2xl font-bold text-destructive">{stats.max}</div><div className="text-sm text-muted-foreground">Peak AQI</div></div>
          <div><div className="text-2xl font-bold text-green-600">{stats.min}</div><div className="text-sm text-muted-foreground">Lowest AQI</div></div>
        </div>
      )}
    </div>
  );
};

export default TrendAnalysisChart;
