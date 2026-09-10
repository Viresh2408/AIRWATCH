import React, { useState, useEffect } from 'react';
import { getInversionTimeline } from '../../../services/realDataService';
import { AlertTriangle, Clock, ArrowDownRight, ArrowUpRight, Info, ShieldAlert } from 'lucide-react';

const CATEGORY_COLORS = {
  None: '#10B981',      // Emerald green
  Weak: '#06B6D4',      // Cyan
  Moderate: '#F59E0B',  // Amber
  Strong: '#F97316',    // Orange
  Severe: '#EF4444',    // Red
};

const CATEGORY_BG = {
  None: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800',
  Weak: 'bg-cyan-50 text-cyan-700 border-cyan-200 dark:bg-cyan-950/40 dark:text-cyan-300 dark:border-cyan-800',
  Moderate: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800',
  Strong: 'bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-950/40 dark:text-orange-300 dark:border-orange-800',
  Severe: 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800 animate-pulse',
};

const InversionGauge = ({ stationId = 3409620, stationName = 'Selected Station', station = null }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedPointIndex, setSelectedPointIndex] = useState(0);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);

    getInversionTimeline(stationId, 48, station)
      .then((res) => {
        if (isMounted) {
          setData(res);
          setSelectedPointIndex(0);
          setLoading(false);
        }
      })
      .catch((err) => {
        console.error('Inversion fetch error:', err);
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [stationId, station]);

  if (loading) {
    return (
      <div className="bg-card border rounded-2xl p-6 shadow-sm flex flex-col justify-center items-center h-80 animate-pulse">
        <div className="w-12 h-12 rounded-full border-4 border-primary/20 border-t-primary animate-spin mb-4" />
        <p className="text-sm text-muted-foreground">Calculating atmospheric inversion index...</p>
      </div>
    );
  }

  const timeline = data?.timeline || [];
  const currentPoint = timeline[selectedPointIndex] || timeline[0] || {
    score: 0.65,
    category: 'Moderate',
    pbl_height: 380,
    dpbl_dt: -45,
    components: { base_score: 0.45, trend_bonus: 0.1, tod_bonus: 0.1 },
  };

  const score = currentPoint.score ?? 0;
  const category = currentPoint.category || 'Moderate';
  const pblHeight = currentPoint.pbl_height ?? 400;
  const dpbl = currentPoint.dpbl_dt;
  const activeColor = CATEGORY_COLORS[category] || '#F59E0B';

  // SVG Gauge Calculations: 180-degree arc from 180° to 0°
  const radius = 85;
  const strokeWidth = 14;
  const circumference = Math.PI * radius; // half circle length
  const strokeDashoffset = circumference - circumference * Math.min(1, Math.max(0, score));

  // Needle angle: from -90 deg (score=0) to +90 deg (score=1)
  const needleAngle = -90 + score * 180;

  return (
    <div className="bg-card border rounded-2xl p-6 shadow-sm relative overflow-hidden">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-6">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-xl bg-amber-500/10 text-amber-600 dark:text-amber-400">
              <ShieldAlert className="w-5 h-5" />
            </span>
            <h3 className="font-bold text-lg text-foreground">Atmospheric Inversion Gauge</h3>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Planetary Boundary Layer (PBL) suppression & aerosol trapping severity
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className={`text-xs font-semibold px-3 py-1.5 rounded-full border ${CATEGORY_BG[category]}`}>
            {category} Inversion ({Math.round(score * 100)}%)
          </span>
        </div>
      </div>

      {/* Main Gauge Visual + Readouts */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-center">
        {/* Semi-circular Radial Gauge */}
        <div className="md:col-span-6 flex flex-col items-center justify-center relative">
          <svg className="w-64 h-36 overflow-visible" viewBox="0 0 200 110">
            {/* Background Arc */}
            <path
              d="M 15 100 A 85 85 0 0 1 185 100"
              fill="none"
              stroke="currentColor"
              strokeWidth={strokeWidth}
              className="text-muted/20"
              strokeLinecap="round"
            />
            {/* Value Colored Arc */}
            <path
              d="M 15 100 A 85 85 0 0 1 185 100"
              fill="none"
              stroke={activeColor}
              strokeWidth={strokeWidth}
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
              className="transition-all duration-700 ease-out"
            />

            {/* Threshold Ticks */}
            {[0, 0.25, 0.5, 0.75, 0.9, 1].map((val, idx) => {
              const angle = (-180 + val * 180) * (Math.PI / 180);
              const innerR = radius - 18;
              const outerR = radius - 8;
              const x1 = 100 + innerR * Math.cos(angle);
              const y1 = 100 + innerR * Math.sin(angle);
              const x2 = 100 + outerR * Math.cos(angle);
              const y2 = 100 + outerR * Math.sin(angle);
              return (
                <line
                  key={idx}
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke="currentColor"
                  strokeWidth="1.5"
                  className="text-muted-foreground/40"
                />
              );
            })}

            {/* Needle Pivot Indicator */}
            <g transform={`translate(100, 100) rotate(${needleAngle})`} className="transition-transform duration-700 ease-out">
              <polygon points="-3,0 3,0 0,-76" fill={activeColor} />
              <circle cx="0" cy="0" r="7" fill={activeColor} />
              <circle cx="0" cy="0" r="3" fill="#FFFFFF" />
            </g>
          </svg>

          {/* Value Labels */}
          <div className="text-center mt-1">
            <div className="text-3xl font-extrabold font-mono text-foreground tracking-tight">
              {score.toFixed(2)}
              <span className="text-xs text-muted-foreground font-sans font-normal ml-1">/ 1.0</span>
            </div>
            <p className="text-xs text-muted-foreground">Inversion Index Score</p>
          </div>
        </div>

        {/* Telemetry Cards Grid */}
        <div className="md:col-span-6 grid grid-cols-2 gap-3">
          <div className="bg-muted/40 border border-border/60 rounded-xl p-3">
            <span className="text-xs text-muted-foreground">Boundary Layer (PBL)</span>
            <div className="text-xl font-bold font-mono text-foreground mt-1">
              {Math.round(pblHeight)}{' '}
              <span className="text-xs font-normal text-muted-foreground">m AGL</span>
            </div>
            <div className="text-[11px] text-muted-foreground mt-0.5 flex items-center gap-1">
              {pblHeight < 200 ? (
                <span className="text-rose-500 font-medium">Critical (&lt;200m)</span>
              ) : pblHeight < 500 ? (
                <span className="text-amber-500 font-medium">Restricted (&lt;500m)</span>
              ) : (
                <span className="text-emerald-500 font-medium">Open Ventilation</span>
              )}
            </div>
          </div>

          <div className="bg-muted/40 border border-border/60 rounded-xl p-3">
            <span className="text-xs text-muted-foreground">PBL Collapse Rate</span>
            <div className="text-xl font-bold font-mono text-foreground mt-1 flex items-center gap-1">
              {dpbl !== null && dpbl !== undefined ? (
                <>
                  {dpbl < 0 ? (
                    <ArrowDownRight className="w-4 h-4 text-rose-500" />
                  ) : (
                    <ArrowUpRight className="w-4 h-4 text-emerald-500" />
                  )}
                  {Math.abs(Math.round(dpbl))}
                </>
              ) : (
                '0'
              )}
              <span className="text-xs font-normal text-muted-foreground">m/h</span>
            </div>
            <div className="text-[11px] text-muted-foreground mt-0.5">
              {dpbl && dpbl < -50 ? (
                <span className="text-rose-500 font-medium">Rapid Collapse</span>
              ) : (
                <span>Stable Transition</span>
              )}
            </div>
          </div>

          <div className="bg-muted/40 border border-border/60 rounded-xl p-3">
            <span className="text-xs text-muted-foreground">Pre-Dawn Risk</span>
            <div className="text-sm font-semibold text-foreground mt-1 flex items-center gap-1">
              <Clock className="w-3.5 h-3.5 text-indigo-500" />
              01:00 – 06:00 IST
            </div>
            <div className="text-[11px] text-muted-foreground mt-0.5">
              {currentPoint?.components?.tod_bonus > 0 ? (
                <span className="text-indigo-600 dark:text-indigo-400 font-medium">+0.10 Active Bonus</span>
              ) : (
                <span>Off-Peak Hours</span>
              )}
            </div>
          </div>

          <div className="bg-muted/40 border border-border/60 rounded-xl p-3">
            <span className="text-xs text-muted-foreground">Peak 48h Severity</span>
            <div className="text-sm font-semibold text-foreground mt-1 flex items-center gap-1">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
              {data?.peak_category || 'Strong'} ({data?.peak_score?.toFixed(2) || '0.78'})
            </div>
            <div className="text-[11px] text-muted-foreground mt-0.5 truncate">
              {data?.peak_time ? new Date(data.peak_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Tonight'}
            </div>
          </div>
        </div>
      </div>

      {/* 48-Hour Inversion Timeline Scrub Bar */}
      <div className="mt-6 pt-4 border-t">
        <div className="flex items-center justify-between text-xs text-muted-foreground mb-2">
          <span className="font-medium text-foreground">Inversion Trajectory (Next 48 Hours)</span>
          <span>Click any hour to inspect</span>
        </div>

        <div className="flex items-end gap-1 h-16 w-full bg-muted/20 p-2 rounded-xl border overflow-x-auto">
          {timeline.slice(0, 48).map((point, idx) => {
            const ptScore = point.score ?? 0;
            const ptCat = point.category || 'None';
            const barHeight = Math.max(12, Math.round(ptScore * 100));
            const isSelected = idx === selectedPointIndex;
            const ptColor = CATEGORY_COLORS[ptCat] || '#9CA3AF';
            const dt = new Date(point.datetime);
            const label = dt.getHours() + ':00';

            return (
              <button
                key={idx}
                type="button"
                onClick={() => setSelectedPointIndex(idx)}
                className={`flex-1 min-w-[10px] h-full flex flex-col justify-end items-center group relative transition-transform ${
                  isSelected ? 'scale-110 z-10' : 'opacity-80 hover:opacity-100'
                }`}
                title={`${label}: Score ${ptScore.toFixed(2)} (${ptCat}), PBL ${Math.round(point.pbl_height)}m`}
              >
                <div
                  style={{ height: `${barHeight}%`, backgroundColor: ptColor }}
                  className={`w-full rounded-t-sm transition-all duration-300 ${
                    isSelected ? 'ring-2 ring-foreground ring-offset-1' : ''
                  }`}
                />
              </button>
            );
          })}
        </div>
        <div className="flex justify-between text-[11px] text-muted-foreground mt-1 px-1">
          <span>Now</span>
          <span>+12h</span>
          <span>+24h</span>
          <span>+36h</span>
          <span>+48h</span>
        </div>
      </div>

      {/* Educational Callout */}
      <div className="mt-4 p-3 rounded-xl bg-blue-50/60 dark:bg-blue-950/20 border border-blue-200/60 dark:border-blue-900/40 text-xs text-blue-900 dark:text-blue-300 flex items-start gap-2">
        <Info className="w-4 h-4 text-blue-600 dark:text-blue-400 mt-0.5 shrink-0" />
        <p className="leading-relaxed">
          <strong className="font-semibold">Indo-Gangetic Plain Physics:</strong> During Delhi winter, night-time radiative cooling suppresses the mixing layer below 200m. Trapped surface aerosols absorb & scatter solar flux, causing ground cooling that delays PBL lifting the following morning (two-way feedback loop).
        </p>
      </div>
    </div>
  );
};

export default InversionGauge;
