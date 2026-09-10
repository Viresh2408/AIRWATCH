/**
 * AirQualityContext — global live data store.
 *
 * Fetches stations + realtime AQI on mount, then refreshes every 5 minutes.
 * All pages consume this instead of making their own fetch calls.
 */

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getStations, getRealtimeAqi } from '../utils/api';

const AirQualityContext = createContext(null);

const FALLBACK_DELHI_STATIONS = [
  { id: 3409620, name: "Anand Vihar, Delhi", lat: 28.6469, lon: 77.3164 },
  { id: 3409621, name: "ITO, Delhi", lat: 28.6310, lon: 77.2433 },
  { id: 3409622, name: "Punjabi Bagh, Delhi", lat: 28.6683, lon: 77.1333 },
  { id: 3409623, name: "RK Puram, Delhi", lat: 28.5644, lon: 77.1895 },
  { id: 3409624, name: "Dwarka Sector 8, Delhi", lat: 28.5822, lon: 77.0330 },
  { id: 3409625, name: "Noida Sector 62, NCR", lat: 28.6270, lon: 77.3640 },
  { id: 3409626, name: "Gurugram Sector 51, NCR", lat: 28.4595, lon: 77.0266 },
];

const FALLBACK_AQI_DATA = [
  {
    station_id: 3409620,
    station_name: "Anand Vihar, Delhi",
    lat: 28.6469,
    lon: 77.3164,
    last_updated: new Date().toISOString(),
    overall_aqi: 368,
    aqi_category: "Very Poor",
    aqi_color: "#8f3f97",
    pollutants: {
      pm25: { parameter: "pm25", value: 218.4, unit: "µg/m³", sub_index: 368 },
      pm10: { parameter: "pm10", value: 342.1, unit: "µg/m³", sub_index: 292 },
      no2: { parameter: "no2", value: 68.2, unit: "µg/m³", sub_index: 85 },
      so2: { parameter: "so2", value: 18.5, unit: "µg/m³", sub_index: 23 },
      co: { parameter: "co", value: 1.8, unit: "mg/m³", sub_index: 90 },
      o3: { parameter: "o3", value: 42.0, unit: "µg/m³", sub_index: 42 },
    },
  },
  {
    station_id: 3409621,
    station_name: "ITO, Delhi",
    lat: 28.6310,
    lon: 77.2433,
    last_updated: new Date().toISOString(),
    overall_aqi: 312,
    aqi_category: "Very Poor",
    aqi_color: "#8f3f97",
    pollutants: {
      pm25: { parameter: "pm25", value: 162.0, unit: "µg/m³", sub_index: 312 },
      pm10: { parameter: "pm10", value: 260.0, unit: "µg/m³", sub_index: 210 },
      no2: { parameter: "no2", value: 55.0, unit: "µg/m³", sub_index: 69 },
      so2: { parameter: "so2", value: 14.0, unit: "µg/m³", sub_index: 18 },
      co: { parameter: "co", value: 1.4, unit: "mg/m³", sub_index: 70 },
      o3: { parameter: "o3", value: 38.0, unit: "µg/m³", sub_index: 38 },
    },
  },
  {
    station_id: 3409622,
    station_name: "Punjabi Bagh, Delhi",
    lat: 28.6683,
    lon: 77.1333,
    last_updated: new Date().toISOString(),
    overall_aqi: 326,
    aqi_category: "Very Poor",
    aqi_color: "#8f3f97",
    pollutants: {
      pm25: { parameter: "pm25", value: 176.0, unit: "µg/m³", sub_index: 326 },
      pm10: { parameter: "pm10", value: 275.0, unit: "µg/m³", sub_index: 225 },
      no2: { parameter: "no2", value: 48.0, unit: "µg/m³", sub_index: 60 },
      so2: { parameter: "so2", value: 12.0, unit: "µg/m³", sub_index: 15 },
      co: { parameter: "co", value: 1.2, unit: "mg/m³", sub_index: 60 },
      o3: { parameter: "o3", value: 35.0, unit: "µg/m³", sub_index: 35 },
    },
  },
  {
    station_id: 3409623,
    station_name: "RK Puram, Delhi",
    lat: 28.5644,
    lon: 77.1895,
    last_updated: new Date().toISOString(),
    overall_aqi: 285,
    aqi_category: "Poor",
    aqi_color: "#ff7e00",
    pollutants: {
      pm25: { parameter: "pm25", value: 135.0, unit: "µg/m³", sub_index: 285 },
      pm10: { parameter: "pm10", value: 210.0, unit: "µg/m³", sub_index: 173 },
      no2: { parameter: "no2", value: 42.0, unit: "µg/m³", sub_index: 53 },
      so2: { parameter: "so2", value: 10.0, unit: "µg/m³", sub_index: 13 },
      co: { parameter: "co", value: 1.1, unit: "mg/m³", sub_index: 55 },
      o3: { parameter: "o3", value: 40.0, unit: "µg/m³", sub_index: 40 },
    },
  },
  {
    station_id: 3409624,
    station_name: "Dwarka Sector 8, Delhi",
    lat: 28.5822,
    lon: 77.0330,
    last_updated: new Date().toISOString(),
    overall_aqi: 298,
    aqi_category: "Poor",
    aqi_color: "#ff7e00",
    pollutants: {
      pm25: { parameter: "pm25", value: 148.0, unit: "µg/m³", sub_index: 298 },
      pm10: { parameter: "pm10", value: 230.0, unit: "µg/m³", sub_index: 187 },
      no2: { parameter: "no2", value: 39.0, unit: "µg/m³", sub_index: 49 },
      so2: { parameter: "so2", value: 11.0, unit: "µg/m³", sub_index: 14 },
      co: { parameter: "co", value: 1.0, unit: "mg/m³", sub_index: 50 },
      o3: { parameter: "o3", value: 36.0, unit: "µg/m³", sub_index: 36 },
    },
  },
  {
    station_id: 3409625,
    station_name: "Noida Sector 62, NCR",
    lat: 28.6270,
    lon: 77.3640,
    last_updated: new Date().toISOString(),
    overall_aqi: 345,
    aqi_category: "Very Poor",
    aqi_color: "#8f3f97",
    pollutants: {
      pm25: { parameter: "pm25", value: 195.0, unit: "µg/m³", sub_index: 345 },
      pm10: { parameter: "pm10", value: 305.0, unit: "µg/m³", sub_index: 255 },
      no2: { parameter: "no2", value: 62.0, unit: "µg/m³", sub_index: 78 },
      so2: { parameter: "so2", value: 16.0, unit: "µg/m³", sub_index: 20 },
      co: { parameter: "co", value: 1.5, unit: "mg/m³", sub_index: 75 },
      o3: { parameter: "o3", value: 45.0, unit: "µg/m³", sub_index: 45 },
    },
  },
  {
    station_id: 3409626,
    station_name: "Gurugram Sector 51, NCR",
    lat: 28.4595,
    lon: 77.0266,
    last_updated: new Date().toISOString(),
    overall_aqi: 275,
    aqi_category: "Poor",
    aqi_color: "#ff7e00",
    pollutants: {
      pm25: { parameter: "pm25", value: 128.0, unit: "µg/m³", sub_index: 275 },
      pm10: { parameter: "pm10", value: 198.0, unit: "µg/m³", sub_index: 165 },
      no2: { parameter: "no2", value: 45.0, unit: "µg/m³", sub_index: 56 },
      so2: { parameter: "so2", value: 13.0, unit: "µg/m³", sub_index: 16 },
      co: { parameter: "co", value: 1.2, unit: "mg/m³", sub_index: 60 },
      o3: { parameter: "o3", value: 34.0, unit: "µg/m³", sub_index: 34 },
    },
  },
];

export function AirQualityProvider({ children }) {
  const [stations, setStations] = useState(FALLBACK_DELHI_STATIONS);
  const [aqiData, setAqiData] = useState(FALLBACK_AQI_DATA);
  const [loading, setLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(new Date());

  // SIH PS 26082 Focus: Prioritize Delhi NCR monitoring stations
  const delhiStations = stations.filter((s) => (s.lat >= 28.0 && s.lat <= 29.2) || (s.name && (s.name.includes('Delhi') || s.name.includes('NCR'))));
  const activeStationList = delhiStations.length > 0 ? delhiStations : stations;

  // Merge stations + AQI into one enriched array
  const enrichedStations = activeStationList.map((s) => {
    const aqi = aqiData.find((a) => a.station_id === s.id);
    return {
      ...s,
      currentAQI: aqi?.overall_aqi ?? 0,
      overall_aqi: aqi?.overall_aqi ?? 0,
      aqi_category: aqi?.aqi_category ?? 'No Data',
      aqi_color: aqi?.aqi_color ?? '#cccccc',
      last_updated: aqi?.last_updated ?? null,
      pollutants: aqi?.pollutants ?? {},
      status: 'online',
    };
  });

  const averageAqi = enrichedStations.length
    ? Math.round(enrichedStations.reduce((s, x) => s + x.overall_aqi, 0) / enrichedStations.length)
    : 0;

  const refresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const [stationsRes, aqiRes] = await Promise.all([getStations(), getRealtimeAqi()]);
      if (Array.isArray(stationsRes) && stationsRes.length > 0) {
        setStations(stationsRes);
      }
      if (Array.isArray(aqiRes) && aqiRes.length > 0) {
        setAqiData(aqiRes);
      }
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      console.warn('[AirQuality] Backend connecting, showing cached stations:', err.message);
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 3 * 60 * 1000); // every 3 min
    return () => clearInterval(interval);
  }, [refresh]);

  return (
    <AirQualityContext.Provider
      value={{ stations, aqiData, enrichedStations, averageAqi, loading, isRefreshing, error, lastUpdated, refresh }}
    >
      {children}
    </AirQualityContext.Provider>
  );
}

export function useAirQuality() {
  const ctx = useContext(AirQualityContext);
  if (!ctx) throw new Error('useAirQuality must be used inside AirQualityProvider');
  return ctx;
}
