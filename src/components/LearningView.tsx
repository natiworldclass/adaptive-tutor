import React, { useEffect, useRef, useState } from "react";
import { Message, ReflectionLog } from "../types";

interface LearningViewProps {
  onAddReflection: (log: ReflectionLog) => void;
}

interface RetrievedSource {
  title: string;
  text: string;
  score: number;
}

interface SourceMetadata {
  file_name: string;
  chunk_count: number;
  preview_title?: string;
  preview_text?: string;
  detected_title?: string;
  subject?: string;
  chapters?: Array<{ chapter_number?: number; title?: string; pages?: number[]; concepts?: string[] }>;
  concept_count?: number;
}

interface QuickCheck {
  prompt: string;
  options: string[];
  correct_index?: number;
  explanation?: string;
}

interface ConceptGraph {
  detected_title?: string;
  subject?: string;
  chapters?: Array<{ chapter_number?: number; title?: string; pages?: number[]; concepts?: string[] }>;
  concepts?: Array<{
    id?: string;
    name: string;
    description?: string;
    source_refs?: Array<{ title?: string; page_number?: number; chapter_number?: number }>;
    prerequisites?: string[];
    next_concepts?: string[];
  }>;
}

interface SessionOutcome {
  completed: boolean;
  confidence_score: number;
  mastered_concept?: string;
  suggested_next_concept?: ConceptGraph["concepts"] extends Array<infer T> ? T : never;
  reason?: string;
}

const emptySource: RetrievedSource = {
  title: "No active source yet",
  score: 0,
  text: "Upload a PDF or TXT source, then ask a question. The tutor will retrieve the closest matching passages before answering.",
};

export default function LearningView({ onAddReflection }: LearningViewProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "m-1",
      sender: "tutor",
      text:
        "Upload a source or ask about the currently indexed source. I will retrieve matching passages, explain them in the selected mode, and show the evidence I used.",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    },
  ]);
  const [inputText, setInputText] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [responseLanguage, setResponseLanguage] = useState<"EN" | "FR" | "SW" | "HA" | "YO">("EN");
  const [adaptationMode, setAdaptationMode] = useState<"analogy" | "step-step" | "visual" | "peer">("step-step");
  const [hintLevel, setHintLevel] = useState(1);
  const [checkDifficulty, setCheckDifficulty] = useState<"diagnostic" | "easy" | "medium" | "hard">("diagnostic");
  const [activeMobileSubTab, setActiveMobileSubTab] = useState<"chat" | "source">("chat");
  const [activeSources, setActiveSources] = useState<RetrievedSource[]>([emptySource]);
  const [showAssessment, setShowAssessment] = useState(false);
  const [quickCheck, setQuickCheck] = useState<QuickCheck | null>(null);
  const [selectedQuickCheckIndex, setSelectedQuickCheckIndex] = useState<number | null>(null);
  const [activeQuestion, setActiveQuestion] = useState<string | null>(null);
  const [sourceMetadata, setSourceMetadata] = useState<SourceMetadata | null>(null);
  const [conceptGraph, setConceptGraph] = useState<ConceptGraph | null>(null);
  const [sessionOutcome, setSessionOutcome] = useState<SessionOutcome | null>(null);
  const [showReflectModal, setShowReflectModal] = useState(false);
  const [reflectionText, setReflectionText] = useState("");
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [micActive, setMicActive] = useState(false);
  const [uploadStatus, setUploadStatus] = useState("");
  const [isUploading, setIsUploading] = useState(false);

  const listEndRef = useRef<HTMLDivElement>(null);
  const activeRequestRef = useRef<AbortController | null>(null);
  const activeSource = activeSources[0] || emptySource;

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSending, showAssessment]);

  useEffect(() => {
    const loadCurrentSource = async () => {
      try {
        const response = await fetch("/api/sources/current");
        const data = await response.json();
        const source: SourceMetadata | null = data.source || null;
        const graph: ConceptGraph | null = data.concept_graph || null;
        setConceptGraph(graph);
        setSourceMetadata(source);
        if (source?.preview_text) {
          setActiveSources([
            {
              title: source.preview_title || source.file_name,
              text: source.preview_text,
              score: 0,
            },
          ]);
          setUploadStatus(`${source.file_name} active (${source.chunk_count} chunks).`);
        }
      } catch (error) {
        console.error("Failed to load current source:", error);
      }
    };

    loadCurrentSource();
  }, []);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  };

  const getHintExplanation = () => {
    switch (hintLevel) {
      case 1:
        return "Orienting";
      case 2:
        return "Narrowing";
      case 3:
        return "Similar Example";
      case 4:
        return "Full Reasoning";
      default:
        return "";
    }
  };

  const submitTutorTurn = async (
    visibleUserText: string,
    backendUserText = visibleUserText,
    historyExtras: Message[] = [],
  ) => {
    if (!visibleUserText.trim() || isSending || activeRequestRef.current) return;

    const controller = new AbortController();
    activeRequestRef.current = controller;
    setIsSending(true);
    setShowAssessment(false);
    setQuickCheck(null);
    setSelectedQuickCheckIndex(null);
    setSessionOutcome(null);

    const studentMessage: Message = {
      id: "std-" + Date.now(),
      sender: "student",
      text: visibleUserText,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, studentMessage]);
    const outgoingHistory = [...messages.slice(-8), ...historyExtras];

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          message: backendUserText,
          history: outgoingHistory,
          language: responseLanguage,
          mode: adaptationMode,
          current_hint_level: hintLevel,
          current_check_difficulty: checkDifficulty,
          auto_hint: true,
          active_question: activeQuestion,
        }),
      });

      const data = await response.json();
      const returnedSources: RetrievedSource[] = Array.isArray(data.sources) ? data.sources : [];
      const candidateSources: RetrievedSource[] = Array.isArray(data.candidate_sources) ? data.candidate_sources : [];
      const groundingStatus = typeof data.grounding_status === "string" ? data.grounding_status : "unknown";
      const effectiveHintLevel = typeof data.effective_hint_level === "number" ? data.effective_hint_level : hintLevel;
      const returnedQuickCheck = data.quick_check;
      const returnedSessionOutcome = data.session_outcome;
      const returnedCheckDifficulty = typeof data.check_difficulty === "string" ? data.check_difficulty : checkDifficulty;
      const returnedActiveQuestion = typeof data.active_question === "string" ? data.active_question : activeQuestion;
      setActiveQuestion(returnedActiveQuestion);
      setHintLevel(Math.min(4, Math.max(1, effectiveHintLevel)));
      if (["diagnostic", "easy", "medium", "hard"].includes(returnedCheckDifficulty)) {
        setCheckDifficulty(returnedCheckDifficulty as typeof checkDifficulty);
      }
      if (returnedSources.length) {
        setActiveSources(returnedSources);
      } else if (candidateSources.length) {
        setActiveSources(candidateSources);
      }

      const sourceNote = returnedSources.length
        ? "\n\nSources used: " + returnedSources.map((source) => source.title).join(", ")
        : groundingStatus === "insufficient_context"
        ? ""
        : "\n\nNo strong source match was found in the current indexed file.";

      setMessages((prev) => [
        ...prev,
        {
          id: "tut-" + Date.now(),
          sender: "tutor",
          text: `${data.text || "No response text returned."}${sourceNote}`,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
      if (
        returnedQuickCheck &&
        typeof returnedQuickCheck.prompt === "string" &&
        Array.isArray(returnedQuickCheck.options) &&
        returnedQuickCheck.options.length >= 2
      ) {
        setQuickCheck({
          prompt: returnedQuickCheck.prompt,
          options: returnedQuickCheck.options.slice(0, 4),
          correct_index:
            typeof returnedQuickCheck.correct_index === "number"
              ? returnedQuickCheck.correct_index
              : undefined,
          explanation:
            typeof returnedQuickCheck.explanation === "string"
              ? returnedQuickCheck.explanation
              : undefined,
        });
        setShowAssessment(false);
      } else {
        setShowAssessment(effectiveHintLevel >= 4 || groundingStatus === "insufficient_context");
      }
      if (returnedSessionOutcome?.completed) {
        setSessionOutcome(returnedSessionOutcome);
        setShowAssessment(false);
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        setMessages((prev) => [
          ...prev,
          {
            id: "tut-cancelled-" + Date.now(),
            sender: "tutor",
            text: "Stopped. You can send a new question when ready.",
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          },
        ]);
        return;
      }
      console.error("Failed to query tutor API:", error);
      setMessages((prev) => [
        ...prev,
        {
          id: "tut-fallback-" + Date.now(),
          sender: "tutor",
          text: "I could not reach the tutor backend. Check that FastAPI is running on port 8000, then try again.",
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } finally {
      activeRequestRef.current = null;
      setIsSending(false);
    }
  };

  const handleStopResponse = () => {
    activeRequestRef.current?.abort();
    activeRequestRef.current = null;
    setIsSending(false);
    showToast("Response stopped.");
  };

  const handleSend = async () => {
    if (!inputText.trim() || isSending) return;
    const userText = inputText.trim();
    setInputText("");
    await submitTutorTurn(userText);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const toggleMic = () => {
    if (micActive) {
      setMicActive(false);
      return;
    }

    setMicActive(true);
    setTimeout(() => {
      setInputText("Explain the main idea from the current source in simple steps.");
      setMicActive(false);
    }, 1000);
  };

  const handleSourceUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || isUploading) return;

    setIsUploading(true);
    setUploadStatus(`Uploading ${file.name}...`);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch("/api/sources/upload", {
        method: "POST",
        body: formData,
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Upload failed.");
      }

      setUploadStatus(`${data.source.file_name} active (${data.source.chunk_count} chunks).`);
      setSourceMetadata(data.source);
      setConceptGraph(data.concept_graph || null);
      setActiveSources([
        {
          title: data.source.preview_title || data.source.file_name,
          text: data.source.preview_text || "New source uploaded and indexed. Ask a question to retrieve the most relevant passage.",
          score: 0,
        },
      ]);
      setMessages([
        {
          id: "m-upload-" + Date.now(),
          sender: "tutor",
          text: `${data.source.file_name} is now the active source. Ask a question from that material and I will ground the answer in it.`,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
      setHintLevel(1);
      setCheckDifficulty("diagnostic");
      setActiveQuestion(null);
      setQuickCheck(null);
      setSelectedQuickCheckIndex(null);
      setShowAssessment(false);
      setSessionOutcome(null);
      showToast("Source uploaded and indexed successfully.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Upload failed.";
      setUploadStatus(message);
      showToast(message);
    } finally {
      setIsUploading(false);
      event.target.value = "";
    }
  };

  const handleSelectQuickCheck = async (index: number) => {
    if (!quickCheck || isSending || selectedQuickCheckIndex !== null) return;

    setSelectedQuickCheckIndex(index);
    const selectedOption = quickCheck.options[index];
    const isDiagnostic = quickCheck.correct_index === undefined;
    const isCorrect = isDiagnostic || quickCheck.correct_index === index;
    onAddReflection({
      id: "ref-" + Date.now(),
      title: "Quick Understanding Check",
      category: activeSource.title,
      type: isDiagnostic || isCorrect ? "realization" : "reasoning",
      content: `Prompt: ${quickCheck.prompt}\nSelected: ${selectedOption}\nFeedback: ${quickCheck.explanation || "No extra feedback provided."}`,
      timestamp: "Just now in Chat",
      rating: isDiagnostic ? 4 : isCorrect ? 5 : 3,
    });

    const quickCheckHistory: Message = {
      id: "qc-" + Date.now(),
      sender: "tutor",
      text: `Quick check: ${quickCheck.prompt}\nOptions: ${quickCheck.options.join(" | ")}`,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
    const visibleAnswer = `I choose: ${selectedOption}`;
    const backendAnswer = isDiagnostic
      ? `Quick check response. Question: ${quickCheck.prompt}\nSelected answer: ${selectedOption}\nDiagnostic: true`
      : `Quick check response. Question: ${quickCheck.prompt}\nSelected answer: ${selectedOption}\nCorrect: ${isCorrect}`;

    showToast(isDiagnostic ? "Starting point saved." : isCorrect ? "Check submitted and saved." : "Check submitted and saved. The tutor will respond to it.");
    await submitTutorTurn(visibleAnswer, backendAnswer, [quickCheckHistory]);
  };

  const handleSaveReflection = () => {
    if (!reflectionText.trim()) {
      showToast("Write one short reflection first.");
      return;
    }

    onAddReflection({
      id: "ref-" + Date.now(),
      title: "Source-Grounded Understanding Check",
      category: activeSource.title,
      type: "journal",
      content: reflectionText.trim(),
      timestamp: "Just now in Chat",
      rating: 4,
    });

    setReflectionText("");
    setShowReflectModal(false);
    setShowAssessment(false);
    showToast("Reflection saved to your learning journal.");
  };

  return (
    <div className="flex-grow flex flex-col md:flex-row bg-slate-50 h-[calc(100vh-8rem)] lg:h-[calc(100vh-4rem)] overflow-hidden relative">
      {toastMessage && (
        <div className="fixed top-6 right-6 z-50 bg-slate-900 text-white rounded-xl px-5 py-3 shadow-xl flex items-center gap-3 border border-slate-800">
          <span className="material-symbols-outlined text-indigo-300">info</span>
          <span className="text-xs font-semibold">{toastMessage}</span>
        </div>
      )}

      <div className="md:hidden flex border-b border-slate-200 bg-white shadow-xs shrink-0 select-none">
        <button
          onClick={() => setActiveMobileSubTab("chat")}
          className={`flex-1 py-3 text-center font-display text-xs font-bold transition-all border-b-2 flex items-center justify-center gap-1.5 ${
            activeMobileSubTab === "chat" ? "border-indigo-600 text-indigo-600" : "border-transparent text-slate-500"
          }`}
        >
          <span className="material-symbols-outlined text-[18px]">forum</span>
          <span>Tutor Chat</span>
        </button>
        <button
          onClick={() => setActiveMobileSubTab("source")}
          className={`flex-1 py-3 text-center font-display text-xs font-bold transition-all border-b-2 flex items-center justify-center gap-1.5 ${
            activeMobileSubTab === "source" ? "border-indigo-600 text-indigo-600" : "border-transparent text-slate-500"
          }`}
        >
          <span className="material-symbols-outlined text-[18px]">menu_book</span>
          <span>Source</span>
        </button>
      </div>

      <section
        className={`flex-grow flex-col h-full border-r border-slate-200 bg-white relative ${
          activeMobileSubTab === "chat" ? "flex" : "hidden md:flex"
        }`}
      >
        <div className="absolute top-4 right-4 z-10 hidden sm:block">
          <div
            className="bg-indigo-50 border border-indigo-100 rounded-full px-4 py-1.5 flex items-center gap-3 shadow-sm"
            title="Tutor-controlled hint level"
          >
            <span className="font-display text-xs font-bold text-indigo-700">Hint Level {hintLevel}/4</span>
            <div className="flex gap-0.5">
              {[1, 2, 3, 4].map((num) => (
                <div
                  key={num}
                  className={`w-3.5 h-1.5 rounded-full transition-all ${
                    num <= hintLevel ? "bg-indigo-600" : "bg-slate-200"
                  }`}
                />
              ))}
            </div>
            <span className="font-sans text-[11px] text-slate-500 italic font-semibold">{getHintExplanation()}</span>
            <span className="font-mono text-[10px] text-slate-400 uppercase">{checkDifficulty}</span>
          </div>
        </div>

        <div className="flex-grow overflow-y-auto p-6 pb-28 space-y-6 hide-scrollbar">
          {messages.map((msg) => {
            const isTutor = msg.sender === "tutor";
            return (
              <div
                key={msg.id}
                className={`flex flex-col gap-1 max-w-[85%] sm:max-w-[75%] ${
                  isTutor ? "mr-auto" : "ml-auto items-end"
                }`}
              >
                <div className={`flex items-center gap-1.5 text-xs font-extrabold ${isTutor ? "text-indigo-600" : "text-slate-500"}`}>
                  <span className="material-symbols-outlined text-[16px]">{isTutor ? "smart_toy" : "person"}</span>
                  <span className="font-display uppercase tracking-wider">{isTutor ? "Adaptive Tutor" : "Student"}</span>
                  <span className="text-[10px] text-slate-300 font-normal font-sans">{msg.timestamp}</span>
                </div>

                <div
                  className={`p-4 rounded-xl shadow-sm border ${
                    isTutor
                      ? "bg-slate-50 border-slate-200 rounded-tl-none text-slate-800"
                      : "bg-indigo-600 text-white border-transparent rounded-tr-none"
                  }`}
                >
                  <p className="font-sans leading-relaxed text-sm whitespace-pre-wrap">{msg.text}</p>
                </div>
              </div>
            );
          })}

          {isSending && (
            <div className="flex flex-col gap-1 max-w-[70%] mr-auto">
              <div className="flex items-center gap-1.5 text-xs text-indigo-600 font-extrabold">
                <span className="material-symbols-outlined text-[16px] animate-spin">sync</span>
                <span className="font-display">Retrieving source context...</span>
              </div>
              <div className="bg-slate-50 border border-slate-200 p-4 rounded-xl rounded-tl-none text-slate-800">
                <div className="flex gap-1.5">
                  <div className="w-2.5 h-2.5 bg-indigo-600 rounded-full animate-bounce"></div>
                  <div className="w-2.5 h-2.5 bg-indigo-600 rounded-full animate-bounce [animation-delay:0.2s]"></div>
                  <div className="w-2.5 h-2.5 bg-indigo-600 rounded-full animate-bounce [animation-delay:0.4s]"></div>
                </div>
              </div>
            </div>
          )}

          {quickCheck && (
            <div className="border border-indigo-100 rounded-2xl p-5 bg-white max-w-2xl mx-auto my-6 shadow-sm">
              <div className="flex items-center gap-2 mb-3">
                <span className="material-symbols-outlined text-indigo-600 text-lg">quiz</span>
                <h4 className="font-display text-xs font-bold uppercase tracking-wider text-indigo-800">
                  Quick Check
                </h4>
              </div>
              <p className="font-display text-sm font-bold text-slate-800 mb-4 leading-normal">
                {quickCheck.prompt}
              </p>
              <div className="space-y-2.5">
                {quickCheck.options.map((option, index) => {
                  const isSelected = selectedQuickCheckIndex === index;
                  const isCorrect = quickCheck.correct_index === index;
                  const showFeedback = selectedQuickCheckIndex !== null;
                  return (
                    <button
                      key={`${option}-${index}`}
                      disabled={selectedQuickCheckIndex !== null}
                      onClick={() => handleSelectQuickCheck(index)}
                      className={`w-full text-left p-3.5 rounded-xl border text-xs leading-relaxed transition-all flex items-start gap-3 ${
                        showFeedback && isSelected
                          ? isCorrect || quickCheck.correct_index === undefined
                            ? "bg-emerald-50 border-emerald-400 text-emerald-900"
                            : "bg-rose-50 border-rose-400 text-rose-900"
                          : "bg-slate-50 border-slate-200 hover:bg-white text-slate-700"
                      }`}
                    >
                      <span className="w-5 h-5 rounded-full flex items-center justify-center shrink-0 font-display text-[11px] font-black border bg-white text-slate-500 border-slate-200">
                        {String.fromCharCode(65 + index)}
                      </span>
                      <span className="font-medium">{option}</span>
                    </button>
                  );
                })}
              </div>
              {selectedQuickCheckIndex !== null && (
                <div className="mt-4 p-3 bg-slate-50 border border-slate-100 rounded-xl text-[11px] leading-relaxed">
                  {quickCheck.explanation && (
                    <p className="font-sans text-slate-600">
                      <span className="font-bold text-slate-800">Feedback: </span>
                      {quickCheck.explanation}
                    </p>
                  )}
                  <p className="mt-2 font-sans text-slate-500">
                    Your answer is being sent to the tutor and saved to reflections.
                  </p>
                </div>
              )}
            </div>
          )}

          {sessionOutcome?.completed && (
            <div className="border border-emerald-200 rounded-2xl p-5 bg-emerald-50 max-w-2xl mx-auto my-6 shadow-sm">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-xl bg-white text-emerald-600 flex items-center justify-center shrink-0 border border-emerald-100">
                  <span className="material-symbols-outlined">verified</span>
                </div>
                <div className="min-w-0 flex-1">
                  <h4 className="font-display text-xs font-bold uppercase tracking-wider text-emerald-800">
                    Concept Added to Learning Map
                  </h4>
                  <p className="font-sans text-sm text-slate-800 mt-2 leading-relaxed">
                    You showed enough understanding for this concept. Confidence:{" "}
                    <span className="font-bold">{Math.round(sessionOutcome.confidence_score * 100)}%</span>
                  </p>
                  {sessionOutcome.suggested_next_concept?.name && (
                    <div className="mt-4 p-3 rounded-xl bg-white border border-emerald-100">
                      <p className="font-display text-[11px] font-bold uppercase tracking-wider text-slate-500">
                        Source-Grounded Next Concept
                      </p>
                      <p className="font-display text-sm font-bold text-slate-900 mt-1">
                        {sessionOutcome.suggested_next_concept.name}
                      </p>
                      {sessionOutcome.suggested_next_concept.description && (
                        <p className="font-sans text-xs text-slate-600 mt-1 leading-relaxed">
                          {sessionOutcome.suggested_next_concept.description}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {showAssessment && (
            <div className="border border-slate-200 rounded-2xl p-5 bg-indigo-50/20 max-w-2xl mx-auto my-6 shadow-sm">
              <div className="flex items-center gap-2 mb-3">
                <span className="material-symbols-outlined text-indigo-600 text-lg">psychology_alt</span>
                <h4 className="font-display text-xs font-bold uppercase tracking-wider text-indigo-800">
                  Quick Understanding Check
                </h4>
              </div>
              <p className="font-display text-sm font-bold text-slate-800 mb-2 leading-normal">
                In one sentence, explain what you understood from the answer.
              </p>
              <p className="font-sans text-xs text-slate-500 leading-relaxed">
                Then compare your sentence with the source panel on the right. If the answer is not supported by that source, flag it during testing.
              </p>
              <button
                onClick={() => setShowReflectModal(true)}
                className="mt-4 px-4 py-2 bg-indigo-600 text-white rounded-lg font-display text-xs font-bold hover:bg-indigo-700 active:scale-95 transition-all cursor-pointer"
              >
                Add Reflection
              </button>
            </div>
          )}

          <div ref={listEndRef}></div>
        </div>

        <div className="absolute bottom-0 left-0 right-0 bg-white border-t border-slate-200 p-4">
          <div className="relative">
            <textarea
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              className="w-full bg-slate-50 border border-slate-200 rounded-xl py-3 pl-4 pr-16 text-sm font-sans focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none resize-none hide-scrollbar text-slate-800"
              placeholder="Ask a question from the active source..."
            />
            <button
              disabled={!inputText.trim() && !isSending}
              onClick={isSending ? handleStopResponse : handleSend}
              className={`absolute bottom-3 right-3 w-10 h-10 text-white rounded-lg flex items-center justify-center active:scale-95 transition-all cursor-pointer ${
                isSending
                  ? "bg-rose-600 hover:bg-rose-700"
                  : "bg-indigo-600 disabled:bg-slate-300 hover:bg-indigo-700"
              }`}
              title={isSending ? "Stop response" : "Send message"}
            >
              <span className="material-symbols-outlined">{isSending ? "stop" : "send"}</span>
            </button>
          </div>

          <div className="flex flex-col sm:flex-row justify-between gap-3 mt-3 text-xs">
            <div className="flex items-center gap-2">
              <span className="font-display font-semibold text-slate-500">Response Language:</span>
              <div className="flex bg-slate-100 border border-slate-200 rounded-lg p-0.5">
                {(["EN", "FR", "SW", "HA", "YO"] as const).map((lang) => (
                  <button
                    key={lang}
                    onClick={() => setResponseLanguage(lang)}
                    className={`px-2.5 py-1 rounded-md text-xs transition-all cursor-pointer font-bold ${
                      responseLanguage === lang ? "bg-white text-indigo-600 shadow-sm" : "text-slate-500 hover:text-indigo-600"
                    }`}
                  >
                    {lang}
                  </button>
                ))}
              </div>
            </div>

            <button
              onClick={toggleMic}
              className={`flex items-center gap-1.5 text-sm font-display font-semibold transition-all cursor-pointer hover:text-indigo-600 ${
                micActive ? "text-rose-600 animate-pulse" : "text-slate-500"
              }`}
            >
              <span className="material-symbols-outlined text-[18px]">{micActive ? "mic" : "mic_none"}</span>
              <span>{micActive ? "Listening..." : "Voice Input"}</span>
            </button>
          </div>
        </div>
      </section>

      <section
        className={`w-full md:w-[380px] lg:w-[410px] bg-slate-50 flex-col border-l border-slate-200 h-full overflow-hidden shrink-0 ${
          activeMobileSubTab === "source" ? "flex" : "hidden md:flex"
        }`}
      >
        <div className="p-4 border-b border-slate-200 bg-white">
          <h3 className="font-display text-xs font-bold text-slate-500 mb-3 uppercase tracking-wider">Adaptation Modes</h3>
          <div className="grid grid-cols-2 gap-2">
            {[
              { id: "analogy", title: "Explain with an Analogy", icon: "compare_arrows" },
              { id: "step-step", title: "Step-by-Step Logic", icon: "format_list_numbered" },
              { id: "visual", title: "Visual Description", icon: "image" },
              { id: "peer", title: "Peer Mode", icon: "groups" },
            ].map((mode) => {
              const active = adaptationMode === mode.id;
              return (
                <button
                  key={mode.id}
                  onClick={() => setAdaptationMode(mode.id as typeof adaptationMode)}
                  className={`flex flex-col items-center justify-center p-3 sm:p-4 rounded-xl transition-all cursor-pointer border ${
                    active ? "bg-indigo-50 border-2 border-indigo-500 shadow-sm" : "bg-slate-50 hover:bg-slate-100 border-slate-200"
                  }`}
                >
                  <span className={`material-symbols-outlined mb-1.5 text-lg ${active ? "text-indigo-600" : "text-slate-500"}`}>
                    {mode.icon}
                  </span>
                  <span className={`text-[11px] leading-tight text-center ${active ? "font-bold text-indigo-600" : "text-slate-500"}`}>
                    {mode.title}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex-grow flex flex-col overflow-hidden">
          <div className="px-4 py-3 bg-slate-900 flex justify-between items-center text-white">
            <span className="font-display text-xs font-bold uppercase tracking-wider truncate">Source: {activeSource.title}</span>
            {activeSource.score > 0 && (
              <span className="font-mono text-[10px] text-slate-300 shrink-0">Match {(activeSource.score * 100).toFixed(0)}%</span>
            )}
          </div>

          <div className="flex-grow overflow-y-auto p-4 space-y-4 hide-scrollbar">
            <div className="bg-white p-4 border border-slate-200 rounded-xl shadow-sm">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                  <span className="material-symbols-outlined">upload_file</span>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-display text-sm font-bold text-slate-900">Upload Source</p>
                  <p className="font-sans text-[11px] text-slate-500 mt-1">
                    PDF and TXT are supported. Scanned image-only PDFs will need OCR later.
                  </p>
                  <label className="mt-3 inline-flex items-center gap-2 px-3 py-2 bg-indigo-600 text-white rounded-lg font-display text-xs font-bold hover:bg-indigo-700 active:scale-95 transition-all cursor-pointer">
                    <span className="material-symbols-outlined text-[16px]">add</span>
                    <span>{isUploading ? "Indexing..." : "Choose File"}</span>
                    <input
                      type="file"
                      accept=".pdf,.txt,application/pdf,text/plain"
                      className="hidden"
                      disabled={isUploading}
                      onChange={handleSourceUpload}
                    />
                  </label>
                  {uploadStatus && <p className="font-sans text-[11px] text-slate-500 mt-2 break-words">{uploadStatus}</p>}
                </div>
              </div>
            </div>

            <div className="bg-white p-4 border border-slate-200 rounded-xl shadow-sm">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0">
                  <span className="material-symbols-outlined">article</span>
                </div>
                <div className="min-w-0">
                  <p className="font-display text-sm font-bold text-slate-900 break-words">
                    {sourceMetadata?.detected_title || conceptGraph?.detected_title || activeSource.title}
                  </p>
                  <p className="font-sans text-[11px] text-slate-500 mt-1">
                    {sourceMetadata?.subject || conceptGraph?.subject || "Current source preview or retrieved matching chunk."}
                  </p>
                  {(sourceMetadata?.concept_count || conceptGraph?.concepts?.length) && (
                    <p className="font-mono text-[10px] text-slate-400 mt-1">
                      {sourceMetadata?.concept_count || conceptGraph?.concepts?.length} source concepts detected
                    </p>
                  )}
                </div>
              </div>
            </div>

            {conceptGraph?.concepts?.length ? (
              <div className="bg-white border border-slate-200 rounded-xl p-4">
                <h4 className="font-display text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">
                  Source Learning Map
                </h4>
                <div className="space-y-2">
                  {conceptGraph.concepts.slice(0, 5).map((concept) => (
                    <div key={concept.id || concept.name} className="p-3 rounded-lg bg-slate-50 border border-slate-100">
                      <p className="font-display text-xs font-bold text-slate-800">{concept.name}</p>
                      {concept.source_refs?.[0] && (
                        <p className="font-mono text-[10px] text-slate-400 mt-1">
                          {concept.source_refs[0].page_number ? `Page ${concept.source_refs[0].page_number}` : "Source linked"}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="space-y-3 font-sans text-xs text-slate-700 leading-relaxed">
              <p className="whitespace-pre-wrap">{activeSource.text}</p>
            </div>

            {activeSources.length > 1 && (
              <div className="bg-white border border-slate-200 rounded-xl p-4">
                <h4 className="font-display text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">
                  Other Retrieved Chunks
                </h4>
                <div className="space-y-2">
                  {activeSources.slice(1).map((source) => (
                    <button
                      key={`${source.title}-${source.score}`}
                      onClick={() => setActiveSources([source, ...activeSources.filter((item) => item !== source)])}
                      className="w-full text-left p-3 rounded-lg border border-slate-100 hover:border-indigo-300 bg-slate-50 transition-all"
                    >
                      <p className="font-display text-xs font-bold text-slate-800">{source.title}</p>
                      <p className="font-mono text-[10px] text-slate-400 mt-0.5">Match {(source.score * 100).toFixed(0)}%</p>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="p-4 bg-indigo-50 border-t border-indigo-100 text-indigo-800">
          <div className="flex items-start gap-2.5">
            <span className="material-symbols-outlined text-indigo-600 shrink-0 mt-0.5">lightbulb</span>
            <p className="font-display font-semibold text-xs leading-normal">
              Test rule: the answer should follow the retrieved source. If the source is unrelated, the tutor should say it cannot answer from that upload.
            </p>
          </div>
        </div>
      </section>

      {showReflectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-md">
          <div className="w-full max-w-xl bg-white border border-slate-100 shadow-2xl rounded-2xl overflow-hidden">
            <header className="p-5 border-b border-slate-100 flex items-center justify-between bg-slate-50">
              <div>
                <p className="text-[10px] font-display font-bold text-slate-400 uppercase tracking-wider">Active Self-Evaluation</p>
                <h3 className="font-display text-sm font-extrabold text-slate-900 uppercase tracking-wide">Reflection Note</h3>
              </div>
              <button
                onClick={() => setShowReflectModal(false)}
                className="w-8 h-8 rounded-full border border-slate-200 bg-white text-slate-400 hover:text-slate-600 active:scale-90 flex items-center justify-center transition-all cursor-pointer"
              >
                <span className="material-symbols-outlined text-base">close</span>
              </button>
            </header>

            <div className="p-6 space-y-4">
              <p className="font-display text-sm font-bold text-slate-800">What did you understand from the source-backed answer?</p>
              <textarea
                rows={5}
                value={reflectionText}
                onChange={(e) => setReflectionText(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs font-sans focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none resize-none text-slate-800 leading-relaxed"
                placeholder="Write the idea in your own words and note whether the answer matched the source."
              />
            </div>

            <footer className="p-4 bg-slate-50 border-t border-slate-100 flex justify-end gap-2">
              <button
                onClick={() => setShowReflectModal(false)}
                className="px-4 py-2 border border-slate-200 bg-white rounded-lg font-display text-xs font-semibold hover:bg-slate-50 active:scale-95 transition-all cursor-pointer text-slate-700"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveReflection}
                className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-display text-xs font-bold active:scale-95 transition-all cursor-pointer"
              >
                Save Reflection
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}
