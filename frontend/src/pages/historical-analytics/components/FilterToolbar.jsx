import React, { useState } from 'react';
import Icon from '../../../components/AppIcon';
import Button from '../../../components/ui/Button';
import Select from '../../../components/ui/Select';
import { Checkbox } from '../../../components/ui/Checkbox';

const FilterToolbar = ({ onFiltersChange, isLoading }) => {
  const now = new Date();
  const [dateRange, setDateRange] = useState({
    startDate: `${now.getFullYear()}-01-01`,
    endDate: `${now.getFullYear()}-12-31`
  });
  const [selectedStations, setSelectedStations] = useState(['all']);
  const [selectedPollutants, setSelectedPollutants] = useState(['pm25', 'pm10', 'no2']);
  const [timeframe, setTimeframe] = useState('monthly');
  const [isExpanded, setIsExpanded] = useState(true);

  const stationOptions = [
    { value: 'all', label: 'All Stations' },
    { value: '3409620', label: 'Anand Vihar, Delhi' },
    { value: '3409621', label: 'ITO, Delhi' },
    { value: '3409622', label: 'Punjabi Bagh, Delhi' },
    { value: '3409623', label: 'RK Puram, Delhi' },
    { value: '3409624', label: 'Dwarka Sector 8, Delhi' },
    { value: '3409625', label: 'Noida Sector 62, NCR' },
    { value: '3409626', label: 'Gurugram Sector 51, NCR' }
  ];

  const timeframeOptions = [
    { value: 'daily', label: 'Daily Analysis' },
    { value: 'weekly', label: 'Weekly Trends' },
    { value: 'monthly', label: 'Monthly Overview' },
    { value: 'quarterly', label: 'Quarterly Reports' },
    { value: 'yearly', label: 'Annual Comparison' }
  ];

  const pollutantTypes = [
    { id: 'pm25', label: 'PM2.5', color: 'text-red-600' },
    { id: 'pm10', label: 'PM10', color: 'text-orange-600' },
    { id: 'no2', label: 'NO₂', color: 'text-blue-600' },
    { id: 'so2', label: 'SO₂', color: 'text-purple-600' },
    { id: 'o3', label: 'O₃', color: 'text-green-600' },
    { id: 'co', label: 'CO', color: 'text-gray-600' }
  ];

  const handleDateChange = (field, value) => {
    const newDateRange = { ...dateRange, [field]: value };
    setDateRange(newDateRange);
    applyFilters({ dateRange: newDateRange });
  };

  const handlePollutantToggle = (pollutantId) => {
    const newSelected = selectedPollutants?.includes(pollutantId)
      ? selectedPollutants?.filter(id => id !== pollutantId)
      : [...selectedPollutants, pollutantId];
    
    setSelectedPollutants(newSelected);
    applyFilters({ pollutants: newSelected });
  };

  const applyFilters = (updates = {}) => {
    const filters = {
      dateRange,
      stations: selectedStations,
      pollutants: selectedPollutants,
      timeframe,
      ...updates
    };
    onFiltersChange(filters);
  };

  const resetFilters = () => {
    const defaultFilters = {
      dateRange: { startDate: `${(new Date()).getFullYear()}-01-01`, endDate: `${(new Date()).getFullYear()}-12-31` },
      stations: ['all'],
      pollutants: ['pm25', 'pm10', 'no2'],
      timeframe: 'monthly'
    };
    
    setDateRange(defaultFilters?.dateRange);
    setSelectedStations(defaultFilters?.stations);
    setSelectedPollutants(defaultFilters?.pollutants);
    setTimeframe(defaultFilters?.timeframe);
    onFiltersChange(defaultFilters);
  };

  return (
    <div className="bg-card border border-border rounded-xl p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-3">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary/10">
            <Icon name="Filter" size={16} className="text-primary" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-foreground">Analysis Filters</h3>
            <p className="text-sm text-muted-foreground">Configure parameters for historical data analysis</p>
          </div>
        </div>
        
        <div className="flex items-center space-x-2">
          <Button
            variant="outline"
            size="sm"
            onClick={resetFilters}
            iconName="RotateCcw"
            iconPosition="left"
          >
            Reset
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsExpanded(!isExpanded)}
            iconName={isExpanded ? "ChevronUp" : "ChevronDown"}
          >
            {isExpanded ? 'Collapse' : 'Expand'}
          </Button>
        </div>
      </div>
      {isExpanded && (
        <div className="space-y-6">
          {/* Date Range Selection */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-foreground mb-2">Start Date</label>
              <input
                type="date"
                value={dateRange?.startDate}
                onChange={(e) => handleDateChange('startDate', e?.target?.value)}
                className="w-full px-3 py-2 border border-border rounded-lg bg-input text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary"
                max={dateRange?.endDate}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-2">End Date</label>
              <input
                type="date"
                value={dateRange?.endDate}
                onChange={(e) => handleDateChange('endDate', e?.target?.value)}
                className="w-full px-3 py-2 border border-border rounded-lg bg-input text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary"
                min={dateRange?.startDate}
              />
            </div>
          </div>

          {/* Station and Timeframe Selection */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Select
              label="Monitoring Stations"
              options={stationOptions}
              value={selectedStations}
              onChange={setSelectedStations}
              multiple
              searchable
              placeholder="Select stations to analyze"
            />
            
            <Select
              label="Analysis Timeframe"
              options={timeframeOptions}
              value={timeframe}
              onChange={(value) => {
                setTimeframe(value);
                applyFilters({ timeframe: value });
              }}
              placeholder="Choose analysis period"
            />
          </div>

          {/* Pollutant Type Selection */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-3">Pollutant Types</label>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              {pollutantTypes?.map((pollutant) => (
                <div key={pollutant?.id} className="flex items-center space-x-2">
                  <Checkbox
                    checked={selectedPollutants?.includes(pollutant?.id)}
                    onChange={() => handlePollutantToggle(pollutant?.id)}
                  />
                  <label className={`text-sm font-medium cursor-pointer ${pollutant?.color}`}>
                    {pollutant?.label}
                  </label>
                </div>
              ))}
            </div>
          </div>

          {/* Quick Filter Presets */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-3">Quick Presets</label>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  const lastMonth = new Date();
                  lastMonth?.setMonth(lastMonth?.getMonth() - 1);
                  handleDateChange('startDate', lastMonth?.toISOString()?.split('T')?.[0]);
                  handleDateChange('endDate', new Date()?.toISOString()?.split('T')?.[0]);
                }}
              >
                Last Month
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  const lastQuarter = new Date();
                  lastQuarter?.setMonth(lastQuarter?.getMonth() - 3);
                  handleDateChange('startDate', lastQuarter?.toISOString()?.split('T')?.[0]);
                  handleDateChange('endDate', new Date()?.toISOString()?.split('T')?.[0]);
                }}
              >
                Last Quarter
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  const lastYear = new Date();
                  lastYear?.setFullYear(lastYear?.getFullYear() - 1);
                  handleDateChange('startDate', lastYear?.toISOString()?.split('T')?.[0]);
                  handleDateChange('endDate', new Date()?.toISOString()?.split('T')?.[0]);
                }}
              >
                Last Year
              </Button>
            </div>
          </div>

          {/* Apply Filters Button */}
          <div className="flex justify-end pt-4 border-t border-border">
            <Button
              onClick={() => applyFilters()}
              loading={isLoading}
              iconName="Search"
              iconPosition="left"
            >
              Apply Filters
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

export default FilterToolbar;