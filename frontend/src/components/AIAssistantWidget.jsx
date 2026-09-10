import React, { useState, useEffect, useRef } from 'react';
import { Bot, X, Send, Sparkles, AlertTriangle, ShieldCheck, Activity, RefreshCw } from 'lucide-react';
import { getAIAdvisory, sendAIChatMessage } from '../services/realDataService';

export const AIAssistantWidget = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('advisory'); // 'advisory' | 'chat'
  const [advisory, setAdvisory] = useState(null);
  const [loadingAdvisory, setLoadingAdvisory] = useState(false);

  // Chat state
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: 'Hello! I am AirWatch AI powered by Groq. Ask me anything about current air pollution levels, health precautions, or travel recommendations!'
    }
  ]);
  const [inputMessage, setInputMessage] = useState('');
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    if (isOpen && !advisory) {
      loadAdvisory();
    }
  }, [isOpen]);

  useEffect(() => {
    if (activeTab === 'chat' && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, activeTab]);

  const loadAdvisory = async () => {
    setLoadingAdvisory(true);
    try {
      const data = await getAIAdvisory();
      if (data) {
        setAdvisory(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingAdvisory(false);
    }
  };

  const handleSendMessage = async (e) => {
    e?.preventDefault();
    if (!inputMessage.trim() || isSending) return;

    const userMsg = inputMessage.trim();
    setInputMessage('');
    const updatedHistory = [...messages, { role: 'user', content: userMsg }];
    setMessages(updatedHistory);
    setIsSending(true);

    try {
      const response = await sendAIChatMessage(userMsg, updatedHistory);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: response.reply || 'No response received.' }
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Connection issue. Please try again in a moment.' }
      ]);
    } finally {
      setIsSending(false);
    }
  };

  const getRiskBadgeColor = (level) => {
    switch (level?.toLowerCase()) {
      case 'low':
        return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
      case 'moderate':
        return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
      case 'high':
      case 'severe':
        return 'bg-rose-500/20 text-rose-400 border-rose-500/30';
      default:
        return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
    }
  };

  return (
    <div className="fixed bottom-6 right-6 z-50 font-sans">
      {/* Trigger Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="flex items-center gap-2.5 px-4 py-3 bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white font-medium rounded-full shadow-lg hover:shadow-indigo-500/25 transition-all duration-200 transform hover:scale-105 active:scale-95 border border-white/10"
        >
          <Sparkles className="w-5 h-5 text-amber-300 animate-pulse" />
          <span>AirWatch AI Assistant</span>
          <span className="bg-white/20 text-xs px-2 py-0.5 rounded-full text-indigo-100">Groq</span>
        </button>
      )}

      {/* Main Drawer Modal */}
      {isOpen && (
        <div className="w-[380px] sm:w-[420px] h-[560px] bg-slate-900/95 backdrop-blur-xl border border-slate-700/60 rounded-2xl shadow-2xl flex flex-col overflow-hidden text-slate-100 animate-in fade-in zoom-in-95 duration-200">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 bg-slate-800/80 border-b border-slate-700/50">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center text-indigo-400">
                <Bot className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-1.5 font-semibold text-sm">
                  <span>AirWatch AI</span>
                  <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.2 bg-indigo-500/20 text-indigo-300 rounded border border-indigo-500/30">
                    Groq
                  </span>
                </div>
                <p className="text-[11px] text-slate-400">Real-time Environmental Insights</p>
              </div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700/50 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Navigation Tabs */}
          <div className="flex border-b border-slate-700/50 bg-slate-800/40 text-xs font-medium">
            <button
              onClick={() => setActiveTab('advisory')}
              className={`flex-1 py-2.5 text-center transition-colors border-b-2 flex items-center justify-center gap-1.5 ${
                activeTab === 'advisory'
                  ? 'border-indigo-500 text-indigo-400 bg-slate-800/60 font-semibold'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <Activity className="w-3.5 h-3.5" />
              Health Advisory
            </button>
            <button
              onClick={() => setActiveTab('chat')}
              className={`flex-1 py-2.5 text-center transition-colors border-b-2 flex items-center justify-center gap-1.5 ${
                activeTab === 'chat'
                  ? 'border-indigo-500 text-indigo-400 bg-slate-800/60 font-semibold'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <Bot className="w-3.5 h-3.5" />
              AI Chat
            </button>
          </div>

          {/* Tab 1: Health Advisory */}
          {activeTab === 'advisory' && (
            <div className="flex-1 overflow-y-auto p-4 space-y-3.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">
                  Live Station Advisory
                </span>
                <button
                  onClick={loadAdvisory}
                  disabled={loadingAdvisory}
                  className="flex items-center gap-1 text-[11px] text-indigo-400 hover:text-indigo-300 disabled:opacity-50"
                >
                  <RefreshCw className={`w-3 h-3 ${loadingAdvisory ? 'animate-spin' : ''}`} />
                  Refresh
                </button>
              </div>

              {loadingAdvisory ? (
                <div className="flex flex-col items-center justify-center py-16 space-y-3 text-slate-400">
                  <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
                  <p>Analyzing live telemetry with Groq...</p>
                </div>
              ) : advisory ? (
                <>
                  {/* Station & Risk Level */}
                  <div className="p-3 bg-slate-800/60 border border-slate-700/60 rounded-xl flex items-center justify-between">
                    <div>
                      <div className="text-[11px] text-slate-400">Active Station</div>
                      <div className="font-semibold text-slate-200">{advisory.station_name}</div>
                    </div>
                    {advisory.health_risk_level && (
                      <span className={`px-2.5 py-1 rounded-full text-xs font-semibold border ${getRiskBadgeColor(advisory.health_risk_level)}`}>
                        {advisory.health_risk_level} Risk
                      </span>
                    )}
                  </div>

                  {/* Summary */}
                  {advisory.summary && (
                    <div className="p-3 bg-indigo-950/20 border border-indigo-900/40 rounded-xl space-y-1">
                      <div className="flex items-center gap-1.5 text-indigo-300 font-semibold">
                        <Sparkles className="w-3.5 h-3.5" />
                        Executive Summary
                      </div>
                      <p className="text-slate-300 leading-relaxed">{advisory.summary}</p>
                    </div>
                  )}

                  {/* Protective Measures */}
                  {advisory.protective_measures && (
                    <div className="p-3 bg-slate-800/50 border border-slate-700/50 rounded-xl space-y-1">
                      <div className="flex items-center gap-1.5 text-emerald-400 font-semibold">
                        <ShieldCheck className="w-3.5 h-3.5" />
                        Protection & Precautions
                      </div>
                      <p className="text-slate-300 leading-relaxed">{advisory.protective_measures}</p>
                    </div>
                  )}

                  {/* Vulnerable Groups */}
                  {advisory.vulnerable_groups && (
                    <div className="p-3 bg-slate-800/50 border border-slate-700/50 rounded-xl space-y-1">
                      <div className="flex items-center gap-1.5 text-amber-400 font-semibold">
                        <AlertTriangle className="w-3.5 h-3.5" />
                        Sensitive Groups
                      </div>
                      <p className="text-slate-300 leading-relaxed">{advisory.vulnerable_groups}</p>
                    </div>
                  )}

                  {/* Outdoor Activities */}
                  {advisory.outdoor_activities && (
                    <div className="p-3 bg-slate-800/50 border border-slate-700/50 rounded-xl space-y-1">
                      <div className="flex items-center gap-1.5 text-blue-400 font-semibold">
                        <Activity className="w-3.5 h-3.5" />
                        Outdoor Exercise & Commute
                      </div>
                      <p className="text-slate-300 leading-relaxed">{advisory.outdoor_activities}</p>
                    </div>
                  )}
                </>
              ) : (
                <div className="text-center py-12 text-slate-400">
                  <p>Unable to load advisory at this moment.</p>
                </div>
              )}
            </div>
          )}

          {/* Tab 2: Chat Assistant */}
          {activeTab === 'chat' && (
            <div className="flex-1 flex flex-col overflow-hidden">
              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {messages.map((msg, idx) => (
                  <div
                    key={idx}
                    className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[85%] px-3.5 py-2.5 rounded-2xl text-xs leading-relaxed ${
                        msg.role === 'user'
                          ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-br-sm'
                          : 'bg-slate-800 border border-slate-700/60 text-slate-200 rounded-bl-sm whitespace-pre-line'
                      }`}
                    >
                      {msg.content}
                    </div>
                  </div>
                ))}
                {isSending && (
                  <div className="flex justify-start">
                    <div className="bg-slate-800 border border-slate-700/60 text-slate-400 px-3 py-2 rounded-2xl text-xs flex items-center gap-1.5">
                      <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" />
                      <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce [animation-delay:0.2s]" />
                      <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce [animation-delay:0.4s]" />
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Chat Input Bar */}
              <form
                onSubmit={handleSendMessage}
                className="p-3 bg-slate-800/90 border-t border-slate-700/50 flex items-center gap-2"
              >
                <input
                  type="text"
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  placeholder="Ask about AQI, jogging safety, masks..."
                  className="flex-1 px-3.5 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
                />
                <button
                  type="submit"
                  disabled={!inputMessage.trim() || isSending}
                  className="p-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white rounded-xl transition-colors"
                >
                  <Send className="w-4 h-4" />
                </button>
              </form>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default AIAssistantWidget;
