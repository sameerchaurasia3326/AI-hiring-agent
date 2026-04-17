import { useEffect, useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { api } from '../services/api';
import {
  UserCheck, CheckCircle2, AlertCircle, User,
  Star, MessageSquare, Video, FileText,
  Calendar as CalendarIcon, Inbox, Loader2,
  Layers, Target, Zap, Award, ExternalLink,
  Clock, ShieldCheck
} from 'lucide-react';

interface InterviewerCandidate {
  application_id: string;
  candidate_id: string;
  candidate_name: string;
  job_title: string;
  stage: string;
  score: number;
  resume_url: string | null;
  skills: string[] | null;
  ai_summary: string | null;
}

interface UpcomingInterview {
  interview_id: string;
  candidate_name: string;
  job_title: string;
  scheduled_time: string;
  meeting_link: string | null;
  status: string;
}



const getStageColor = (stage: string) => {
  const s = stage?.toLowerCase() || '';
  if (s.includes('shortlist') || s.includes('screening') || s.includes('evaluation')) return 'text-blue-500 bg-blue-500/10 border-blue-500/20';
  if (s.includes('interview')) return 'text-orange-500 bg-orange-500/10 border-orange-500/20';
  if (s.includes('complete') || s.includes('hire') || s.includes('offer')) return 'text-green-500 bg-green-500/10 border-green-500/20';
  if (s.includes('reject') || s.includes('no')) return 'text-red-500 bg-red-500/10 border-red-500/20';
  return 'text-slate-500 bg-slate-500/10 border-slate-500/20';
};

export default function MyTasks() {
  const [candidates, setCandidates] = useState<InterviewerCandidate[]>([]);
  const [interviews, setInterviews] = useState<UpcomingInterview[]>([]);
  const [loading, setLoading] = useState(true);
  const [isWsConnected, setIsWsConnected] = useState(false);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Selection & Form State
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [rating, setRating] = useState<number>(0);
  const [feedbackText, setFeedbackText] = useState<string>('');

  const fetchData = async () => {
    try {
      const [candData, intData] = await Promise.all([
        api.getInterviewerCandidates(),
        api.getInterviewerInterviews()
      ]);
      setCandidates(candData || []);
      setInterviews(intData || []);
    } catch (err) {
      setError('Connection Sync Failed. Check API status.');
    } finally {
      setLoading(false);
    }
  };

  // Debounced Refresh Trigger (Prevent API Flooding)
  const refreshTimer = useRef<any>(null);
  const debouncedFetch = () => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    refreshTimer.current = setTimeout(() => {
      console.info("⚡ [SYNC] Executing debounced data refresh...");
      fetchData();
    }, 300); // 300ms debounce
  };

  // Real-Time WebSocket Sync (ZERO-ERROR SILENT CONNECT)
  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: any = null;

    const connect = () => {
      // Small delay prevents handshake race condition in React Strict Mode Dev
      timer = setTimeout(() => {
        if (ws) return; 

        ws = new WebSocket("ws://127.0.0.1:8000/api/events");

        ws.onopen = () => {
          console.log("✅ WS Connected");
          setIsWsConnected(true);
        };

        ws.onmessage = (e) => {
          console.log("📩", e.data);
          if (e.data === 'REFRESH_TASKS' || e.data === 'REFRESH_INTERVIEWS') {
            fetchData();
          }
        };

        ws.onerror = () => {
          // Silent failure during initial handshake check
          setIsWsConnected(false);
        };

        ws.onclose = () => {
          setIsWsConnected(false);
        };
      }, 50); // 50ms is enough to skip the StrictMode cleanup race
    };

    connect();

    return () => {
      if (timer) clearTimeout(timer);
      if (ws) {
        // Only close if it was actually opened to avoid "Closed before established" console error
        if (ws.readyState === WebSocket.OPEN) {
          ws.close();
        }
        ws = null;
      }
    };
  }, []);

  // Auto-Sync (Initial Load + Fallback Polling)
  useEffect(() => {
    fetchData();

    // Only poll if WebSocket is not connected (Fallback Mode)
    const interval = setInterval(() => {
      if (!isWsConnected) {
        console.info("🔄 [POLLING] WebSocket down. Running fallback sync...");
        fetchData();
      }
    }, 30000);

    return () => clearInterval(interval);
  }, [isWsConnected]);

  // Auto-select first candidate & State Cleanup
  useEffect(() => {
    if (candidates.length > 0 && !selectedCandidateId) {
      setSelectedCandidateId(candidates[0].application_id);
    }

    // Auto-clear feedback after 5s
    if (successMsg || error) {
      const timer = setTimeout(() => {
        setSuccessMsg(null);
        setError(null);
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [candidates, selectedCandidateId, successMsg, error]);

  const selectedCandidate = candidates.find(c => c.application_id === selectedCandidateId);
  // Find associated interview if any
  const associatedInterview = interviews.find(i => i.candidate_name === selectedCandidate?.candidate_name);

  const resetForm = () => {
    setRating(0);
    setFeedbackText('');
  };

  const handleSubmitAction = async (decision: string) => {
    if (!selectedCandidate) return;
    if (rating === 0 || !feedbackText) {
      setError('Rating and notes are required.');
      return;
    }

    setProcessingId(selectedCandidate.application_id);
    setError(null);

    // 🔥 OPTIMISTIC UI: Remove and Select Next INSTANTLY for Zero-Click Advance
    const currentIndex = candidates.findIndex(c => c.application_id === selectedCandidate.application_id);
    const nextCandidates = candidates.filter(c => c.application_id !== selectedCandidate.application_id);

    const nextTargetId = nextCandidates.length > 0
      ? (nextCandidates[currentIndex]?.application_id || nextCandidates[nextCandidates.length - 1].application_id)
      : null;

    const previousCandidates = [...candidates];
    const previousSelectedId = selectedCandidateId;
    const previousRating = rating;
    const previousFeedback = feedbackText;

    setCandidates(nextCandidates);
    setSelectedCandidateId(nextTargetId);
    resetForm();

    try {
      const isInterviewPhase = selectedCandidate.stage === 'interview';
      const targetIntId = associatedInterview?.interview_id;
      const targetAppId = selectedCandidate.application_id;

      if (isInterviewPhase && targetIntId) {
        await api.submitInterviewFeedback(targetIntId, {
          rating: previousRating,
          notes: previousFeedback,
          decision
        });
      } else {
        await api.submitEvaluation(targetAppId, {
          rating: previousRating,
          notes: previousFeedback,
          decision: decision.includes('hire') ? 'select' : 'reject'
        });
      }

      setSuccessMsg("Candidate processed successfully ✅");
      fetchData(); // Sync with backend state
    } catch (err: any) {
      console.error("❌ [API] Evaluation failed. Restoring UI state...");
      setCandidates(previousCandidates);
      setSelectedCandidateId(previousSelectedId);
      setRating(previousRating);
      setFeedbackText(previousFeedback);
      setError("Something went wrong ❌");
      fetchData();
    } finally {
      setProcessingId(null);
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' });
  };

  if (loading) return (
    <div className="h-screen bg-slate-900 flex items-center justify-center">
      <Loader2 className="w-12 h-12 text-blue-500 animate-spin" />
    </div>
  );

  return (
    <div className="h-screen bg-[#0F172A] text-slate-200 flex overflow-hidden font-sans">
      <AnimatePresence>
        {successMsg && (
          <motion.div
            initial={{ opacity: 0, y: 50, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className="fixed bottom-10 left-1/2 -translate-x-1/2 bg-blue-600 px-8 py-5 rounded-[2.5rem] shadow-2xl z-50 flex items-center gap-4 border border-blue-400/30"
          >
            <ShieldCheck className="w-8 h-8 text-white" />
            <p className="text-sm font-black text-white uppercase tracking-widest">{successMsg}</p>
          </motion.div>
        )}

        {error && (
          <motion.div
            initial={{ opacity: 0, y: 50, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className="fixed bottom-10 left-1/2 -translate-x-1/2 bg-red-600 px-8 py-5 rounded-[2.5rem] shadow-2xl z-50 flex items-center gap-4 border border-red-400/30"
          >
            <AlertCircle className="w-8 h-8 text-white" />
            <p className="text-sm font-black text-white uppercase tracking-widest">{error}</p>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="w-[380px] border-r border-slate-800/50 flex flex-col bg-slate-900/40 backdrop-blur-xl shrink-0">
        <div className="p-8">
          <div className="flex items-center gap-3 mb-10">
            <div className="w-10 h-10 bg-blue-600 rounded-2xl flex items-center justify-center shadow-lg shadow-blue-500/20">
              <Zap className="w-6 h-6 text-white" />
            </div>
            <h1 className="text-xl font-black tracking-tighter">Tasks <span className="text-blue-500">.</span></h1>
          </div>

          <div className="flex items-center justify-between mb-4">
            <h3 className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] flex items-center gap-2">
              <Layers className="w-3 h-3" /> Assigned Bench
            </h3>
            <span className="text-[10px] font-bold bg-slate-800 px-2 py-0.5 rounded-full text-slate-400">{candidates.length}</span>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 pb-10 space-y-3 no-scrollbar">
          {candidates.length === 0 ? (
            <div className="py-20 text-center flex flex-col items-center">
              <div className="w-16 h-16 bg-slate-800/50 rounded-[2rem] flex items-center justify-center mb-6 border border-white/5">
                <Inbox className="w-8 h-8 text-blue-500" />
              </div>
              <p className="text-sm font-black text-white">You're all caught up 🎉</p>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mt-2">No candidates assigned</p>
            </div>
          ) : (
            <div className="space-y-4">
              <AnimatePresence mode="popLayout" initial={false}>
                {candidates.map(cand => (
                  <motion.div
                    key={cand.application_id}
                    layout
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -50, filter: 'blur(10px)' }}
                    transition={{
                      layout: { type: 'spring', damping: 20, stiffness: 300 },
                      opacity: { duration: 0.2 }
                    }}
                    whileHover={{ scale: 1.02, x: 5 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => setSelectedCandidateId(cand.application_id)}
                    className={`p-6 rounded-[2rem] cursor-pointer transition-all border-2 relative group ${selectedCandidateId === cand.application_id
                        ? 'bg-blue-600 border-blue-500 shadow-2xl shadow-blue-600/20 text-white'
                        : 'bg-slate-800/20 border-transparent hover:border-slate-700 hover:bg-slate-800/40 text-slate-300'
                      }`}
                  >
                    <div className="flex items-center gap-4">
                      <div className={`w-12 h-12 rounded-2xl flex items-center justify-center ${selectedCandidateId === cand.application_id ? 'bg-white/20' : 'bg-slate-800 group-hover:bg-slate-700'
                        }`}>
                        <User className="w-6 h-6" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-1 mb-1">
                          <h3 className="text-sm font-black truncate">{cand.candidate_name}</h3>
                          <Award className={`w-3 h-3 ${cand.score >= 80 ? 'text-green-400' : 'text-blue-400'}`} />
                        </div>
                        <p className={`text-[10px] font-bold uppercase tracking-tight truncate ${selectedCandidateId === cand.application_id ? 'text-blue-100' : 'text-slate-500'
                          }`}>
                          {cand.job_title}
                        </p>
                      </div>
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 flex flex-col relative overflow-hidden bg-[#0A101F]">
        {/* Top Intelligence Metrics */}
        <div className="px-8 py-6 grid grid-cols-3 gap-6 bg-[#0F172A]/50 border-b border-slate-800/50 backdrop-blur-md">
          <div className="flex items-center gap-4 group">
            <div className="w-12 h-12 bg-blue-600/10 rounded-2xl flex items-center justify-center border border-blue-500/10 group-hover:border-blue-500/30 transition-all">
              <Layers className="w-6 h-6 text-blue-500" />
            </div>
            <div>
              <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest flex items-center gap-2">
                Pending Bench
                <span className="flex h-2 w-2 relative">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                </span>
              </p>
              <p className="text-xl font-black text-white">{candidates.length}</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 bg-orange-600/10 rounded-2xl flex items-center justify-center border border-orange-500/10">
              <CalendarIcon className="w-6 h-6 text-orange-500" />
            </div>
            <div>
              <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Active Schedule</p>
              <p className="text-xl font-black text-white">{interviews.filter(i => i.status !== 'completed').length}</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 bg-green-600/10 rounded-2xl flex items-center justify-center border border-green-500/10">
              <CheckCircle2 className="w-6 h-6 text-green-500" />
            </div>
            <div>
              <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Completed Today</p>
              <p className="text-xl font-black text-white">{interviews.filter(i => i.status === 'completed').length}</p>
            </div>
          </div>
        </div>

        <AnimatePresence mode="wait">
          {selectedCandidate ? (
            <motion.div key={selectedCandidate.application_id} initial={{ opacity: 0, scale: 0.99 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.2 }} className="flex flex-col h-full">
              <div className="p-8 pb-4 flex items-center justify-between border-b border-slate-800/50 bg-[#0F172A]">
                <div>
                  <h2 className="text-2xl font-black tracking-tight leading-none mb-1">{selectedCandidate.candidate_name}</h2>
                  <div className="flex items-center gap-4 mt-2">
                    <span className={`text-[10px] font-black uppercase tracking-widest px-3 py-1 rounded-full border ${getStageColor(selectedCandidate.stage)}`}>
                      {selectedCandidate.stage} Phase
                    </span>
                    <span className="text-xs font-bold text-slate-500 flex items-center gap-1">
                      <Target className="w-3.5 h-3.5" /> ID-{selectedCandidate.application_id.slice(0, 8)}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <a href={selectedCandidate.resume_url || '#'} target="_blank" rel="noreferrer"
                    className="p-3 bg-slate-800 hover:bg-slate-700 rounded-xl transition-all text-blue-400">
                    <ExternalLink className="w-5 h-5" />
                  </a>
                </div>
              </div>

              <div className="px-8 py-4 bg-[#0F172A] border-b border-slate-800/50 flex flex-wrap gap-4 items-center">
                <div className="flex-1 min-w-[300px]">
                  <div className="flex items-center gap-2 mb-1">
                    <MessageSquare className="w-3.5 h-3.5 text-blue-500" />
                    <span className="text-[10px] font-black uppercase text-blue-500/50 tracking-widest">AI Intelligence</span>
                  </div>
                  <p className="text-xs text-slate-400 font-medium italic line-clamp-1 border-l-2 border-blue-500/30 pl-3">
                    "{selectedCandidate.ai_summary || "Processing matching insights..."}"
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {selectedCandidate.skills?.slice(0, 4).map(skill => (
                    <span key={skill} className="px-2 py-1 bg-slate-800/50 border border-white/5 rounded-lg text-[9px] font-bold text-slate-400 uppercase tracking-tight">
                      {skill}
                    </span>
                  ))}
                </div>
              </div>

              <div className="flex-1 flex relative">
                <div className="flex-1 bg-slate-100 relative overflow-hidden">
                  {selectedCandidate.resume_url ? (
                    <iframe src={`${selectedCandidate.resume_url}#toolbar=0`} className="w-full h-full border-none" />
                  ) : (
                    <div className="w-full h-full flex flex-col items-center justify-center opacity-20"><FileText className="w-20 h-20" /></div>
                  )}
                </div>

                <div className="absolute bottom-10 left-1/2 -translate-x-1/2 w-[90%] max-w-[600px] bg-slate-900/90 backdrop-blur-2xl border border-white/5 rounded-[2.5rem] p-8 shadow-2xl z-20">
                  <div className="flex items-center justify-between mb-6">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 bg-yellow-500/10 rounded-xl flex items-center justify-center">
                        <Star className="w-4 h-4 text-yellow-500" />
                      </div>
                      <h4 className="text-xs font-black uppercase tracking-widest text-slate-300"> Verdict</h4>
                    </div>
                    <div className="flex gap-1 bg-black/20 p-1 rounded-xl">
                      {[1, 2, 3, 4, 5].map(s => (
                        <button key={s} disabled={!!processingId} onClick={() => setRating(s)} className={`w-8 h-8 rounded-lg flex items-center justify-center transition-all ${rating >= s ? 'bg-yellow-500 text-white' : 'text-slate-600'
                          }`}><Star className={`w-4 h-4 ${rating >= s ? 'fill-current' : ''}`} /></button>
                      ))}
                    </div>
                  </div>

                  <textarea
                    value={feedbackText} disabled={!!processingId} onChange={e => setFeedbackText(e.target.value)}
                    placeholder="Executive summary of the candidate's alignment..."
                    className="w-full bg-black/20 border border-white/5 p-4 rounded-2xl text-sm font-medium focus:ring-1 focus:ring-blue-500 outline-none resize-none mb-6 h-28"
                  />

                  <div className="grid grid-cols-2 gap-4">
                    <button disabled={!!processingId || rating === 0} onClick={() => handleSubmitAction('reject')}
                      className="py-4 bg-white/5 hover:bg-red-500/10 text-slate-400 hover:text-red-500 rounded-2xl font-black uppercase tracking-widest text-[10px] border border-white/5 transition-all">
                      [ REJECT ]
                    </button>
                    <button disabled={!!processingId || rating === 0} onClick={() => handleSubmitAction('select')}
                      className="py-4 bg-blue-600 hover:bg-blue-500 text-white rounded-2xl font-black uppercase tracking-widest text-[10px] shadow-xl transition-all">
                      [ SELECT ]
                    </button>
                  </div>
                </div>
              </div>
            </motion.div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center opacity-20 p-20 text-center">
              <Zap className="w-32 h-32 mb-8 text-blue-500" />
              <h3 className="text-3xl font-black tracking-tighter uppercase">Command Center</h3>
              <p className="text-sm font-medium mt-4">Select a candidate to initialize workspace</p>
            </div>
          )}
        </AnimatePresence>
      </div>

      <div className="w-[360px] border-l border-slate-800/50 flex flex-col bg-slate-900/40 backdrop-blur-xl shrink-0">
        <div className="p-8">
          <h3 className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] mb-8 flex items-center gap-2">
            <CalendarIcon className="w-3 h-3" /> Command Schedule
          </h3>

          <div className="space-y-4">
            {interviews.length === 0 ? (
              <div className="py-10 text-center opacity-30 border border-dashed border-slate-800 rounded-[2rem]">
                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">No interviews scheduled</p>
              </div>
            ) : interviews.map(int => (
              <div key={int.interview_id} className="p-5 bg-slate-800/30 border border-white/5 rounded-[2rem] group hover:border-blue-500/30 transition-all">
                <div className="flex items-center justify-between mb-4">
                  <div className={`text-[10px] font-black px-2 py-0.5 rounded-lg flex items-center gap-1 ${int.status === 'completed' ? 'bg-green-500/10 text-green-500' : 'bg-orange-500/10 text-orange-500'
                    }`}>
                    {int.status === 'completed' ? <CheckCircle2 className="w-2.5 h-2.5" /> : <Clock className="w-2.5 h-2.5" />}
                    {int.status.toUpperCase()}
                  </div>
                  <p className="text-[10px] font-bold text-slate-500">{formatDate(int.scheduled_time)}</p>
                </div>
                <h4 className="text-sm font-black mb-1">{int.candidate_name}</h4>
                <p className="text-[10px] font-bold text-slate-500 uppercase truncate mb-4">{int.job_title}</p>

                {int.status !== 'completed' && int.meeting_link && (
                  <a href={int.meeting_link} target="_blank" rel="noreferrer"
                    className="w-full flex items-center justify-center gap-2 py-3 bg-blue-600/10 hover:bg-blue-600 text-blue-500 hover:text-white rounded-xl transition-all text-[10px] font-black uppercase tracking-widest">
                    <Video className="w-4 h-4" /> Join Mission
                  </a>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="mt-auto p-8 border-t border-slate-800/50">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 bg-slate-800 rounded-2xl flex items-center justify-center text-slate-400">
              <UserCheck className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs font-black">Interviewer Access</p>
              <p className="text-[10px] font-bold text-slate-500 uppercase italic">Strictly Authorized</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
