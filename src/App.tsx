import React, { useState, useEffect } from "react";
import Sidebar from "./components/Sidebar";
import CurriculumView from "./components/CurriculumView";
import LearningView from "./components/LearningView";
import ReflectionView from "./components/ReflectionView";
import AnalyticsView from "./components/AnalyticsView";
import { ReflectionLog } from "./types";

export default function App() {
  const [currentTab, setCurrentTab] = useState<'curriculum' | 'learning' | 'reflection' | 'analytics'>('curriculum');
  const [reflectionLogs, setReflectionLogs] = useState<ReflectionLog[]>(() => {
    const saved = localStorage.getItem("reflection_logs");
    if (saved) {
      try { return JSON.parse(saved); } catch (e) { console.error(e); }
    }
    return [
      {
        id: "ref-1",
        title: "Source-Grounded Learning Note",
        category: "Indexed Source",
        type: "realization",
        content: "I tested whether the tutor could answer from the currently indexed source instead of giving a generic explanation.",
        timestamp: "Today at 15:30",
        rating: 4,
      }
    ];
  });

  useEffect(() => {
    localStorage.setItem("reflection_logs", JSON.stringify(reflectionLogs));
  }, [reflectionLogs]);

  const addReflectionLog = (log: ReflectionLog) => {
    setReflectionLogs((prev) => [log, ...prev]);
  };

  const renderActiveView = () => {
    switch (currentTab) {
      case 'curriculum':
        return <CurriculumView onResumeLearning={() => setCurrentTab('learning')} />;
      case 'learning':
        return <LearningView onAddReflection={addReflectionLog} />;
      case 'reflection':
        return <ReflectionView reflectionLogs={reflectionLogs} setReflectionLogs={setReflectionLogs} />;
      case 'analytics':
        return <AnalyticsView />;
      default:
        return <CurriculumView onResumeLearning={() => setCurrentTab('learning')} />;
    }
  };

  return (
    <div className="flex bg-[#f9f9ff] min-h-screen text-[#141b2b] font-sans antialiased">
      {/* 1. Left Fixed Sidebar - Desktop only */}
      <Sidebar currentTab={currentTab} onTabChange={setCurrentTab} />

      {/* 2. Main Content Container */}
      <div className="flex-grow flex flex-col lg:ml-64 min-h-screen">
        
        {/* Top Sticky Header */}
        <header className="bg-white border-b border-[#bdc9c6] sticky top-0 z-40 h-16 shrink-0 shadow-sm">
          <div className="flex justify-between items-center px-6 lg:px-8 max-w-[1280px] mx-auto h-full">
            
            {/* Logo elements seen in mobile */}
            <h1 className="lg:hidden font-display text-xl font-bold text-[#005c55] tracking-tight">
              Adaptive Tutor
            </h1>

            {/* Central Desktop-only Menu */}
            <nav className="hidden lg:flex items-center gap-8 h-full">
              {[
                { id: 'curriculum', label: 'Curriculum' },
                { id: 'learning', label: 'Learning' },
                { id: 'reflection', label: 'Reflection' },
                { id: 'analytics', label: 'Analytics' },
              ].map((item) => {
                const isActive = currentTab === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => setCurrentTab(item.id as any)}
                    className={`h-full border-b-2 flex items-center px-1 font-display text-sm font-semibold transition-all duration-200 cursor-pointer ${
                      isActive
                        ? "text-[#005c55] border-[#005c55] font-bold"
                        : "text-[#585f6c] border-transparent hover:text-[#005c55]"
                    }`}
                  >
                    {item.label}
                  </button>
                );
              })}
            </nav>

            {/* User Profile Navigation */}
            <div className="flex items-center gap-2">
              <button className="material-symbols-outlined text-[#585f6c] hover:text-[#005c55] text-2xl p-1 rounded-full hover:bg-gray-100 transition-all cursor-pointer active:scale-95 shadow-sm">
                account_circle
              </button>
            </div>
          </div>
        </header>

        {/* Dynamic page contents body */}
        <main className={`flex-grow p-4 sm:p-6 lg:p-8 max-w-[1280px] mx-auto w-full mb-16 lg:mb-0 ${currentTab === 'learning' ? 'overflow-hidden !p-0 !max-w-none' : ''}`}>
          {renderActiveView()}
        </main>
      </div>

      {/* 3. Mobile Navigation Bottom Bar */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 bg-white border-t border-[#bdc9c6] h-16 flex items-center justify-around z-40 shadow-lg">
        {[
          { id: 'curriculum', label: 'Curriculum', icon: 'map' },
          { id: 'learning', label: 'Learning', icon: 'menu_book' },
          { id: 'reflection', label: 'Reflection', icon: 'psychology' },
          { id: 'analytics', label: 'Analytics', icon: 'analytics' },
        ].map((item) => {
          const isActive = currentTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setCurrentTab(item.id as any)}
              className={`flex flex-col items-center gap-1 cursor-pointer transition-transform ${
                isActive ? "text-[#005c55]" : "text-[#585f6c]"
              }`}
            >
              <span className="material-symbols-outlined text-[20px]" style={{ fontVariationSettings: isActive ? "'FILL' 1" : undefined }}>
                {item.icon}
              </span>
              <span className="text-[10px] font-bold font-display leading-none">
                {item.label}
              </span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}
