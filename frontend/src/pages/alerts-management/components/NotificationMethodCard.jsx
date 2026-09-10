import React, { useState } from 'react';
import Icon from '../../../components/AppIcon';

const NotificationMethodCard = ({ 
  method, 
  icon, 
  title, 
  description, 
  enabled = false, 
  settings = {},
  isExpanded,
  onToggleExpand,
  onToggle,
  onSettingsChange 
}) => {
  const [isEnabled, setIsEnabled] = useState(enabled);
  const [methodSettings, setMethodSettings] = useState(settings);
  const [showSettingsInternal, setShowSettingsInternal] = useState(false);

  const isSettingsOpen = isExpanded !== undefined ? isExpanded : showSettingsInternal;

  const handleToggle = () => {
    const newEnabled = !isEnabled;
    setIsEnabled(newEnabled);
    if (!newEnabled && isSettingsOpen && onToggleExpand) {
      onToggleExpand();
    }
    onToggle && onToggle(method, newEnabled);
  };

  const toggleSettings = () => {
    if (onToggleExpand) {
      onToggleExpand();
    } else {
      setShowSettingsInternal(!showSettingsInternal);
    }
  };

  const handleSettingChange = (key, value) => {
    const newSettings = { ...methodSettings, [key]: value };
    setMethodSettings(newSettings);
    onSettingsChange && onSettingsChange(method, newSettings);
  };

  const renderPushSettings = () => (
    <div className="space-y-4">
      <div>
        <label className="text-sm font-medium text-foreground mb-2 block">
          Quiet Hours
        </label>
        <div className="flex items-center space-x-2">
          <input
            type="time"
            value={methodSettings?.quietStart || '22:00'}
            onChange={(e) => handleSettingChange('quietStart', e?.target?.value)}
            className="px-3 py-2 border border-border rounded-lg bg-input text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
          <span className="text-sm text-muted-foreground">to</span>
          <input
            type="time"
            value={methodSettings?.quietEnd || '07:00'}
            onChange={(e) => handleSettingChange('quietEnd', e?.target?.value)}
            className="px-3 py-2 border border-border rounded-lg bg-input text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
        </div>
      </div>
      
      <div>
        <label className="flex items-center space-x-2">
          <input
            type="checkbox"
            checked={methodSettings?.allowCritical || false}
            onChange={(e) => handleSettingChange('allowCritical', e?.target?.checked)}
            className="w-4 h-4 text-primary border-border rounded focus:ring-primary/20"
          />
          <span className="text-sm text-foreground">Allow critical alerts during quiet hours</span>
        </label>
      </div>
    </div>
  );

  const renderEmailSettings = () => (
    <div className="space-y-4">
      <div>
        <label className="text-sm font-medium text-foreground mb-2 block">
          Email Address
        </label>
        <input
          type="email"
          value={methodSettings?.email || 'admin@airwatch.pro'}
          onChange={(e) => handleSettingChange('email', e?.target?.value)}
          className="w-full px-3 py-2 border border-border rounded-lg bg-input text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
          placeholder="Enter email address"
        />
      </div>
      
      <div>
        <label className="text-sm font-medium text-foreground mb-2 block">
          Frequency
        </label>
        <select
          value={methodSettings?.frequency || 'immediate'}
          onChange={(e) => handleSettingChange('frequency', e?.target?.value)}
          className="w-full px-3 py-2 border border-border rounded-lg bg-input text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
        >
          <option value="immediate">Immediate</option>
          <option value="hourly">Hourly digest</option>
          <option value="daily">Daily summary</option>
        </select>
      </div>
      
      <div>
        <label className="flex items-center space-x-2">
          <input
            type="checkbox"
            checked={methodSettings?.includeCharts || false}
            onChange={(e) => handleSettingChange('includeCharts', e?.target?.checked)}
            className="w-4 h-4 text-primary border-border rounded focus:ring-primary/20"
          />
          <span className="text-sm text-foreground">Include AQI charts in emails</span>
        </label>
      </div>
    </div>
  );

  const renderSMSSettings = () => (
    <div className="space-y-4">
      <div>
        <label className="text-sm font-medium text-foreground mb-2 block">
          Phone Number
        </label>
        <input
          type="tel"
          value={methodSettings?.phone || '+91 98765 43210'}
          onChange={(e) => handleSettingChange('phone', e?.target?.value)}
          className="w-full px-3 py-2 border border-border rounded-lg bg-input text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
          placeholder="Enter phone number"
        />
      </div>
      
      <div>
        <label className="text-sm font-medium text-foreground mb-2 block">
          Alert Levels
        </label>
        <div className="space-y-2">
          {['Moderate', 'Unhealthy', 'Very Unhealthy', 'Hazardous']?.map((level) => (
            <label key={level} className="flex items-center space-x-2">
              <input
                type="checkbox"
                checked={methodSettings?.alertLevels?.[level] || false}
                onChange={(e) => handleSettingChange('alertLevels', {
                  ...methodSettings?.alertLevels,
                  [level]: e?.target?.checked
                })}
                className="w-4 h-4 text-primary border-border rounded focus:ring-primary/20"
              />
              <span className="text-sm text-foreground">{level}</span>
            </label>
          ))}
        </div>
      </div>
    </div>
  );

  const renderSettings = () => {
    switch (method) {
      case 'push':
        return renderPushSettings();
      case 'email':
        return renderEmailSettings();
      case 'sms':
        return renderSMSSettings();
      default:
        return null;
    }
  };

  return (
    <div className={`
      bg-card border border-border rounded-xl p-6 transition-smooth
      ${isEnabled ? 'ring-2 ring-primary/20' : ''}
    `}>
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
            <Icon name={icon} size={20} className="text-primary" />
          </div>
          <div>
            <h3 className="font-semibold text-foreground">{title}</h3>
            <p className="text-sm text-muted-foreground">{description}</p>
          </div>
        </div>
        
        <button
          type="button"
          onClick={handleToggle}
          className={`
            relative w-12 h-6 rounded-full transition-colors
            ${isEnabled ? 'bg-primary' : 'bg-muted-foreground/30'}
          `}
        >
          <div className={`
            absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform
            ${isEnabled ? 'translate-x-6' : 'translate-x-0.5'}
          `} />
        </button>
      </div>

      {isEnabled && (
        <div className="space-y-4 pt-4 border-t border-border">
          <button
            type="button"
            onClick={toggleSettings}
            className="flex items-center space-x-2 text-sm text-primary hover:text-primary/80 transition-smooth"
          >
            <Icon name={isSettingsOpen ? "ChevronUp" : "ChevronDown"} size={16} />
            <span>Configure settings</span>
          </button>

          {isSettingsOpen && (
            <div className="pl-4 border-l-2 border-primary/20">
              {renderSettings()}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default NotificationMethodCard;