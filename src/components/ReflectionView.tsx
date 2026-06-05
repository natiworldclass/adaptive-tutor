import React, { useState } from "react";
import { ReflectionLog } from "../types";

interface ReflectionViewProps {
  reflectionLogs: ReflectionLog[];
  setReflectionLogs: React.Dispatch<React.SetStateAction<ReflectionLog[]>>;
}

export default function ReflectionView({ reflectionLogs, setReflectionLogs }: ReflectionViewProps) {
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [selectedFilter, setSelectedFilter] = useState<string>("All");
  const [searchTerm, setSearchTerm] = useState("");
  const [activeLog, setActiveLog] = useState<ReflectionLog | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 4000);
  };

  const handleClearLogs = () => {
    if (window.confirm("Are you sure you want to clear your learning journal history? This action is irreversible.")) {
      setReflectionLogs([]);
      showToast("Cleared learning journal logs successfully.");
    }
  };

  // Extract unique categories dynamically for filters
  const categories = ["All", ...Array.from(new Set(reflectionLogs.map((log) => log.category)))];

  // Filters search and click terms
  const filteredLogs = reflectionLogs.filter((log) => {
    const matchesCategory = selectedFilter === "All" || log.category === selectedFilter;
    const matchesSearch =
      log.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      log.content.toLowerCase().includes(searchTerm.toLowerCase()) ||
      log.category.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesCategory && matchesSearch;
  });

  // Calculate high-quality analytics metrics dynamically
  const totalLogs = reflectionLogs.length;
  const avgRating = totalLogs
    ? (reflectionLogs.reduce((acc, curr) => acc + (curr.rating || 0), 0) / totalLogs).toFixed(1)
    : "0.0";
  
  const correctCount = reflectionLogs.filter((log) => log.content.includes("[Success Path]")).length;
  const pivotCount = reflectionLogs.filter((log) => log.content.includes("[Wrong Assumption]") || log.type === "journal").length;

  return (
    <div className="space-y-6 pb-16 animate-fade-in">
      {/* Toast Feedback Notification */}
      {toastMessage && (
        <div className="fixed top-6 right-6 z-50 bg-slate-900 text-white rounded-2xl px-5 py-3.5 shadow-xl flex items-center gap-3 border border-slate-800 animate-slide-in">
          <span className="material-symbols-outlined text-indigo-400">info</span>
          <span className="text-xs font-semibold">{toastMessage}</span>
        </div>
      )}

      {/* Header section with clean minimalism */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <span className="text-indigo-600 font-display text-xs font-bold uppercase tracking-widest">
            Scholar Archive
          </span>
          <h2 className="font-display text-2xl font-extrabold text-[#141b2b]">
            Learning Stream & Reflection Journal
          </h2>
          <p className="text-slate-500 font-sans text-xs mt-1">
            Browse and audit dynamic self-evaluation records logged during your AI tutor dialogue.
          </p>
        </div>

        {totalLogs > 0 && (
          <button
            onClick={handleClearLogs}
            className="px-4 py-2 border border-rose-200 text-rose-600 rounded-full font-display text-xs font-bold hover:bg-rose-50 active:scale-95 transition-all cursor-pointer flex items-center gap-1.5"
          >
            <span className="material-symbols-outlined text-base">delete_sweep</span>
            <span>Clear Logs</span>
          </button>
        )}
      </div>

      {/* Metacognitive Statistics Dashboard Panel */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[10px] font-display font-bold uppercase tracking-wider">Total Records</span>
            <span className="material-symbols-outlined text-indigo-600 text-lg">history_edu</span>
          </div>
          <div className="mt-4">
            <span className="text-2xl font-display font-black text-slate-800">{totalLogs}</span>
            <p className="text-[10px] text-slate-400 mt-1 font-sans">Active reflection milestones</p>
          </div>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[10px] font-display font-bold uppercase tracking-wider">Tutor Calibration</span>
            <span className="material-symbols-outlined text-amber-500 text-lg">star</span>
          </div>
          <div className="mt-4 flex items-baseline gap-1">
            <span className="text-2xl font-display font-black text-slate-800">{avgRating}</span>
            <span className="text-slate-400 text-xs font-sans">/5.0</span>
            <p className="text-[10px] text-slate-400 mt-1 font-sans block w-full">Avg conceptual understanding</p>
          </div>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[10px] font-display font-bold uppercase tracking-wider">Direct Paths</span>
            <span className="material-symbols-outlined text-emerald-500 text-lg">check_circle</span>
          </div>
          <div className="mt-4">
            <span className="text-2xl font-display font-black text-slate-800">{correctCount}</span>
            <p className="text-[10px] text-slate-400 mt-1 font-sans">Successful reasoning loops</p>
          </div>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[10px] font-display font-bold uppercase tracking-wider">Assumption Gaps</span>
            <span className="material-symbols-outlined text-[#8a3ffc] text-lg">published_with_changes</span>
          </div>
          <div className="mt-4">
            <span className="text-2xl font-display font-black text-slate-800">{pivotCount}</span>
            <p className="text-[10px] text-slate-400 mt-1 font-sans">Reconciled logical pivots</p>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar Section */}
      <div className="bg-white border border-slate-200 rounded-2xl p-4 flex flex-col sm:flex-row gap-3 items-center justify-between shadow-xs">
        {/* Dynamic Category Pill Filters */}
        <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto hide-scrollbar self-start sm:self-center">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setSelectedFilter(cat)}
              className={`px-3 py-1.5 rounded-full text-xs font-display font-bold transition-all shrink-0 cursor-pointer ${
                selectedFilter === cat
                  ? "bg-slate-900 text-white shadow-sm"
                  : "bg-slate-100 hover:bg-slate-200 text-slate-600"
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Dynamic Search Box */}
        <div className="relative w-full sm:w-64 shrink-0">
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-slate-50 border border-slate-200 rounded-xl py-2 pl-9 pr-4 text-xs font-sans outline-none focus:bg-white focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 text-slate-800 transition-all"
            placeholder="Search journal records..."
          />
          <span className="material-symbols-outlined absolute left-3 top-2.5 text-slate-400 text-sm select-none">
            search
          </span>
        </div>
      </div>

      {/* Main timeline stream view of logs */}
      <div className="bg-white border border-slate-200 rounded-3xl p-6 md:p-8 shadow-sm">
        <h3 className="font-display text-sm font-black text-slate-800 mb-6 uppercase tracking-wider flex items-center gap-2">
          <span className="material-symbols-outlined text-indigo-600 text-[20px]">feed</span>
          <span>Timeline of Mental Calibration Logs</span>
        </h3>

        {filteredLogs.length === 0 ? (
          <div className="text-center py-16 px-4 flex flex-col items-center justify-center">
            <div className="w-16 h-16 bg-slate-50 rounded-2xl flex items-center justify-center border border-slate-100 mb-4 text-slate-300">
              <span className="material-symbols-outlined text-3xl">menu_book</span>
            </div>
            <h4 className="font-display text-sm font-bold text-slate-800">Your journal is currently blank</h4>
            <p className="text-xs text-slate-400 font-sans max-w-sm mt-1 mb-5">
              Launch tutor chat questions, confirm answers, and prompt metacognitive self-evaluations inside the learning room to populate logs here!
            </p>
          </div>
        ) : (
          <div className="relative border-l border-slate-100 ml-3 md:ml-4 pl-6 md:pl-8 space-y-8 pb-4">
            {filteredLogs.map((log) => {
              const isSuccess = log.content.includes("[Success Path]");
              const isPivot = log.content.includes("[Wrong Assumption]");
              
              return (
                <div key={log.id} className="relative group">
                  {/* Timeline node icon */}
                  <div className={`absolute -left-[35px] md:-left-[43px] top-1.5 w-7 h-7 sm:w-8 sm:h-8 rounded-full border bg-white flex items-center justify-center transition-all ${
                    isSuccess 
                      ? "border-emerald-300 text-emerald-600" 
                      : isPivot 
                      ? "border-amber-300 text-amber-500" 
                      : "border-indigo-300 text-indigo-600"
                  }`}>
                    <span className="material-symbols-outlined text-sm sm:text-base select-none">
                      {isSuccess ? "verified" : isPivot ? "published_with_changes" : "stars"}
                    </span>
                  </div>

                  {/* Log Content Card */}
                  <div className="bg-slate-50 border border-slate-150 rounded-2xl p-5 hover:border-slate-300 hover:shadow-xs transition-all relative">
                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-1 mb-3">
                      <div className="flex items-center gap-2">
                        <span className={`px-2.5 py-0.5 rounded-full font-display text-[9px] font-bold uppercase ${
                          isSuccess 
                            ? "bg-emerald-50 text-emerald-700 border border-emerald-100" 
                            : isPivot 
                            ? "bg-amber-50 text-amber-700 border border-amber-100" 
                            : "bg-indigo-50 text-indigo-700 border border-indigo-100"
                        }`}>
                          {log.category}
                        </span>
                        <span className="text-[10px] text-slate-400 font-mono font-bold">
                          ID: {log.id}
                        </span>
                      </div>
                      <span className="text-[10px] font-sans text-slate-400 font-semibold">{log.timestamp}</span>
                    </div>

                    <h4 className="font-display font-extrabold text-sm text-slate-800 mb-2 leading-snug">
                      {log.title}
                    </h4>

                    {/* Styled parse explanation */}
                    <div className="bg-white border border-slate-100 rounded-xl p-3.5 space-y-3 mb-4">
                      {isSuccess ? (
                        <>
                          <div className="text-[11px] font-sans text-slate-600 leading-normal">
                            <span className="font-display text-[10px] font-black uppercase text-emerald-600 block mb-0.5">My Reasoning Path</span>
                            "{log.content.split("| [Takeaway]:")[0].replace("[Success Path]:", "").trim().replace(/^"|"$/g, "")}"
                          </div>
                          <div className="text-[11px] font-sans text-slate-600 border-t border-slate-100 pt-2.5 leading-normal">
                            <span className="font-display text-[10px] font-black uppercase text-slate-400 block mb-0.5">Key Lesson Takeaway</span>
                            "{log.content.split("| [Takeaway]:")[1]?.trim().replace(/^"|"$/g, "")}"
                          </div>
                        </>
                      ) : isPivot ? (
                        <>
                          <div className="text-[11px] font-sans text-slate-600 leading-normal">
                            <span className="font-display text-[10px] font-black uppercase text-rose-500 block mb-0.5">Wrong Assumption</span>
                            "{log.content.split("| [Correct Path]:")[0].replace("[Wrong Assumption]:", "").trim().replace(/^"|"$/g, "")}"
                          </div>
                          <div className="text-[11px] font-sans text-slate-600 border-t border-slate-100 pt-2.5 leading-normal">
                            <span className="font-display text-[10px] font-black uppercase text-emerald-600 block mb-0.5">Corrective Pathway</span>
                            "{log.content.split("| [Correct Path]:")[1]?.trim().replace(/^"|"$/g, "")}"
                          </div>
                        </>
                      ) : (
                        <p className="text-[11px] font-sans text-slate-600 leading-relaxed italic">
                          "{log.content}"
                        </p>
                      )}
                    </div>

                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 pt-2 border-t border-slate-150">
                      {log.rating && (
                        <div className="flex gap-0.5 items-center select-none">
                          <span className="text-[10px] font-display font-bold uppercase text-slate-400 mr-1.5">Learning Calibration:</span>
                          {Array.from({ length: 5 }).map((_, i) => (
                            <span
                              key={i}
                              className={`material-symbols-outlined text-sm ${
                                i < (log.rating || 0) ? "text-amber-500" : "text-slate-200"
                              }`}
                              style={{ fontVariationSettings: i < (log.rating || 0) ? "'FILL' 1" : undefined }}
                            >
                              star
                            </span>
                          ))}
                        </div>
                      )}

                      <button
                        onClick={() => setActiveLog(log)}
                        className="text-xs font-display font-bold text-indigo-600 hover:text-indigo-800 transition-all flex items-center gap-1 shrink-0 ml-auto cursor-pointer"
                      >
                        <span>Inspect Full Entry</span>
                        <span className="material-symbols-outlined text-[14px]">open_in_new</span>
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Floating active journal entry inspector modal */}
      {activeLog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs animate-fade-in">
          <div className="bg-white max-w-xl w-full rounded-3xl border border-slate-200 shadow-2xl p-6 sm:p-8 flex flex-col gap-5 relative animate-scale-up">
            <header className="flex justify-between items-start">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-indigo-600">bookmark_added</span>
                <span className="font-display text-[10px] font-black uppercase text-slate-400 tracking-wider">
                  Log Entry Inspector
                </span>
              </div>
              <button
                onClick={() => setActiveLog(null)}
                className="w-8 h-8 rounded-full border border-slate-100 bg-slate-50 text-slate-400 hover:text-slate-600 active:scale-90 flex items-center justify-center transition-all cursor-pointer"
              >
                <span className="material-symbols-outlined text-base">close</span>
              </button>
            </header>

            <div className="space-y-1">
              <span className="font-display text-[10px] font-bold text-indigo-600 uppercase tracking-widest">{activeLog.category}</span>
              <h3 className="font-display text-lg font-black text-slate-800 leading-snug">
                {activeLog.title}
              </h3>
              <p className="font-sans text-[10px] text-slate-400 mt-1">Logged on: {activeLog.timestamp}</p>
            </div>

            <div className="bg-slate-50 border border-slate-100 p-5 rounded-2xl space-y-4">
              {activeLog.content.includes("[Success Path]") ? (
                <>
                  <div className="space-y-1">
                    <span className="font-display text-[10px] font-black text-emerald-600 uppercase tracking-wide block">How I Solved It</span>
                    <p className="font-sans text-xs text-slate-700 leading-relaxed bg-white p-3 rounded-xl border border-slate-100 shadow-2xs">
                      {activeLog.content.split("| [Takeaway]:")[0].replace("[Success Path]:", "").trim().replace(/^"|"$/g, "")}
                    </p>
                  </div>
                  <div className="space-y-1">
                    <span className="font-display text-[10px] font-black text-slate-400 uppercase tracking-wide block">Study Lesson / Rule</span>
                    <p className="font-sans text-xs text-slate-700 leading-relaxed bg-white p-3 rounded-xl border border-slate-100 shadow-2xs">
                      {activeLog.content.split("| [Takeaway]:")[1]?.trim().replace(/^"|"$/g, "")}
                    </p>
                  </div>
                </>
              ) : activeLog.content.includes("[Wrong Assumption]") ? (
                <>
                  <div className="space-y-1">
                    <span className="font-display text-[10px] font-black text-rose-500 uppercase tracking-wide block">Misconception Logged</span>
                    <p className="font-sans text-xs text-slate-700 leading-relaxed bg-white p-3 rounded-xl border border-slate-100 shadow-2xs">
                      {activeLog.content.split("| [Correct Path]:")[0].replace("[Wrong Assumption]:", "").trim().replace(/^"|"$/g, "")}
                    </p>
                  </div>
                  <div className="space-y-1">
                    <span className="font-display text-[10px] font-black text-emerald-600 uppercase tracking-wide block">How to Correct It</span>
                    <p className="font-sans text-xs text-slate-700 leading-relaxed bg-white p-3 rounded-xl border border-slate-100 shadow-2xs">
                      {activeLog.content.split("| [Correct Path]:")[1]?.trim().replace(/^"|"$/g, "")}
                    </p>
                  </div>
                </>
              ) : (
                <p className="font-sans text-xs text-slate-700 leading-relaxed bg-white p-3 rounded-xl border border-slate-100 shadow-2xs italic">
                  "{activeLog.content}"
                </p>
              )}
            </div>

            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 pt-3 border-t border-slate-100">
              {activeLog.rating && (
                <div className="flex gap-0.5 items-center select-none">
                  <span className="text-[10px] font-display font-bold uppercase text-slate-400 mr-1.5 text-xs">Calibrated Competency Level:</span>
                  {Array.from({ length: 5 }).map((_, i) => (
                    <span
                      key={i}
                      className={`material-symbols-outlined text-base ${
                        i < (activeLog.rating || 0) ? "text-amber-500" : "text-slate-200"
                      }`}
                      style={{ fontVariationSettings: i < (activeLog.rating || 0) ? "'FILL' 1" : undefined }}
                    >
                      star
                    </span>
                  ))}
                </div>
              )}

              <button
                onClick={() => setActiveLog(null)}
                className="w-full sm:w-auto px-5 py-2.5 bg-slate-900 hover:bg-slate-800 text-white font-display text-xs font-bold rounded-xl transition-all cursor-pointer text-center"
              >
                Done Inspecting
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
