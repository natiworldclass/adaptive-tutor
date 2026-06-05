import React, { useEffect, useState } from "react";
import { CurriculumNode } from "../types";

interface CurriculumViewProps {
  onResumeLearning: () => void;
}

interface SourceMetadata {
  file_name: string;
  chunk_count: number;
  preview_title?: string;
  preview_text?: string;
}

const workflowNodes: CurriculumNode[] = [
  {
    id: "node-1",
    title: "Source Uploaded",
    subtitle: "A learning source has been selected for this session.",
    status: "mastered",
  },
  {
    id: "node-2",
    title: "Source-Grounded Questions",
    subtitle: "Ask questions and compare each answer with retrieved evidence.",
    status: "in-progress",
    masteryPercentage: 45,
    lastReview: "Current session",
    nextReview: "After 3 checks",
    details: "Current focus: retrieve, explain, verify, and reflect.",
  },
  {
    id: "node-3",
    title: "Understanding Checks",
    subtitle: "Save short reflections after answers to build mastery evidence.",
    status: "locked",
    prerequisite: "Complete source-grounded questions",
  },
  {
    id: "node-4",
    title: "Review Weak Areas",
    subtitle: "Use future analytics to revisit confusing sections from the uploaded source.",
    status: "locked",
    prerequisite: "Complete understanding checks",
  },
];

export default function CurriculumView({ onResumeLearning }: CurriculumViewProps) {
  const [source, setSource] = useState<SourceMetadata | null>(null);
  const [nodes] = useState<CurriculumNode[]>(workflowNodes);
  const [activeNodeId, setActiveNodeId] = useState<string | null>("node-2");
  const [showNodeStats, setShowNodeStats] = useState(true);

  useEffect(() => {
    const loadCurrentSource = async () => {
      try {
        const response = await fetch("/api/sources/current");
        const data = await response.json();
        setSource(data.source || null);
      } catch (error) {
        console.error("Failed to load current source:", error);
      }
    };

    loadCurrentSource();
  }, []);

  const sourceTitle = source?.file_name || "No Source Selected";
  const sourceSubtitle = source
    ? `${source.chunk_count} indexed chunks ready for testing`
    : "Upload a PDF or TXT file in Learning to start source-grounded tutoring.";

  const handleNodeClick = (nodeId: string) => {
    setActiveNodeId(activeNodeId === nodeId ? null : nodeId);
    if (nodeId === "node-2") {
      setShowNodeStats((prev) => !prev);
    }
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
      <section className="col-span-12 lg:col-span-4 flex flex-col gap-6">
        <div className="bg-indigo-600 rounded-3xl p-8 text-white relative overflow-hidden flex flex-col justify-between shadow-xl shadow-indigo-100 min-h-[320px]">
          <div className="relative z-10">
            <span className="font-sans text-xs font-semibold bg-white/20 backdrop-blur-md text-white px-3 py-1 rounded-full uppercase tracking-wider">
              Active Now
            </span>
            <h2 className="font-display text-3xl font-extrabold text-white mt-6 mb-2 leading-tight break-words">
              Current Source:<br />
              {sourceTitle}
            </h2>
            <p className="font-sans text-xs text-indigo-100 opacity-90">{sourceSubtitle}</p>
          </div>

          <div className="relative z-10 mt-6">
            <div className="flex items-center justify-between text-xs font-bold text-indigo-50 mb-2">
              <span>Testing Progress</span>
              <span>45%</span>
            </div>
            <div className="flex items-center gap-4 mb-6">
              <div className="flex-grow h-2 bg-white/20 rounded-full overflow-hidden">
                <div className="h-full bg-white w-[45%] transition-all duration-500"></div>
              </div>
            </div>

            <button
              onClick={onResumeLearning}
              className="w-full bg-white text-indigo-600 font-display text-sm font-bold py-3.5 px-4 rounded-2xl hover:bg-slate-50 active:scale-[0.98] transition-all flex items-center justify-center gap-2 cursor-pointer shadow-md"
            >
              <span className="material-symbols-outlined text-[18px]" style={{ fontVariationSettings: "'FILL' 1" }}>
                play_arrow
              </span>
              Resume Learning Session
            </button>
          </div>
        </div>

        <div className="bg-white border border-slate-200 p-6 rounded-3xl flex flex-col justify-between shadow-sm">
          <div>
            <h3 className="font-display text-slate-500 text-sm font-medium">Session Checks</h3>
            <div className="flex items-end gap-2 mt-2">
              <span className="font-display text-4xl font-extrabold text-indigo-600">0</span>
              <span className="font-sans text-sm font-semibold text-slate-700 pb-1">Saved Reflections</span>
            </div>
          </div>
          <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden mt-4">
            <div className="bg-emerald-500 h-full w-[15%]"></div>
          </div>
        </div>
      </section>

      <section className="col-span-12 lg:col-span-8">
        <div className="bg-white border border-slate-200 p-6 sm:p-8 rounded-3xl shadow-sm">
          <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-6 border-b border-slate-100 pb-4">
            <h2 className="font-display text-xl font-bold text-slate-900">Learning Workflow</h2>
            <div className="flex flex-wrap gap-4">
              <div className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-slate-200"></span>
                <span className="font-sans text-xs text-slate-500">Locked</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-indigo-600"></span>
                <span className="font-sans text-xs text-slate-500">In Progress</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
                <span className="font-sans text-xs text-slate-500">Ready</span>
              </div>
            </div>
          </header>

          <div className="relative flex flex-col gap-6 pl-4">
            <div className="absolute left-[24px] top-6 bottom-6 w-0.5 node-line"></div>

            {nodes.map((node) => {
              const prefixStyles = {
                mastered: "bg-emerald-500 text-white ring-4 ring-emerald-50",
                "in-progress": "bg-indigo-600 text-white ring-4 ring-indigo-50 animate-pulse",
                locked: "bg-slate-200 text-slate-400 ring-4 ring-slate-100",
              };

              return (
                <div key={node.id} className="relative flex items-start gap-4">
                  <button
                    onClick={() => handleNodeClick(node.id)}
                    className={`z-10 w-10 h-10 rounded-full flex items-center justify-center border-2 border-white cursor-pointer hover:scale-105 active:scale-95 transition-all ${
                      prefixStyles[node.status]
                    }`}
                  >
                    <span className="material-symbols-outlined text-[18px]">
                      {node.status === "mastered" && "check_circle"}
                      {node.status === "in-progress" && "pending"}
                      {node.status === "locked" && "lock"}
                    </span>
                  </button>

                  <div className="flex-1 pt-1">
                    {node.status === "in-progress" ? (
                      <div
                        onClick={() => handleNodeClick(node.id)}
                        className="bg-indigo-50/40 p-5 rounded-2xl border border-indigo-100 transition-all cursor-pointer group hover:bg-indigo-50/70"
                      >
                        <div className="flex justify-between items-start gap-4 mb-1">
                          <div>
                            <h4 className="font-display text-base font-bold text-slate-900">{node.title}</h4>
                            <p className="font-sans text-xs text-slate-500 mt-0.5 font-medium">{node.details}</p>
                          </div>
                          <span className="font-display text-[10px] font-bold text-indigo-700 bg-indigo-100 px-2.5 py-1 rounded-full uppercase tracking-wider shrink-0">
                            In Progress
                          </span>
                        </div>

                        {showNodeStats && (
                          <div className="grid grid-cols-3 gap-2 mt-3 pt-3 border-t border-slate-150">
                            <div className="flex flex-col">
                              <span className="font-sans text-[9px] uppercase font-bold text-slate-400">Coverage</span>
                              <span className="font-display text-xs font-bold text-indigo-600">Source-led</span>
                            </div>
                            <div className="flex flex-col border-l border-slate-200 pl-2">
                              <span className="font-sans text-[9px] uppercase font-bold text-slate-400">Last Review</span>
                              <span className="font-display text-xs font-semibold text-slate-700">{node.lastReview}</span>
                            </div>
                            <div className="flex flex-col border-l border-slate-200 pl-2">
                              <span className="font-sans text-[9px] uppercase font-bold text-slate-400">Next Review</span>
                              <span className="font-display text-xs font-bold text-emerald-600">{node.nextReview}</span>
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className={node.status === "locked" ? "opacity-60" : ""}>
                        <div className="flex justify-between items-center gap-4">
                          <h4 className="font-display text-base font-semibold text-slate-800">{node.title}</h4>
                          <span
                            className={`font-display text-[10px] font-bold tracking-wider uppercase ${
                              node.status === "mastered" ? "text-emerald-600" : "text-slate-400"
                            }`}
                          >
                            {node.status === "mastered" ? "ready" : node.status}
                          </span>
                        </div>
                        <p className="font-sans text-xs text-slate-500 mt-0.5">{node.subtitle}</p>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section className="col-span-12 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <div className="bg-white border border-slate-200 p-6 rounded-3xl flex flex-col gap-3 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-indigo-50 flex items-center justify-center text-indigo-600">
              <span className="material-symbols-outlined text-[20px]">fact_check</span>
            </div>
            <h3 className="font-display text-sm font-bold text-slate-800">Source Check</h3>
          </div>
          <p className="font-sans text-xs text-slate-500 leading-relaxed font-semibold">
            Test whether answers are supported by retrieved chunks from the active upload. Unsupported answers should be treated as product bugs.
          </p>
        </div>

        <div className="bg-white border border-slate-200 p-6 rounded-3xl flex flex-col justify-between shadow-sm">
          <div>
            <h3 className="font-display text-sm font-bold text-slate-800 mb-3">Recommended Next Test</h3>
            <div className="p-4 bg-slate-50 rounded-2xl border border-slate-100 group cursor-pointer hover:border-indigo-500 hover:bg-indigo-50/20 transition-all">
              <p className="font-display font-bold text-sm text-slate-800 group-hover:text-indigo-600">Ask From Uploaded Material</p>
              <p className="font-sans text-xs text-slate-500 mt-1">Use a question whose answer is visible in the source preview or nearby pages.</p>
            </div>
          </div>
          <div className="mt-4 flex items-center justify-between">
            <span className="font-sans text-xs text-slate-400 font-semibold">Priority: High</span>
            <span className="material-symbols-outlined text-indigo-600 animate-bounce-horizontal">arrow_forward</span>
          </div>
        </div>

        <div className="bg-white border border-slate-100 p-6 rounded-3xl flex flex-col justify-between shadow-sm">
          <div>
            <h3 className="font-display text-sm font-bold text-slate-800 mb-3">Testing Metric</h3>
            <p className="font-sans text-xs text-slate-500 leading-relaxed">
              For this step, success means a tester can upload a source, ask an answerable question, see retrieved evidence, and reject unrelated questions cleanly.
            </p>
          </div>
          <div className="h-2 bg-gradient-to-r from-indigo-500 to-emerald-500 rounded-full w-full mt-4"></div>
        </div>
      </section>
    </div>
  );
}
