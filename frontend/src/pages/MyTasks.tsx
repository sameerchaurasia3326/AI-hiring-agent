import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { api } from '../services/api';
import { 
  Clock, UserCheck, CheckCircle2, XCircle, Briefcase, User, 
  Star, ChevronRight, MessageSquare, Video, FileText, 
  Calendar as CalendarIcon, Hash, Inbox, Loader2, Bookmark
} from 'lucide-react';

interface Task {
  application_id: string;
  candidate_id: string;
  candidate_name: string;
  candidate_email: string;
  job_id: string;
  job_title: string;
  stage_id: string | null;
  stage_name: string;
  status: string;
  interview_slot: string | null;
  meeting_link: string | null;
  resume_url: string | null;
}

export default function MyTasks() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  
  // Form state
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [decision, setDecision] = useState<string>('');
  const [rating, setRating] = useState<number>(0);
  const [feedbackText, setFeedbackText] = useState<string>('');

  const fetchTasks = async () => {
    try {
      const data = await api.getMyTasks();
      setTasks(data.tasks || []);
    } catch (err) {
      setError('Could not load your tasks. Please check your connection.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
  }, []);

  const handleSubmitFeedback = async (task: Task) => {
    if (!decision || rating === 0 || !feedbackText) {
      setError('Please provide a decision, rating, and feedback text.');
      return;
    }

    setProcessingId(task.application_id);
    setError(null);
    setSuccessMsg(null);
    
    try {
      await api.submitFeedback({
        candidate_id: task.candidate_id,
        stage_id: task.stage_id || '', 
        decision: decision,
        rating: rating,
        feedback_text: feedbackText
      });

      setSuccessMsg(`Feedback submitted for ${task.candidate_name}.`);
      setSelectedTaskId(null);
      resetForm();
      await fetchTasks();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'An error occurred during submission.');
    } finally {
      setProcessingId(null);
    }
  };

  const resetForm = () => {
    setDecision('');
    setRating(0);
    setFeedbackText('');
  };

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    return d.toLocaleString([], { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const selectedTask = tasks.find(t => t.application_id === selectedTaskId);

  if (loading) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center gap-4">
        <div className="relative">
            <div className="w-16 h-16 border-4 border-blue-100 border-t-blue-600 rounded-full animate-spin"></div>
            <Clock className="w-6 h-6 text-blue-600 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
        </div>
        <p className="text-gray-400 font-bold animate-pulse uppercase tracking-widest text-xs">Synchronizing your dashboard...</p>
      </div>
    );
  }

  return (
    <div className="max-w-[1200px] mx-auto animate-fade-in pb-12">
      <AnimatePresence>
        {successMsg && (
          <motion.div 
            initial={{ opacity: 0, y: -20, scale: 0.9 }} 
            animate={{ opacity: 1, y: 0, scale: 1 }} 
            exit={{ opacity: 0, scale: 0.9 }}
            className="fixed top-8 right-8 z-50 bg-white border border-green-100 shadow-2xl rounded-2xl p-6 flex items-center gap-4"
          >
            <div className="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center">
              <CheckCircle2 className="w-6 h-6 text-green-600" />
            </div>
            <div>
                <p className="font-bold text-gray-900">{successMsg}</p>
                <p className="text-xs text-gray-500">The pipeline has been updated.</p>
            </div>
            <button onClick={() => setSuccessMsg(null)} className="ml-4 p-2 hover:bg-gray-50 rounded-lg transition-colors text-gray-300">
                <XCircle className="w-4 h-4" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="mb-12 flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div className="relative">
          <div className="absolute -top-6 -left-6 w-24 h-24 bg-blue-400/10 rounded-full blur-3xl animate-pulse"></div>
          <h1 className="text-5xl font-black text-slate-900 tracking-tighter mb-3 relative">
            My Tasks <span className="text-blue-600 pointer-events-none">.</span>
          </h1>
          <p className="text-slate-500 font-medium text-lg flex items-center gap-2">
            <Bookmark className="w-5 h-5 text-blue-500" />
            Active evaluations for currently assigned candidates.
          </p>
        </div>
        
        <div className="bg-slate-900 text-white px-6 py-3 rounded-2xl flex items-center gap-4 shadow-xl shadow-slate-900/10 border border-white/5">
            <div className="flex -space-x-2">
                {tasks.slice(0,3).map((t, i) => (
                    <div key={i} className="w-8 h-8 rounded-full bg-slate-800 border-2 border-slate-900 flex items-center justify-center text-[10px] font-bold">
                        {t.candidate_name.charAt(0)}
                    </div>
                ))}
            </div>
            <span className="text-sm font-bold text-slate-400">
                <span className="text-white">{tasks.length}</span> pending actions
            </span>
        </div>
      </div>

      <div className="grid lg:grid-cols-[1fr,400px] gap-8 items-start">
        {/* Task List */}
        <div className="space-y-4">
          {tasks.length === 0 ? (
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-white rounded-[2.5rem] p-20 text-center border-2 border-dashed border-slate-100 flex flex-col items-center"
            >
              <div className="w-20 h-20 bg-slate-50 rounded-3xl flex items-center justify-center mb-6 rotate-3">
                <Inbox className="w-10 h-10 text-slate-300" />
              </div>
              <h3 className="text-2xl font-black text-slate-900">Inbox Zero</h3>
              <p className="text-slate-400 mt-2 max-w-xs mx-auto font-medium">No candidates are currently assigned to you for evaluation.</p>
            </motion.div>
          ) : (
            tasks.map((task) => (
              <motion.div
                key={task.application_id}
                layoutId={task.application_id}
                onClick={() => setSelectedTaskId(task.application_id)}
                className={`group cursor-pointer rounded-[2rem] p-6 transition-all border-2 ${
                  selectedTaskId === task.application_id 
                  ? 'bg-blue-600 border-blue-600 shadow-2xl shadow-blue-600/20 translate-x-2' 
                  : 'bg-white border-transparent hover:border-slate-100 shadow-sm hover:shadow-xl hover:shadow-slate-200/50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-5">
                    <div className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-all ${
                      selectedTaskId === task.application_id ? 'bg-white/20 text-white' : 'bg-slate-50 text-slate-400 group-hover:bg-blue-50 group-hover:text-blue-500'
                    }`}>
                      <User className="w-7 h-7" />
                    </div>
                    <div>
                      <h3 className={`text-xl font-black leading-none mb-2 ${selectedTaskId === task.application_id ? 'text-white' : 'text-slate-900'}`}>
                        {task.candidate_name}
                      </h3>
                      <div className={`flex items-center gap-3 text-xs font-bold uppercase tracking-widest ${selectedTaskId === task.application_id ? 'text-blue-100' : 'text-slate-400'}`}>
                        <span className="flex items-center gap-1.5"><Briefcase className="w-3.5 h-3.5" /> {task.job_title}</span>
                        <div className={`w-1 h-1 rounded-full ${selectedTaskId === task.application_id ? 'bg-blue-300' : 'bg-slate-200'}`}></div>
                        <span className={`px-2 py-0.5 rounded-lg ${selectedTaskId === task.application_id ? 'bg-white/10' : 'bg-slate-100 text-slate-500'}`}>
                            {task.stage_name}
                        </span>
                      </div>
                    </div>
                  </div>
                  
                  <div className="flex flex-col items-end gap-2">
                    {task.interview_slot ? (
                        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-xl text-[10px] font-black uppercase tracking-tighter ${
                            selectedTaskId === task.application_id ? 'bg-white/10 text-white' : 'bg-orange-50 text-orange-600'
                        }`}>
                            <CalendarIcon className="w-3 h-3" />
                            {formatDate(task.interview_slot)}
                        </div>
                    ) : (
                        <div className={`px-3 py-1.5 rounded-xl text-[10px] font-black uppercase tracking-tighter ${
                            selectedTaskId === task.application_id ? 'bg-white/10 text-white' : 'bg-slate-100 text-slate-400'
                        }`}>
                            Waiting Schedule
                        </div>
                    )}
                    <ChevronRight className={`w-5 h-5 transition-transform ${selectedTaskId === task.application_id ? 'text-white rotate-90' : 'text-slate-300 group-hover:text-blue-500'}`} />
                  </div>
                </div>
              </motion.div>
            ))
          )}
        </div>

        {/* Action Panel / Feedback Sidebar */}
        <div className="sticky top-8">
          <AnimatePresence mode="wait">
            {selectedTask ? (
              <motion.div
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                className="bg-white rounded-[2.5rem] shadow-2xl border border-slate-100 overflow-hidden flex flex-col min-h-[600px]"
              >
                <div className="p-8 bg-slate-900 text-white relative h-48 flex flex-col justify-end">
                  <div className="absolute top-8 left-8 p-3 bg-white/10 rounded-2xl backdrop-blur-md border border-white/10">
                    <User className="w-8 h-8 text-blue-400" />
                  </div>
                  <h2 className="text-2xl font-black tracking-tight">{selectedTask.candidate_name}</h2>
                  <p className="text-slate-400 text-sm font-semibold flex items-center gap-2">
                      <Hash className="w-3.5 h-3.5" /> ID-{selectedTask.application_id.slice(0,8)}
                  </p>
                </div>

                <div className="p-8 flex-1 space-y-8">
                  {/* Quick Actions */}
                  <div className="grid grid-cols-2 gap-4">
                    {selectedTask.meeting_link ? (
                        <a 
                            href={selectedTask.meeting_link} 
                            target="_blank" 
                            rel="noopener noreferrer"
                            className="bg-blue-600 hover:bg-blue-700 text-white p-4 rounded-2xl flex flex-col items-center gap-2 transition-all active:scale-95 shadow-lg shadow-blue-200"
                        >
                            <Video className="w-6 h-6" />
                            <span className="text-[10px] font-black uppercase tracking-widest">Join Meet</span>
                        </a>
                    ) : (
                        <div className="bg-slate-50 text-slate-300 p-4 rounded-2xl flex flex-col items-center gap-2 cursor-not-allowed">
                            <Video className="w-6 h-6" />
                            <span className="text-[10px] font-black uppercase tracking-widest">No Link</span>
                        </div>
                    )}

                    {selectedTask.resume_url ? (
                        <a 
                            href={selectedTask.resume_url} 
                            target="_blank" 
                            rel="noopener noreferrer"
                            className="bg-slate-900 hover:bg-slate-800 text-white p-4 rounded-2xl flex flex-col items-center gap-2 transition-all active:scale-95 shadow-lg shadow-slate-200"
                        >
                            <FileText className="w-6 h-6" />
                            <span className="text-[10px] font-black uppercase tracking-widest">View CV</span>
                        </a>
                    ) : (
                        <div className="bg-slate-50 text-slate-300 p-4 rounded-2xl flex flex-col items-center gap-2 cursor-not-allowed">
                            <FileText className="w-6 h-6" />
                            <span className="text-[10px] font-black uppercase tracking-widest">No Resume</span>
                        </div>
                    )}
                  </div>

                  {/* Feedback Form */}
                  <div className="space-y-6">
                    <div className="space-y-3">
                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Overall Rating</label>
                        <div className="flex justify-between p-1 bg-slate-50 rounded-2xl border border-slate-100/50">
                            {[1, 2, 3, 4, 5].map((s) => (
                                <button
                                    key={s}
                                    onClick={() => setRating(s)}
                                    className={`w-12 h-12 rounded-xl flex items-center justify-center transition-all ${
                                        rating >= s ? 'bg-yellow-400 text-white shadow-lg' : 'text-slate-300 hover:text-slate-400'
                                    }`}
                                >
                                    <Star className={`w-5 h-5 ${rating >= s ? 'fill-current' : ''}`} />
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="space-y-3">
                        <label className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Final Decision</label>
                        <select 
                            value={decision}
                            onChange={(e) => setDecision(e.target.value)}
                            className="w-full bg-slate-50 border border-slate-100 p-4 rounded-2xl font-bold focus:ring-2 focus:ring-blue-500 outline-none appearance-none cursor-pointer"
                        >
                            <option value="">Move candidate to...</option>
                            <option value="strong_yes">Pass (Strong Fit)</option>
                            <option value="yes">Pass (Qualified)</option>
                            <option value="no">Reject (Unqualified)</option>
                            <option value="strong_no">Reject (Culture Gap)</option>
                        </select>
                    </div>

                    <div className="space-y-3">
                        <div className="flex justify-between items-center">
                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Evaluation Notes</label>
                            <span className="text-[10px] font-bold text-slate-300">{feedbackText.length}/1000</span>
                        </div>
                        <textarea
                            value={feedbackText}
                            onChange={(e) => setFeedbackText(e.target.value)}
                            placeholder="Type your feedback..."
                            rows={6}
                            className="w-full bg-slate-50 border border-slate-100 p-4 rounded-2xl font-medium focus:ring-2 focus:ring-blue-500 outline-none resize-none placeholder:text-slate-300 text-sm"
                        />
                    </div>
                  </div>
                </div>

                <div className="p-8 pt-0 mt-auto">
                    <button
                        disabled={processingId !== null || !decision || rating === 0}
                        onClick={() => handleSubmitFeedback(selectedTask)}
                        className="w-full py-5 bg-blue-600 hover:bg-blue-700 text-white rounded-[1.25rem] font-black shadow-2xl shadow-blue-500/20 transition-all disabled:opacity-30 flex items-center justify-center gap-3 active:scale-95 uppercase tracking-widest text-xs"
                    >
                        {processingId === selectedTask.application_id ? <Loader2 className="w-5 h-5 animate-spin" /> : <UserCheck className="w-5 h-5 font-bold" />}
                        Complete Evaluation
                    </button>
                    {error && <p className="mt-4 text-center text-red-500 text-[10px] font-bold uppercase tracking-tight">{error}</p>}
                </div>
              </motion.div>
            ) : (
              <div className="h-[600px] border-2 border-dashed border-slate-100 rounded-[2.5rem] flex flex-col items-center justify-center p-12 text-center">
                <div className="w-16 h-16 bg-slate-50 rounded-full flex items-center justify-center mb-6">
                    <MessageSquare className="w-8 h-8 text-slate-200" />
                </div>
                <h3 className="text-xl font-black text-slate-900">Evaluation Mode</h3>
                <p className="text-slate-400 mt-2 text-sm font-medium">Select a candidate from the left to start your evaluation.</p>
              </div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
