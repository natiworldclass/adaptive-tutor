import React from "react";

interface SidebarProps {
  currentTab: 'curriculum' | 'learning' | 'reflection' | 'analytics';
  onTabChange: (tab: 'curriculum' | 'learning' | 'reflection' | 'analytics') => void;
}

export default function Sidebar({ currentTab, onTabChange }: SidebarProps) {
  const menuItems = [
    { id: 'curriculum', label: 'Curriculum', icon: 'map' },
    { id: 'learning', label: 'Learning', icon: 'menu_book' },
    { id: 'reflection', label: 'Reflection', icon: 'psychology' },
    { id: 'analytics', label: 'Analytics', icon: 'analytics' },
  ] as const;

  return (
    <aside className="hidden lg:flex flex-col gap-6 p-6 w-64 h-screen bg-white border-r border-slate-200 fixed left-0 top-0 text-slate-900">
      {/* Brand Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center">
          <div className="w-4 h-4 bg-white rounded-sm"></div>
        </div>
        <div>
          <h1 className="font-display text-lg font-bold text-slate-900 tracking-tight leading-none">Adaptive Tutor</h1>
          <p className="font-sans text-[10px] font-bold text-slate-400 uppercase tracking-wider mt-1">Source-Grounded Tutor</p>
        </div>
      </div>

      {/* Navigation Links */}
      <nav className="flex flex-col gap-1.5 flex-1">
        {menuItems.map((item) => {
          const isActive = currentTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onTabChange(item.id)}
              className={`flex items-center gap-3 rounded-xl px-4 py-2.5 text-left font-display text-sm font-semibold transition-all duration-200 interactive-scale cursor-pointer ${
                isActive
                  ? 'bg-indigo-50 text-indigo-700 shadow-none'
                  : 'text-slate-500 hover:bg-slate-50'
              }`}
            >
              <span className="material-symbols-outlined text-[20px]" style={{ fontVariationSettings: isActive ? "'FILL' 1" : undefined }}>
                {item.icon}
              </span>
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      {/* Bottom Sidebar Controls / widgets matching design */}
      <div className="mt-auto flex flex-col gap-3 pt-4 border-t border-slate-100">
        {/* Offline Cache Status Widget configured as a neat bento card */}
        <div className="p-4 bg-slate-900 rounded-2xl text-white">
          <p className="text-[9px] text-slate-400 uppercase tracking-wider font-bold mb-1">Session state</p>
          <p className="font-semibold text-sm mb-3">Local Offline Cache</p>
          <div className="flex items-center gap-2 text-[11px] text-amber-300">
            <span className="material-symbols-outlined text-xs animate-pulse">wifi_off</span>
            <span>Intermittent Connection</span>
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <button className="flex items-center gap-3 text-slate-500 font-display text-xs font-semibold px-4 py-2 hover:bg-slate-50 rounded-xl transition-all duration-200 cursor-pointer">
            <span className="material-symbols-outlined text-[18px]">settings</span>
            <span>Settings</span>
          </button>
          <button className="flex items-center gap-3 text-slate-500 font-display text-xs font-semibold px-4 py-2 hover:bg-slate-50 rounded-xl transition-all duration-200 cursor-pointer">
            <span className="material-symbols-outlined text-[18px]">help</span>
            <span>Help Center</span>
          </button>
        </div>
      </div>
    </aside>
  );
}
