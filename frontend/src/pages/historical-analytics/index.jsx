import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../../components/ui/Header';
import Breadcrumbs from '../../components/ui/Breadcrumbs';
import Icon from '../../components/AppIcon';
import Button from '../../components/ui/Button';
import realDataService from '../../services/realDataService';

// Import all components
import FilterToolbar from './components/FilterToolbar';
import TrendAnalysisChart from './components/TrendAnalysisChart';
import HeatmapVisualization from './components/HeatmapVisualization';
import StatisticalSummary from './components/StatisticalSummary';
import ComparisonCharts from './components/ComparisonCharts';
import ExportPanel from './components/ExportPanel';

const HistoricalAnalytics = () => {
  const navigate = useNavigate();
  const [stations, setStations] = useState([
    { id: 3409620, name: 'Anand Vihar, Delhi' },
    { id: 3409621, name: 'ITO, Delhi' },
    { id: 3409622, name: 'Punjabi Bagh, Delhi' },
    { id: 3409623, name: 'RK Puram, Delhi' },
    { id: 3409624, name: 'Dwarka Sector 8, Delhi' },
    { id: 3409625, name: 'Noida Sector 62, NCR' },
    { id: 3409626, name: 'Gurugram Sector 51, NCR' }
  ]);
  const [analyticsData, setAnalyticsData] = useState(null);
  const now = new Date();
  const [activeFilters, setActiveFilters] = useState({
    dateRange: {
      startDate: `${now.getFullYear()}-01-01`,
      endDate: `${now.getFullYear()}-12-31`
    },
    stations: ['all'],
    pollutants: ['pm25', 'pm10', 'no2'],
    timeframe: 'monthly'
  });
  const [isLoading, setIsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('trends');
  const [refreshKey, setRefreshKey] = useState(0);

  // Fetch real stations data
  const fetchStationsData = async () => {
    try {
      const stationsData = await realDataService.getStations();
      setStations(stationsData);
      
      // Update filter options with real station IDs
      setActiveFilters(prev => ({
        ...prev,
        stations: ['all'] // Default to all stations
      }));
    } catch (error) {
      console.error('Error fetching stations:', error);
    }
  };

  // Fetch analytics data without loading states
  const fetchAnalyticsData = async () => {
    // Remove loading states - data updates seamlessly
    try {
      const summary = await realDataService.getAnalyticsSummary();
      setAnalyticsData(summary);
    } catch (error) {
      console.error('Error fetching analytics data:', error);
      // Keep existing data on error
    }
  };

  useEffect(() => {
    fetchStationsData();
    fetchAnalyticsData();
  }, []);

  const analyticsViews = [
    {
      id: 'trends',
      label: 'Trend Analysis',
      icon: 'TrendingUp',
      description: 'Time-series analysis and patterns'
    },
    {
      id: 'heatmap',
      label: 'Heatmap View',
      icon: 'Grid3x3',
      description: 'Spatial and temporal visualization'
    },
    {
      id: 'statistics',
      label: 'Statistical Summary',
      icon: 'BarChart3',
      description: 'Descriptive statistics and metrics'
    },
    {
      id: 'comparison',
      label: 'Comparative Analysis',
      icon: 'BarChart',
      description: 'Multi-dimensional comparisons'
    },
    {
      id: 'export',
      label: 'Export Data',
      icon: 'Download',
      description: 'Generate reports and downloads'
    }
  ];

  const handleFiltersChange = (newFilters) => {
    setActiveFilters(newFilters);
    fetchAnalyticsData(); // Refetch data with new filters
  };

  const handleExport = (exportData) => {
    console.log('Export completed:', exportData);
    // Show success notification or handle export completion
  };

  const handleRefreshData = () => {
    fetchAnalyticsData();
  };

  const renderActiveView = () => {
    const props = { 
      filters: activeFilters, 
      stations: stations,
      analyticsData: analyticsData,
      key: `${activeTab}-${refreshKey}` 
    };

    switch (activeTab) {
      case 'trends':
        return <TrendAnalysisChart {...props} />;
      case 'heatmap':
        return <HeatmapVisualization {...props} />;
      case 'statistics':
        return <StatisticalSummary {...props} />;
      case 'comparison':
        return <ComparisonCharts {...props} />;
      case 'export':
        return <ExportPanel {...props} onExport={handleExport} />;
      default:
        return <TrendAnalysisChart {...props} />;
    }
  };

  // Auto-refresh data every 5 minutes
  useEffect(() => {
    const interval = setInterval(() => {
      if (activeTab !== 'export') {
        handleRefreshData();
      }
    }, 300000); // 5 minutes

    return () => clearInterval(interval);
  }, [activeTab]);

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="pt-16">
        <div className="max-w-7xl mx-auto px-6 py-8">
          <Breadcrumbs />
          
          {/* Page Header */}
          <div className="flex items-center justify-between mb-8">
            <div className="flex items-center space-x-4">
              <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br from-primary to-accent">
                <Icon name="TrendingUp" size={24} color="white" />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-foreground">Historical Analytics</h1>
                <p className="text-muted-foreground mt-1">
                  Comprehensive analysis of air quality trends and patterns across monitoring stations
                </p>
              </div>
            </div>
            
            <div className="flex items-center space-x-3">
              <Button
                variant="outline"
                onClick={handleRefreshData}
                loading={isLoading}
                iconName="RefreshCw"
                iconPosition="left"
              >
                Refresh Data
              </Button>
              
              <Button
                onClick={() => navigate('/dashboard')}
                iconName="LayoutDashboard"
                iconPosition="left"
              >
                Back to Dashboard
              </Button>
            </div>
          </div>

          {/* Filter Toolbar */}
          <FilterToolbar 
            onFiltersChange={handleFiltersChange}
            isLoading={isLoading}
          />

          {/* Analytics Navigation Tabs */}
          <div className="bg-card border border-border rounded-xl p-2 mb-6">
            <div className="flex items-center space-x-1 overflow-x-auto">
              {analyticsViews?.map((view) => (
                <button
                  key={view?.id}
                  onClick={() => setActiveTab(view?.id)}
                  className={`
                    flex items-center space-x-2 px-4 py-3 rounded-lg text-sm font-medium transition-smooth whitespace-nowrap
                    ${activeTab === view?.id
                      ? 'bg-primary text-primary-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                    }
                  `}
                  title={view?.description}
                >
                  <Icon name={view?.icon} size={16} />
                  <span>{view?.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Active Filter Summary */}
          <div className="bg-muted/50 border border-border rounded-lg p-4 mb-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-4">
                <Icon name="Filter" size={16} className="text-muted-foreground" />
                <div className="text-sm">
                  <span className="text-muted-foreground">Active Filters: </span>
                  <span className="font-medium text-foreground">
                    {activeFilters?.dateRange?.startDate} to {activeFilters?.dateRange?.endDate}
                  </span>
                  <span className="text-muted-foreground"> • </span>
                  <span className="font-medium text-foreground">
                    {activeFilters?.stations?.includes('all') ? 'All Stations' : `${activeFilters?.stations?.length} Stations`}
                  </span>
                  <span className="text-muted-foreground"> • </span>
                  <span className="font-medium text-foreground">
                    {stations.length} Total Stations
                  </span>
                  <span className="text-muted-foreground"> • </span>
                  <span className="font-medium text-foreground">
                    {activeFilters?.pollutants?.length} Pollutants
                  </span>
                </div>
              </div>
              
              <div className="flex items-center space-x-2 text-sm text-muted-foreground">
                <Icon name="Clock" size={14} />
                <span>Last updated: {new Date()?.toLocaleTimeString('en-IN')}</span>
              </div>
            </div>
          </div>

          {/* Main Content Area */}
          <div className="space-y-6">
            {renderActiveView()}
          </div>

          {/* Quick Actions Footer */}
          <div className="mt-8 pt-6 border-t border-border">
            <div className="flex items-center justify-between">
              <div className="text-sm text-muted-foreground">
                Need help with analytics? Check our{' '}
                <button className="text-primary hover:underline">documentation</button> or{' '}
                <button className="text-primary hover:underline">contact support</button>.
              </div>
              
              <div className="flex items-center space-x-3">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate('/station-details')}
                  iconName="MapPin"
                  iconPosition="left"
                >
                  Station Details
                </Button>
                
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate('/alerts-management')}
                  iconName="Bell"
                  iconPosition="left"
                >
                  Manage Alerts
                </Button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default HistoricalAnalytics;