import React from 'react';
import { useNavigate } from 'react-router-dom';
import Icon from '../../components/AppIcon';
import Button from '../../components/ui/Button';

const LandingPage = () => {
  const navigate = useNavigate();

  const features = [
    {
      icon: 'TrendingUp',
      title: '72-Hour Coupled Forecasting',
      description: 'Physics-chemistry coupled engine simulates two-way feedbacks between meteorology (PBL height, winds, inversion) and pollutants (PM2.5, PM10, O3, NOx).',
      color: 'bg-purple-100 text-purple-600',
    },
    {
      icon: 'MapPin',
      title: '7 Delhi NCR Stations',
      description: 'Real-time monitoring and forecasting across key receptors: Anand Vihar, ITO, Punjabi Bagh, RK Puram, Dwarka, Noida 62, and Gurugram.',
      color: 'bg-blue-100 text-blue-600',
    },
    {
      icon: 'Flame',
      title: 'Stubble-Burning Plume Tracking',
      description: 'Ingests NASA FIRMS active fire hotspots and computes regional Gaussian plume advection across Northwest India into Delhi NCR.',
      color: 'bg-amber-100 text-amber-600',
    },
    {
      icon: 'Activity',
      title: 'Atmospheric Inversion Gauge',
      description: 'Quantifies pre-dawn boundary layer collapse and inversion strength [0.0-1.0] that traps particulate matter near the surface.',
      color: 'bg-red-100 text-red-600',
    },
    {
      icon: 'BarChart3',
      title: 'Coupling Explainability',
      description: 'Transparent iteration trace demonstrating uncoupled vs. coupled PBL suppression %, surface dimming, and numerical convergence.',
      color: 'bg-green-100 text-green-600',
    },
    {
      icon: 'Shield',
      title: 'Enterprise MLOps & API',
      description: 'Automated 6-hour scheduler, live OpenAQ & NASA FIRMS ingestion, Supabase PostgreSQL, and Groq LLM health advisory assistant.',
      color: 'bg-indigo-100 text-indigo-600',
    },
  ];

  const stats = [
    { value: '7', label: 'Delhi NCR Stations', icon: 'MapPin' },
    { value: '72h', label: 'Coupled Forecast Horizon', icon: 'Clock' },
    { value: '18%', label: 'Avg PBL Suppression Modeled', icon: 'Activity' },
    { value: '2-Way', label: 'Aerosol-Weather Feedback', icon: 'Wind' },
  ];

  return (
    <div className="min-h-screen bg-background">
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white/80 backdrop-blur-lg border-b border-border">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-purple-600 rounded-xl flex items-center justify-center">
              <Icon name="Wind" size={20} className="text-white" />
            </div>
            <span className="text-xl font-bold text-foreground">AirWatch<span className="text-blue-600">Pro</span></span>
          </div>
          <div className="flex items-center gap-4">
            <button onClick={() => navigate('/login')} className="px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
              Sign In
            </button>
            <button onClick={() => navigate('/register')} className="px-4 py-2 text-sm font-medium bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors">
              Get Started
            </button>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="pt-32 pb-20 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div className="text-center lg:text-left">
              <div className="inline-flex items-center gap-2 px-4 py-2 bg-blue-50 border border-blue-200 rounded-full mb-6">
                <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                <span className="text-sm text-blue-700 font-medium">Live AQI Monitoring Active</span>
              </div>
              <h1 className="text-3xl sm:text-4xl md:text-5xl font-bold text-foreground mb-6 leading-tight">
                Air Pollution–Weather
                <span className="block text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-purple-600 mt-2">
                  Coupled Forecasting System
                </span>
              </h1>
              <p className="text-base sm:text-lg text-muted-foreground mb-8 leading-relaxed">
                High-resolution 72-hour Delhi NCR forecasts integrating dynamic two-way interactions between atmospheric physics (inversion layers, PBL height) and chemical dispersion (PM2.5, PM10, O3, stubble-burning plume advection).
              </p>
              <div className="flex flex-wrap justify-center lg:justify-start gap-4">
                <button 
                  onClick={() => navigate('/login')}
                  className="px-8 py-4 bg-gradient-to-r from-blue-600 to-purple-600 text-white font-semibold rounded-xl hover:shadow-lg hover:shadow-purple-500/25 transition-all"
                >
                  Explore Dashboard
                </button>
                <button 
                  onClick={() => navigate('/register')}
                  className="px-8 py-4 border border-border text-foreground font-semibold rounded-xl hover:bg-muted transition-colors"
                >
                  View Documentation
                </button>
              </div>
            </div>
            
            {/* Hero Visual */}
            <div className="relative">
              <div className="bg-gradient-to-br from-slate-900 to-slate-800 rounded-3xl p-6 shadow-2xl">
                {/* Mini Dashboard Preview */}
                <div className="flex items-center gap-2 mb-4">
                  <div className="w-3 h-3 rounded-full bg-red-500"></div>
                  <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
                  <div className="w-3 h-3 rounded-full bg-green-500"></div>
                  <span className="ml-4 text-sm text-slate-400">Atmospheric Intelligence · Delhi NCR</span>
                </div>
                
                {/* AQI Card */}
                <div className="bg-gradient-to-r from-purple-700 to-rose-700 rounded-xl p-6 mb-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-purple-200 text-sm mb-1">Delhi NCR Average AQI</p>
                      <p className="text-5xl font-bold text-white">326</p>
                      <p className="text-purple-200 text-sm mt-1">Very Poor · Inversion Trapping Active</p>
                    </div>
                    <div className="w-16 h-16 bg-white/20 rounded-full flex items-center justify-center">
                      <Icon name="Wind" size={32} className="text-white" />
                    </div>
                  </div>
                </div>
                
                {/* Station Cards */}
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { name: 'Anand Vihar', aqi: 365, color: 'from-purple-600 to-rose-600' },
                    { name: 'ITO', aqi: 310, color: 'from-purple-500 to-indigo-600' },
                    { name: 'Punjabi Bagh', aqi: 325, color: 'from-purple-600 to-pink-600' },
                  ].map((station) => (
                    <div key={station.name} className="bg-white/10 rounded-lg p-3">
                      <p className="text-slate-400 text-xs mb-1 truncate">{station.name}</p>
                      <p className="text-xl font-bold text-white">{station.aqi}</p>
                      <div className={`h-1 mt-2 rounded-full bg-gradient-to-r ${station.color}`}></div>
                    </div>
                  ))}
                </div>
                
                {/* Forecast Preview */}
                <div className="mt-4 bg-white/10 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-slate-300">72h Coupled Forecast</span>
                    <span className="text-xs text-amber-400 font-medium">σ=15° Plume Advection</span>
                  </div>
                  <div className="h-8 flex items-end gap-1">
                    {[65, 78, 85, 92, 88, 70, 60, 75, 95, 100, 85, 70].map((h, i) => (
                      <div 
                        key={i} 
                        className="flex-1 bg-gradient-to-t from-purple-600 to-rose-500 rounded-t opacity-80"
                        style={{ height: `${h}%` }}
                      ></div>
                    ))}
                  </div>
                </div>
              </div>
              
              {/* Floating Elements */}
              <div className="absolute -top-4 -right-4 bg-white rounded-xl shadow-lg p-3 border border-border">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 bg-green-100 rounded-lg flex items-center justify-center">
                    <Icon name="Check" size={16} className="text-green-600" />
                  </div>
                  <span className="text-sm font-medium">Model Updated</span>
                </div>
              </div>
              <div className="absolute -bottom-4 -left-4 bg-white rounded-xl shadow-lg p-3 border border-border">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center">
                    <Icon name="Zap" size={16} className="text-blue-600" />
                  </div>
                  <span className="text-sm font-medium">Live Data</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="py-16 px-6 bg-muted/50">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {stats.map((stat) => (
              <div key={stat.label} className="text-center">
                <div className="w-14 h-14 bg-white rounded-xl flex items-center justify-center mx-auto mb-4 shadow-sm">
                  <Icon name={stat.icon} size={24} className="text-primary" />
                </div>
                <p className="text-4xl font-bold text-foreground mb-2">{stat.value}</p>
                <p className="text-muted-foreground">{stat.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-bold text-foreground mb-4">Everything You Need for Air Quality</h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Comprehensive tools for monitoring, predicting, and managing air quality across multiple stations.
            </p>
          </div>
          
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((feature) => (
              <div 
                key={feature.title}
                className="bg-card border border-border rounded-xl p-6 hover:shadow-lg hover:border-primary/20 transition-all group"
              >
                <div className={`w-12 h-12 ${feature.color} rounded-xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform`}>
                  <Icon name={feature.icon} size={24} />
                </div>
                <h3 className="text-lg font-semibold text-foreground mb-2">{feature.title}</h3>
                <p className="text-muted-foreground text-sm leading-relaxed">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 px-6">
        <div className="max-w-4xl mx-auto">
          <div className="bg-gradient-to-br from-blue-600 to-purple-600 rounded-3xl p-12 text-center text-white relative overflow-hidden">
            <div className="absolute inset-0 opacity-10">
              <div className="absolute top-0 left-0 w-40 h-40 bg-white rounded-full -translate-x-1/2 -translate-y-1/2"></div>
              <div className="absolute bottom-0 right-0 w-60 h-60 bg-white rounded-full translate-x-1/3 translate-y-1/3"></div>
            </div>
            <div className="relative">
              <h2 className="text-4xl font-bold mb-4">Ready to Monitor Air Quality?</h2>
              <p className="text-xl text-blue-100 mb-8 max-w-2xl mx-auto">
                Join now and get real-time insights into air quality across the Mumbai metropolitan region.
              </p>
              <div className="flex flex-wrap justify-center gap-4">
                <button 
                  onClick={() => navigate('/register')}
                  className="px-8 py-4 bg-white text-blue-600 font-semibold rounded-xl hover:bg-blue-50 transition-colors"
                >
                  Get Started Free
                </button>
                <button 
                  onClick={() => navigate('/login')}
                  className="px-8 py-4 border-2 border-white/50 text-white font-semibold rounded-xl hover:bg-white/10 transition-colors"
                >
                  Sign In
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 px-6 border-t border-border">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row items-center justify-between gap-6">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
                <Icon name="Wind" size={16} className="text-white" />
              </div>
              <span className="font-bold text-foreground">AirWatch<span className="text-blue-600">Pro</span></span>
            </div>
            <p className="text-sm text-muted-foreground">
              Real-time air quality monitoring powered by ML predictions. Data from MPCB monitoring stations.
            </p>
            <div className="flex items-center gap-4 text-sm text-muted-foreground">
              <span>© 2026 AirWatch Pro</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
