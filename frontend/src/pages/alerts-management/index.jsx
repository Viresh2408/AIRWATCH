import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../../components/ui/Header';
import Breadcrumbs from '../../components/ui/Breadcrumbs';
import Icon from '../../components/AppIcon';
import Button from '../../components/ui/Button';
import AlertThresholdSlider from './components/AlertThresholdSlider';
import StationAlertToggle from './components/StationAlertToggle';
import NotificationMethodCard from './components/NotificationMethodCard';
import AlertHistoryCard from './components/AlertHistoryCard';
import PredictiveAlertSettings from './components/PredictiveAlertSettings';
import BulkAlertManager from './components/BulkAlertManager';
import { useAirQuality } from '../../context/AirQualityContext';

const AlertsManagement = () => {
  const navigate = useNavigate();
  const { enrichedStations, loading: contextLoading } = useAirQuality();
  const [activeTab, setActiveTab] = useState('thresholds');
  const [showToast, setShowToast] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterSeverity, setFilterSeverity] = useState('all');
  const [filterTimeRange, setFilterTimeRange] = useState('7d');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expandedNotificationMethod, setExpandedNotificationMethod] = useState(null);

  // Enhanced alert levels based on standard AQI categories
  const alertLevels = [
    {
      level: 'Moderate',
      color: '#F59E0B',
      icon: 'AlertCircle',
      defaultValue: 101,
      min: 51,
      max: 150
    },
    {
      level: 'Unhealthy for Sensitive',
      color: '#EF4444',
      icon: 'AlertTriangle',
      defaultValue: 151,
      min: 101,
      max: 200
    },
    {
      level: 'Very Unhealthy',
      color: '#DC2626',
      icon: 'AlertOctagon',
      defaultValue: 201,
      min: 151,
      max: 300
    },
    {
      level: 'Hazardous',
      color: '#7C2D12',
      icon: 'Skull',
      defaultValue: 301,
      min: 201,
      max: 500
    }
  ];

  // Use real enriched stations from context
  const monitoringStations = enrichedStations.map((station) => ({
    id: station.id,
    name: station.name,
    location: `${station.lat?.toFixed(4)}, ${station.lon?.toFixed(4)}`,
    currentAQI: station.overall_aqi,
    status: station.aqi_category,
    lastUpdated: station.last_updated
      ? new Date(station.last_updated).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })
      : 'N/A',
    alertEnabled: true,
    customThreshold: null,
  }));

  // Build real alert history from live threshold breaches
  const THRESHOLDS = { pm25: 60, pm10: 100, no2: 80, o3: 100, so2: 80 };
  const alertHistory = enrichedStations.flatMap((station) => {
    const alerts = [];
    if (station.overall_aqi > 200) {
      alerts.push({
        id: `aqi-${station.id}`,
        type: 'threshold', severity: 'hazardous',
        title: 'Severe AQI Alert',
        message: `AQI is ${station.overall_aqi} (${station.aqi_category}) at ${station.name}`,
        stationId: station.id, stationName: station.name,
        aqiValue: station.overall_aqi,
        timestamp: new Date(station.last_updated || Date.now()),
        acknowledged: false,
      });
    } else if (station.overall_aqi > 100) {
      alerts.push({
        id: `aqi-${station.id}`,
        type: 'threshold', severity: 'unhealthy',
        title: 'Elevated AQI Alert',
        message: `AQI is ${station.overall_aqi} (${station.aqi_category}) at ${station.name}`,
        stationId: station.id, stationName: station.name,
        aqiValue: station.overall_aqi,
        timestamp: new Date(station.last_updated || Date.now()),
        acknowledged: false,
      });
    }
    Object.entries(station.pollutants || {}).forEach(([param, data]) => {
      const thresh = THRESHOLDS[param];
      if (!thresh) return;
      const val = data.ugm3_value ?? data.value ?? 0;
      if (val >= thresh) {
        alerts.push({
          id: `${param}-${station.id}`,
          type: 'threshold',
          severity: val >= thresh * 1.5 ? 'very-unhealthy' : 'unhealthy',
          title: `${param.toUpperCase()} Threshold Breach`,
          message: `${param.toUpperCase()} at ${val.toFixed(1)} µg/m³ exceeds threshold (${thresh}) at ${station.name}`,
          stationId: station.id, stationName: station.name,
          aqiValue: station.overall_aqi,
          timestamp: new Date(station.last_updated || Date.now()),
          acknowledged: false,
        });
      }
    });
    return alerts;
  });

  // Mock data for notification methods
  const notificationMethods = [
    {
      method: 'push',
      icon: 'Smartphone',
      title: 'Push Notifications',
      description: 'Instant alerts on your device',
      enabled: true,
      settings: {
        quietStart: '22:00',
        quietEnd: '07:00',
        allowCritical: true
      }
    },
    {
      method: 'email',
      icon: 'Mail',
      title: 'Email Notifications',
      description: 'Detailed reports via email',
      enabled: true,
      settings: {
        email: 'admin@airwatch.pro',
        frequency: 'immediate',
        includeCharts: true
      }
    },
    {
      method: 'sms',
      icon: 'MessageSquare',
      title: 'SMS Alerts',
      description: 'Text messages for critical alerts',
      enabled: false,
      settings: {
        phone: '+91 98765 43210',
        alertLevels: {
          'Very Unhealthy': true,
          'Hazardous': true
        }
      }
    }
  ];

  const tabs = [
    { id: 'thresholds', label: 'Alert Thresholds', icon: 'Sliders' },
    { id: 'stations', label: 'Station Settings', icon: 'MapPin' },
    { id: 'notifications', label: 'Notification Methods', icon: 'Bell' },
    { id: 'predictive', label: 'Predictive Alerts', icon: 'TrendingUp' },
    { id: 'history', label: 'Alert History', icon: 'Clock' },
    { id: 'bulk', label: 'Bulk Management', icon: 'Settings' }
  ];

  const showToastMessage = (message, type = 'success') => {
    setShowToast({ message, type });
    setTimeout(() => setShowToast(null), 3000);
  };

  const handleThresholdChange = (level, value) => {
    showToastMessage(`${level} threshold updated to AQI ${value}`);
  };

  const handleStationToggle = (stationId, enabled) => {
    const station = monitoringStations?.find(s => s?.id === stationId);
    showToastMessage(`Alerts ${enabled ? 'enabled' : 'disabled'} for ${station?.name}`);
  };

  const handleNotificationToggle = (method, enabled) => {
    const methodData = notificationMethods?.find(m => m?.method === method);
    showToastMessage(`${methodData?.title} ${enabled ? 'enabled' : 'disabled'}`);
  };

  const handlePredictiveSettingsSave = (settings) => {
    showToastMessage('Predictive alert settings saved successfully');
  };

  const handleBulkUpdate = (actionData) => {
    const { stationIds, action } = actionData;
    showToastMessage(`Bulk action "${action}" applied to ${stationIds?.length} station(s)`);
  };

  const filteredHistory = alertHistory?.filter(alert => {
    const matchesSearch = alert?.title?.toLowerCase()?.includes(searchTerm?.toLowerCase()) ||
                         alert?.stationName?.toLowerCase()?.includes(searchTerm?.toLowerCase());
    const matchesSeverity = filterSeverity === 'all' || alert?.severity === filterSeverity;
    
    let matchesTimeRange = true;
    if (filterTimeRange !== 'all') {
      const now = new Date();
      const alertDate = new Date(alert.timestamp);
      const daysDiff = Math.floor((now - alertDate) / (1000 * 60 * 60 * 24));
      
      switch (filterTimeRange) {
        case '1d':
          matchesTimeRange = daysDiff === 0;
          break;
        case '7d':
          matchesTimeRange = daysDiff <= 7;
          break;
        case '30d':
          matchesTimeRange = daysDiff <= 30;
          break;
      }
    }
    
    return matchesSearch && matchesSeverity && matchesTimeRange;
  });

  const renderTabContent = () => {
    switch (activeTab) {
      case 'thresholds':
        return (
          <div className="space-y-6">
            <div className="bg-card border border-border rounded-xl p-6">
              <div className="flex items-center space-x-3 mb-6">
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                  <Icon name="Sliders" size={20} className="text-primary" />
                </div>
                <div>
                  <h3 className="font-semibold text-foreground">Global Alert Thresholds</h3>
                  <p className="text-sm text-muted-foreground">
                    Configure AQI levels that trigger notifications across all stations
                  </p>
                </div>
              </div>
              
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {alertLevels?.map((level) => (
                  <AlertThresholdSlider
                    key={level?.level}
                    level={level?.level}
                    color={level?.color}
                    icon={level?.icon}
                    defaultValue={level?.defaultValue}
                    min={level?.min}
                    max={level?.max}
                    onChange={(value) => handleThresholdChange(level?.level, value)}
                    onToggle={(enabled) => showToastMessage(`${level?.level} threshold ${enabled ? 'enabled' : 'disabled'}`)}
                  />
                ))}
              </div>
            </div>
          </div>
        );

      case 'stations':
        return (
          <div className="space-y-6">
            <div className="bg-card border border-border rounded-xl p-6">
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                    <Icon name="MapPin" size={20} className="text-primary" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-foreground">Station-Specific Settings</h3>
                    <p className="text-sm text-muted-foreground">
                      Configure individual alert preferences for each monitoring station
                    </p>
                  </div>
                </div>
                
                <div className="text-sm text-muted-foreground">
                  {monitoringStations?.filter(s => s?.alertEnabled)?.length} of {monitoringStations?.length} stations enabled
                </div>
              </div>
              
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {monitoringStations?.map((station) => (
                  <StationAlertToggle
                    key={station?.id}
                    station={station}
                    enabled={station?.alertEnabled}
                    customThreshold={station?.customThreshold}
                    onToggle={handleStationToggle}
                    onThresholdChange={(stationId, threshold) => showToastMessage(`Custom threshold for ${monitoringStations?.find(s => s?.id === stationId)?.name} set to AQI ${threshold}`)}
                  />
                ))}
              </div>
            </div>
          </div>
        );

      case 'notifications':
        return (
          <div className="space-y-6">
            <div className="bg-card border border-border rounded-xl p-6">
              <div className="flex items-center space-x-3 mb-6">
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                  <Icon name="Bell" size={20} className="text-primary" />
                </div>
                <div>
                  <h3 className="font-semibold text-foreground">Notification Preferences</h3>
                  <p className="text-sm text-muted-foreground">
                    Choose how and when you receive air quality alerts
                  </p>
                </div>
              </div>
              
              <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
                {notificationMethods?.map((method) => (
                  <NotificationMethodCard
                    key={method?.method}
                    method={method?.method}
                    icon={method?.icon}
                    title={method?.title}
                    description={method?.description}
                    enabled={method?.enabled}
                    settings={method?.settings}
                    isExpanded={expandedNotificationMethod === method?.method}
                    onToggleExpand={() => {
                      setExpandedNotificationMethod(prev => 
                        prev === method?.method ? null : method?.method
                      );
                    }}
                    onToggle={handleNotificationToggle}
                  />
                ))}
              </div>
            </div>
          </div>
        );

      case 'predictive':
        return (
          <div className="space-y-6">
            <PredictiveAlertSettings onSave={handlePredictiveSettingsSave} />
          </div>
        );

      case 'history':
        return (
          <div className="space-y-6">
            <div className="bg-card border border-border rounded-xl p-6">
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                    <Icon name="Clock" size={20} className="text-primary" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-foreground">Alert History</h3>
                    <p className="text-sm text-muted-foreground">
                      Review past air quality notifications and alerts
                    </p>
                  </div>
                </div>
                
                <div className="text-sm text-muted-foreground">
                  {filteredHistory?.length} of {alertHistory?.length} alerts
                </div>
              </div>

              {/* Filters */}
              <div className="flex flex-col sm:flex-row gap-4 mb-6">
                <div className="flex-1">
                  <div className="relative">
                    <Icon name="Search" size={16} className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" />
                    <input
                      type="text"
                      placeholder="Search alerts..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e?.target?.value)}
                      className="w-full pl-10 pr-4 py-2 border border-border rounded-lg bg-input text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                    />
                  </div>
                </div>
                
                <select
                  value={filterSeverity}
                  onChange={(e) => setFilterSeverity(e?.target?.value)}
                  className="px-3 py-2 border border-border rounded-lg bg-input text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                >
                  <option value="all">All Severities</option>
                  <option value="moderate">Moderate</option>
                  <option value="unhealthy">Unhealthy</option>
                  <option value="very-unhealthy">Very Unhealthy</option>
                  <option value="hazardous">Hazardous</option>
                </select>
                
                <select
                  value={filterTimeRange}
                  onChange={(e) => setFilterTimeRange(e?.target?.value)}
                  className="px-3 py-2 border border-border rounded-lg bg-input text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                >
                  <option value="all">All Time</option>
                  <option value="1d">Today</option>
                  <option value="7d">Last 7 days</option>
                  <option value="30d">Last 30 days</option>
                </select>
              </div>
              
              <div className="space-y-4">
                {filteredHistory?.length > 0 ? (
                  filteredHistory?.map((alert) => (
                    <AlertHistoryCard
                      key={alert?.id}
                      alert={alert}
                      onShare={(message) => showToastMessage(message)}
                    />
                  ))
                ) : (
                  <div className="text-center py-12">
                    <Icon name="Clock" size={48} className="text-muted-foreground mx-auto mb-4" />
                    <h4 className="text-lg font-medium text-foreground mb-2">No alerts found</h4>
                    <p className="text-muted-foreground">
                      {searchTerm || filterSeverity !== 'all' || filterTimeRange !== 'all' ? 'Try adjusting your filters to see more results.' : 'Alert history will appear here when notifications are triggered.'}
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        );

      case 'bulk':
        return (
          <div className="space-y-6">
            <BulkAlertManager
              stations={monitoringStations}
              onBulkUpdate={handleBulkUpdate}
            />
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="pt-16">
        <div className="max-w-7xl mx-auto px-6 py-8">
          <Breadcrumbs />
          
          {/* Page Header */}
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-3xl font-bold text-foreground mb-2">
                Alerts Management
              </h1>
              <p className="text-muted-foreground">
                Configure notification preferences and review air quality warning history
              </p>
            </div>
            
            <div className="flex items-center space-x-3">
              <Button
                variant="outline"
                onClick={() => navigate('/dashboard')}
                iconName="ArrowLeft"
                iconPosition="left"
              >
                Back to Dashboard
              </Button>
            </div>
          </div>

          {/* Loading State */}
          {loading && (
            <div className="bg-card border border-border rounded-xl p-8">
              <div className="flex items-center justify-center space-x-3">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
                <span className="text-muted-foreground">Loading monitoring stations...</span>
              </div>
            </div>
          )}

          {/* Error State */}
          {error && (
            <div className="bg-card border border-destructive/20 rounded-xl p-6 mb-8">
              <div className="flex items-center space-x-3 text-destructive">
                <Icon name="AlertCircle" size={20} />
                <div>
                  <h3 className="font-medium">Error Loading Data</h3>
                  <p className="text-sm mt-1">{error}</p>
                </div>
              </div>
            </div>
          )}

          {/* Main Content */}
          {!error && (
            <>
              {/* Tabs Navigation */}
              <div className="bg-card border border-border rounded-xl p-2 mb-8">
                <div className="flex flex-wrap gap-1">
                  {tabs?.map((tab) => (
                    <button
                      key={tab?.id}
                      onClick={() => setActiveTab(tab?.id)}
                      className={`
                        flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-smooth
                        ${activeTab === tab?.id
                          ? 'bg-primary text-primary-foreground shadow-sm'
                          : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                        }
                      `}
                    >
                      <Icon name={tab?.icon} size={16} />
                      <span className="hidden sm:inline">{tab?.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Tab Content */}
              {renderTabContent()}
            </>
          )}
        </div>
      </main>
      {/* Toast Notification */}
      {showToast && (
        <div className="fixed bottom-6 right-6 z-50 animate-slide-in">
          <div className={`
            flex items-center space-x-3 px-4 py-3 rounded-lg shadow-lg border
            ${showToast?.type === 'success' ? 'bg-success text-success-foreground border-success/20' : 'bg-destructive text-destructive-foreground border-destructive/20'}
          `}>
            <Icon 
              name={showToast?.type === 'success' ? "CheckCircle" : "AlertCircle"} 
              size={16} 
            />
            <span className="text-sm font-medium">{showToast?.message}</span>
            <button
              onClick={() => setShowToast(null)}
              className="ml-2 hover:opacity-80 transition-opacity"
            >
              <Icon name="X" size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default AlertsManagement;