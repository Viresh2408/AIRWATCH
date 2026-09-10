import React, { useState, useEffect } from 'react';
import Icon from '../../../components/AppIcon';
import { useNavigate } from 'react-router-dom';
import { getPredictions } from '../../../utils/api';

const AQIStationCard = ({ station, className = '' }) => {
  const navigate = useNavigate();
  const [isExpanded, setIsExpanded] = useState(false);
  const [currentReading, setCurrentReading] = useState(station?.currentAQI || 0);
  const [prediction, setPrediction] = useState(null);
  const [loadingPred, setLoadingPred] = useState(false);

  const getAQIStatus = (value) => {
    if (value <= 50) return { status: 'good', label: 'Good', color: 'text-green-600', bg: 'bg-green-50', border: 'border-green-200' };
    if (value <= 100) return { status: 'moderate', label: 'Moderate', color: 'text-yellow-600', bg: 'bg-yellow-50', border: 'border-yellow-200' };
    if (value <= 150) return { status: 'unhealthy-sensitive', label: 'Unhealthy for Sensitive', color: 'text-orange-600', bg: 'bg-orange-50', border: 'border-orange-200' };
    if (value <= 200) return { status: 'unhealthy', label: 'Unhealthy', color: 'text-red-600', bg: 'bg-red-50', border: 'border-red-200' };
    if (value <= 300) return { status: 'very-unhealthy', label: 'Very Unhealthy', color: 'text-purple-600', bg: 'bg-purple-50', border: 'border-purple-200' };
    return { status: 'hazardous', label: 'Hazardous', color: 'text-purple-900', bg: 'bg-purple-100', border: 'border-purple-300' };
  };

  // Format pollutant values properly
  const formatPollutantValue = (pollutant) => {
    if (!pollutant) return 'N/A';
    
    if (typeof pollutant === 'object') {
      return `${Math.round(pollutant.value * 10) / 10} ${pollutant.unit || 'µg/m³'}`;
    }
    
    return `${Math.round(pollutant * 10) / 10} µg/m³`;
  };

  const aqiInfo = getAQIStatus(currentReading);
  const trend = station?.trend || 'stable';
  const trendIcon = trend === 'up' ? 'TrendingUp' : trend === 'down' ? 'TrendingDown' : 'Minus';
  const trendColor = trend === 'up' ? 'text-red-500' : trend === 'down' ? 'text-green-500' : 'text-muted-foreground';

  // Update reading when station prop changes
  useEffect(() => {
    setCurrentReading(station?.currentAQI || 0);
    
    // Fetch 24h prediction
    if (station?.id) {
      setLoadingPred(true);
      getPredictions(station.id)
        .then(preds => {
          if (preds && preds.length > 0) {
            // Get 24h ahead prediction
            const now = new Date();
            const targetTime = new Date(now.getTime() + 24 * 60 * 60 * 1000);
            const closest = preds.reduce((prev, curr) => {
              const prevDiff = Math.abs(new Date(prev.prediction_time) - targetTime);
              const currDiff = Math.abs(new Date(curr.prediction_time) - targetTime);
              return currDiff < prevDiff ? curr : prev;
            });
            setPrediction(closest?.predicted_aqi);
          }
        })
        .catch(() => setPrediction(null))
        .finally(() => setLoadingPred(false));
    }
  }, [station?.currentAQI, station?.id]);

  const handleCardClick = () => {
    navigate(`/station-details/${station?.id}`);
  };

  return (
    <div 
      className={`
        bg-white border rounded-xl p-6 transition-all duration-200 hover:shadow-lg cursor-pointer
        ${aqiInfo?.bg} ${aqiInfo?.border} border ${className}
      `}
      onClick={handleCardClick}
    >
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <div className="flex items-center space-x-2 mb-1">
            <Icon name="MapPin" size={16} className="text-gray-500" />
            <h3 className="font-semibold text-gray-900">{station?.name || 'Unknown Station'}</h3>
          </div>
          <p className="text-sm text-gray-600">{station?.location || 'Delhi NCR, India'}</p>
        </div>
        
        <div className="flex items-center space-x-2">
          <span className={`w-2 h-2 rounded-full ${station?.status === 'online' ? 'bg-green-500' : 'bg-gray-400'}`}></span>
          <Icon name={trendIcon} size={16} className={trendColor} />
          <button
            onClick={(e) => {
              e.stopPropagation();
              setIsExpanded(!isExpanded);
            }}
            className="p-1 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <Icon 
              name={isExpanded ? "ChevronUp" : "ChevronDown"} 
              size={16} 
              className="text-gray-500" 
            />
          </button>
        </div>
      </div>

      <div className="flex items-end justify-between mb-4">
        <div>
          <div className="flex items-baseline space-x-2">
            <span className="text-4xl font-mono font-bold text-gray-900">
              {currentReading || 0}
            </span>
            <span className="text-sm font-medium text-gray-500 uppercase tracking-wide">
              AQI
            </span>
          </div>
          <span className={`text-sm font-medium ${aqiInfo?.color}`}>
            {aqiInfo?.label}
          </span>
        </div>

        <div className="text-right">
          <p className="text-xs text-gray-500">Last Updated</p>
          <p className="text-sm font-medium text-gray-900">
            {station?.last_updated 
              ? new Date(station.last_updated).toLocaleTimeString('en-IN', { 
                  hour: '2-digit', 
                  minute: '2-digit',
                  timeZone: 'Asia/Kolkata'
                })
              : new Date().toLocaleTimeString('en-IN', { 
                  hour: '2-digit', 
                  minute: '2-digit',
                  timeZone: 'Asia/Kolkata'
                })
            }
          </p>
        </div>
      </div>

      {/* Prediction */}
      <div className="flex items-center justify-between p-3 bg-purple-50 border border-purple-100 rounded-lg mb-4">
        <div className="flex items-center space-x-2">
          <Icon name="TrendingUp" size={14} className="text-purple-500" />
          <span className="text-sm text-purple-700">24h Forecast</span>
        </div>
        {loadingPred ? (
          <div className="animate-spin rounded-full h-4 w-4 border-2 border-purple-500 border-t-transparent" />
        ) : (
          <div className="flex items-center space-x-2">
            <span className="text-sm font-mono font-semibold text-purple-700">
              {prediction || currentReading || '—'}
            </span>
            <span className={`text-xs px-2 py-1 rounded-full ${getAQIStatus(prediction || currentReading)?.bg} ${getAQIStatus(prediction || currentReading)?.color}`}>
              {getAQIStatus(prediction || currentReading)?.label}
            </span>
          </div>
        )}
      </div>

      {/* Expanded Details */}
      {isExpanded && (
        <div className="space-y-3 animate-in slide-in-from-top duration-200">
          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 bg-white border rounded-lg">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">PM2.5</span>
                <span className="text-sm font-mono font-semibold text-gray-900">
                  {formatPollutantValue(station?.pollutants?.pm25)}
                </span>
              </div>
            </div>
            <div className="p-3 bg-white border rounded-lg">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">PM10</span>
                <span className="text-sm font-mono font-semibold text-gray-900">
                  {formatPollutantValue(station?.pollutants?.pm10)}
                </span>
              </div>
            </div>
            <div className="p-3 bg-white border rounded-lg">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">NO₂</span>
                <span className="text-sm font-mono font-semibold text-gray-900">
                  {formatPollutantValue(station?.pollutants?.no2)}
                </span>
              </div>
            </div>
            <div className="p-3 bg-white border rounded-lg">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">SO₂</span>
                <span className="text-sm font-mono font-semibold text-gray-900">
                  {formatPollutantValue(station?.pollutants?.so2)}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between pt-2 border-t border-gray-200">
            <span className="text-xs text-gray-500">Station ID: {station?.id}</span>
            <span className={`text-xs ${station?.status === 'online' ? 'text-green-600' : 'text-gray-500'}`}>
              ● {station?.status === 'online' ? 'Online' : 'Offline'}
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

export default AQIStationCard;