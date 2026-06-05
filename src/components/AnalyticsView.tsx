import React, { useState } from "react";
import { CohortTopic, Intervention } from "../types";

export default function AnalyticsView() {
  const [topics] = useState<CohortTopic[]>([
    {
      id: "t-1",
      rank: "#1",
      moduleTitle: "Retrieval Quality",
      topicTitle: "Questions should retrieve chunks that directly support the answer.",
      difficultyScore: 8.8,
      difficultyText: "High",
      avgTimeMinutes: 12,
      confusionTrend: "Spiking",
    },
    {
      id: "t-2",
      rank: "#2",
      moduleTitle: "Answer Grounding",
      topicTitle: "Tutor responses should avoid unsupported outside knowledge.",
      difficultyScore: 7.1,
      difficultyText: "High",
      avgTimeMinutes: 9,
      confusionTrend: "Stable",
    },
    {
      id: "t-3",
      rank: "#3",
      moduleTitle: "Reflection Loop",
      topicTitle: "Students should record what they understood after each answer.",
      difficultyScore: 4.2,
      difficultyText: "Low",
      avgTimeMinutes: 5,
      confusionTrend: "Declining",
    },
  ]);

  const [expandedTopicId, setExpandedTopicId] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [interventions, setInterventions] = useState<Intervention[]>([
    {
      id: "int-1",
      title: "Reject unrelated questions from the active source",
      description: "If retrieval is weak or off-topic, the tutor should say the uploaded material does not cover the question.",
      type: "warning",
      deployed: false,
    },
    {
      id: "int-2",
      title: "Collect tester reflections after answers",
      description: "Use saved reflections to see whether the explanation actually helped the student reason from the source.",
      type: "auto_fix",
      deployed: false,
    },
  ]);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 4000);
  };

  const handleDeployIntervention = (id: string) => {
    setInterventions((prev) => prev.map((item) => (item.id === id ? { ...item, deployed: true } : item)));
    showToast("Testing action marked as active.");
  };

  const handleExportReport = () => {
    showToast("Prototype testing report placeholder generated.");
  };

  const handleToggleDetails = (id: string) => {
    setExpandedTopicId(expandedTopicId === id ? null : id);
  };

  return (
    <div className="space-y-6 relative pb-12">
      {toastMessage && (
        <div className="fixed top-6 right-6 z-50 bg-slate-900 text-white rounded-2xl px-5 py-3.5 shadow-xl flex items-center gap-3 border border-slate-800 animate-slide-in">
          <span className="material-symbols-outlined text-indigo-400">info</span>
          <span className="text-xs font-semibold">{toastMessage}</span>
        </div>
      )}

      <header className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <nav className="flex gap-1.5 text-xs font-display font-bold text-slate-400 mb-1 pointer-events-none uppercase tracking-wider">
            <span>Dashboard</span>
            <span>/</span>
            <span className="text-indigo-600">Prototype Oversight</span>
          </nav>
          <h1 className="font-display text-2xl font-extrabold text-slate-950">Analytics: Source-Grounded Tutor</h1>
        </div>
        <div className="flex gap-2">
          <button className="flex items-center gap-2 px-4 py-2 border border-slate-200 bg-white rounded-full font-display text-xs font-semibold hover:bg-slate-50 transition-all cursor-pointer active:scale-95 select-none text-slate-700">
            <span className="material-symbols-outlined text-[16px]">checklist</span>
            <span>Week 3 Tests</span>
          </button>
          <button
            onClick={handleExportReport}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-full font-display text-xs font-bold hover:bg-indigo-700 transition-all cursor-pointer shadow-md active:scale-95"
          >
            <span className="material-symbols-outlined text-[16px]">download</span>
            <span>Export Report</span>
          </button>
        </div>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-5 border border-slate-200 rounded-3xl flex flex-col gap-1.5 shadow-sm">
          <div className="flex items-center justify-between text-slate-400">
            <span className="font-display text-xs font-bold uppercase tracking-wider">Uploads Indexed</span>
            <span className="material-symbols-outlined text-indigo-600 text-lg">upload_file</span>
          </div>
          <div className="font-display text-3xl font-black text-slate-950">
            1 <span className="text-sm font-normal text-slate-400">active source</span>
          </div>
          <div className="flex items-center gap-1 text-[11px] font-sans text-emerald-600 font-bold mt-1">
            <span className="material-symbols-outlined text-sm">trending_up</span>
            <span>PDF/TXT pipeline working</span>
          </div>
        </div>

        <div className="bg-white p-5 border border-slate-200 rounded-3xl flex flex-col gap-1.5 shadow-sm">
          <div className="flex items-center justify-between text-slate-400">
            <span className="font-display text-xs font-bold uppercase tracking-wider">Embedding Cap</span>
            <span className="material-symbols-outlined text-indigo-600 text-lg">speed</span>
          </div>
          <div className="font-display text-3xl font-black text-slate-950">
            90 <span className="text-sm font-normal text-slate-400">chunks</span>
          </div>
          <div className="flex items-center gap-1 text-[11px] font-sans text-rose-500 font-bold mt-1">
            <span className="material-symbols-outlined text-sm">warning</span>
            <span>Temporary free-tier limit</span>
          </div>
        </div>

        <div className="col-span-1 md:col-span-2 bg-white p-5 border border-slate-200 rounded-3xl flex flex-col gap-3 shadow-sm">
          <div className="flex items-center justify-between text-slate-400">
            <span className="font-display text-xs font-bold uppercase tracking-wider">Success Criteria</span>
            <span className="material-symbols-outlined text-indigo-600 text-lg">fact_check</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <div className="flex flex-col bg-indigo-50/40 p-3 rounded-2xl border border-indigo-100">
              <span className="font-sans text-[10px] font-bold text-indigo-600 uppercase tracking-wide">Upload</span>
              <span className="font-display text-xs font-bold text-slate-800">Source accepted</span>
            </div>
            <div className="flex flex-col bg-slate-50 p-3 rounded-2xl border border-slate-100">
              <span className="font-sans text-[10px] font-bold text-slate-500 uppercase tracking-wide">Retrieve</span>
              <span className="font-display text-xs font-bold text-slate-800">Relevant chunk shown</span>
            </div>
            <div className="flex flex-col bg-slate-50 p-3 rounded-2xl border border-slate-100">
              <span className="font-sans text-[10px] font-bold text-slate-500 uppercase tracking-wide">Explain</span>
              <span className="font-display text-xs font-bold text-slate-800">Answer cites source</span>
            </div>
          </div>
        </div>
      </div>

      <section className="bg-white border border-slate-200 rounded-3xl shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-200 flex justify-between items-center bg-slate-50">
          <h3 className="font-display text-sm font-extrabold text-slate-900 uppercase tracking-wider">Testing Risk Map</h3>
          <span className="font-sans text-xs text-slate-500 font-bold bg-white border border-slate-200 px-3 py-1 rounded-full shadow-xs">
            Prototype Metrics
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead className="bg-slate-50/50 text-slate-400 font-display text-xs uppercase tracking-wider border-b border-slate-100">
              <tr>
                <th className="px-5 py-3.5 font-bold">Rank</th>
                <th className="px-5 py-3.5 font-bold">Area</th>
                <th className="px-5 py-3.5 font-bold">Risk Score</th>
                <th className="px-5 py-3.5 font-bold">Test Time</th>
                <th className="px-5 py-3.5 font-bold">Trend</th>
                <th className="px-3 py-3.5 font-bold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 select-none">
              {topics.map((tp) => {
                const isExpanded = expandedTopicId === tp.id;
                const progressWidths = {
                  High: "w-[88%]",
                  Mid: "w-[62%]",
                  Low: "w-[34%]",
                };
                const tagColorStyles = {
                  Spiking: "bg-rose-50 text-rose-600 border-rose-200/50",
                  Stable: "bg-indigo-50/60 text-slate-500 border-indigo-100",
                  Declining: "bg-emerald-50 text-emerald-600 border-emerald-200",
                };

                return (
                  <React.Fragment key={tp.id}>
                    <tr className="hover:bg-slate-50/50 transition-colors">
                      <td className="px-5 py-4 font-display text-sm font-extrabold text-indigo-600">{tp.rank}</td>
                      <td className="px-5 py-4">
                        <div className="flex flex-col">
                          <span className="font-display text-sm font-bold text-slate-900">{tp.moduleTitle}</span>
                          <span className="font-sans text-xs text-slate-500 mt-0.5">{tp.topicTitle}</span>
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-2">
                          <div className="w-24 h-2 bg-slate-100 rounded-full overflow-hidden shrink-0">
                            <div
                              className={`h-full ${
                                tp.difficultyText === "High"
                                  ? "bg-rose-500"
                                  : tp.difficultyText === "Mid"
                                  ? "bg-indigo-500"
                                  : "bg-emerald-500"
                              } ${progressWidths[tp.difficultyText]}`}
                            ></div>
                          </div>
                          <span className={`font-display text-xs font-bold leading-none ${tp.difficultyText === "High" ? "text-rose-600" : "text-slate-700"}`}>
                            {tp.difficultyText} ({tp.difficultyScore}/10)
                          </span>
                        </div>
                      </td>
                      <td className="px-5 py-4 font-sans text-xs text-slate-600 font-bold">{tp.avgTimeMinutes}m</td>
                      <td className="px-5 py-4">
                        <span className={`px-2.5 py-1 rounded-full font-display text-[10px] font-bold uppercase border ${tagColorStyles[tp.confusionTrend]}`}>
                          {tp.confusionTrend}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-right">
                        <button
                          onClick={() => handleToggleDetails(tp.id)}
                          className="text-indigo-600 font-display text-xs font-bold hover:text-indigo-800 cursor-pointer hover:underline"
                        >
                          {isExpanded ? "Hide Details" : "View Details"}
                        </button>
                      </td>
                    </tr>

                    {isExpanded && (
                      <tr>
                        <td colSpan={6} className="bg-slate-50/50 px-6 py-4 border-l-4 border-indigo-600">
                          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 text-xs text-slate-600">
                            <div className="space-y-1">
                              <p className="font-display font-black text-slate-900">What To Test:</p>
                              <ul className="list-disc pl-4 space-y-0.5 font-sans text-slate-500">
                                <li>Ask one question clearly answered in the source.</li>
                                <li>Ask one question outside the source.</li>
                                <li>Check whether the shown chunk supports the answer.</li>
                              </ul>
                            </div>
                            <div className="space-y-1">
                              <p className="font-display font-black text-slate-900">Product Risk:</p>
                              <p className="font-sans leading-relaxed text-slate-500">
                                Weak grounding makes the app look like a generic AI wrapper, which is the main judging risk.
                              </p>
                            </div>
                            <div className="space-y-1">
                              <p className="font-display font-black text-slate-900">Pass Condition:</p>
                              <div className="flex items-center gap-1.5 text-emerald-600 font-bold mt-1">
                                <span className="material-symbols-outlined text-sm">check_circle</span>
                                <span>Answer and source panel agree.</span>
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="p-4 bg-slate-50 text-slate-400 font-sans text-xs italic">
          Replace these placeholder metrics with real tester logs after the next round of app testing.
        </div>
      </section>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="md:col-span-2 bg-indigo-50/40 p-5 rounded-3xl border border-slate-150 flex flex-col justify-between">
          <div>
            <h4 className="font-display text-xs font-bold uppercase tracking-wider text-indigo-600 mb-4">
              Active Testing Actions
            </h4>

            <div className="space-y-3">
              {interventions.map((item) => (
                <div key={item.id} className="flex items-center justify-between bg-white p-4 rounded-2xl border border-slate-200 shadow-xs">
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
                        item.type === "warning" ? "bg-rose-50 text-rose-500" : "bg-indigo-50 text-indigo-600"
                      }`}
                    >
                      <span className="material-symbols-outlined text-lg">{item.type === "warning" ? "warning" : "auto_fix_high"}</span>
                    </div>
                    <div className="flex flex-col pr-4">
                      <p className="font-display text-xs font-bold text-slate-900">{item.title}</p>
                      <p className="font-sans text-[11px] text-slate-400 mt-0.5">{item.description}</p>
                    </div>
                  </div>

                  {item.deployed ? (
                    <span className="bg-emerald-50 text-emerald-600 text-[10px] font-bold uppercase tracking-wide px-3 py-1.5 rounded-xl border border-emerald-200 shrink-0 select-none">
                      Active
                    </span>
                  ) : (
                    <button
                      onClick={() => handleDeployIntervention(item.id)}
                      className="px-4 py-1.5 bg-indigo-600 text-white rounded-xl font-display text-xs font-bold hover:bg-indigo-700 active:scale-95 transition-all cursor-pointer shadow-xs shrink-0 whitespace-nowrap"
                    >
                      Mark Active
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="bg-white rounded-3xl border border-slate-200 overflow-hidden relative shadow-sm h-60 p-6 flex flex-col justify-between">
          <div>
            <span className="font-display text-[9px] font-bold text-indigo-600 uppercase tracking-wider">Real-World Readiness</span>
            <h5 className="font-display text-base font-bold text-slate-900 mt-2">Not Just A Chatbot</h5>
            <p className="font-sans text-xs text-slate-500 leading-relaxed mt-2">
              The defensible product story is upload, retrieve, explain, verify, and reflect. That is the loop judges should see.
            </p>
          </div>
          <div className="h-2 bg-gradient-to-r from-indigo-500 to-emerald-500 rounded-full w-full"></div>
        </div>
      </div>
    </div>
  );
}
