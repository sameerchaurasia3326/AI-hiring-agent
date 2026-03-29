import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Mail, Star, Clock, ArrowLeft, MessageSquare, ShieldCheck, ChevronRight } from 'lucide-react';
import { api } from '../services/api';

interface Feedback {
  id: string;
  decision: string;
  rating: number;
  feedback_text: string;
  interviewer_name: string;
  stage_name: string;
  created_at: string;
}

interface Candidate {
  id: string;
  name: string;
  email: string;
  status: string;
}

export default function CandidateDetail() {
  const { job_id, candidate_id } = useParams();
  const navigate = useNavigate();
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [feedbacks, setFeedbacks] = useState<Feedback[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [candData, feedbackData] = await Promise.all([
          api.getCandidate(candidate_id!),
          api.getCandidateFeedback(candidate_id!)
        ]);
        setCandidate(candData);
        setFeedbacks(feedbackData);
      } catch (err: any) {
        console.error(err);
        setError('Failed to load candidate details.');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [candidate_id]);

  const getDecisionStyles = (decision: string) => {
    switch (decision) {
      case 'strong_yes': return 'bg-green-600 text-white border-green-700';
      case 'yes': return 'bg-emerald-100 text-emerald-800 border-emerald-200';
      case 'no': return 'bg-orange-100 text-orange-800 border-orange-200';
      case 'strong_no': return 'bg-red-600 text-white border-red-700';
      default: return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'rejected': return 'bg-red-50 text-red-700 border-red-100';
      case 'completed': return 'bg-green-50 text-green-700 border-green-100';
      default: return 'bg-blue-50 text-blue-700 border-blue-100';
    }
  };

  if (loading) {
    return (
      <div className="h-64 flex items-center justify-center text-blue-600">
        <Clock className="w-8 h-8 animate-spin" />
      </div>
    );
  }

  if (error || !candidate) {
    return (
      <div className="p-8 text-center bg-red-50 rounded-2xl border border-red-100 text-red-600 font-bold">
        {error || 'Candidate not found'}
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto pb-20">
      <button 
        onClick={() => navigate(`/dashboard/jobs/${job_id}`)}
        className="flex items-center text-sm font-black text-gray-400 hover:text-gray-900 transition-colors mb-10 uppercase tracking-widest"
      >
        <ArrowLeft className="w-4 h-4 mr-2" /> Back to Job Pipeline
      </button>

      <div className="grid lg:grid-cols-3 gap-8">
        {/* Left Column: Candidate Info */}
        <div className="lg:col-span-1 space-y-8">
          <motion.div 
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-white rounded-[2rem] p-10 shadow-xl shadow-gray-100/50 border border-gray-100 text-center"
          >
            <div className="w-24 h-24 bg-blue-600 rounded-3xl flex items-center justify-center mx-auto mb-6 text-white text-3xl font-black shadow-lg shadow-blue-200">
              {candidate.name.charAt(0)}
            </div>
            <h1 className="text-3xl font-black text-gray-900 leading-tight">{candidate.name}</h1>
            <p className="text-gray-400 font-bold mt-2 flex items-center justify-center gap-2">
              <Mail className="w-4 h-4" /> {candidate.email}
            </p>
            
            <div className={`mt-8 px-4 py-2 rounded-full border text-xs font-black uppercase tracking-widest inline-block ${getStatusBadge(candidate.status)}`}>
              {candidate.status}
            </div>
          </motion.div>

          <div className="bg-gray-900 rounded-[2rem] p-8 text-white shadow-2xl">
            <h3 className="text-sm font-black text-gray-400 uppercase tracking-[0.2em] mb-6 flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-blue-400" /> Pipeline Meta
            </h3>
            <div className="space-y-6">
              <div className="flex justify-between items-center">
                <span className="text-gray-500 font-bold text-xs uppercase tracking-widest">Total Feedback</span>
                <span className="text-2xl font-black text-blue-400">{feedbacks.length}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500 font-bold text-xs uppercase tracking-widest">Avg Rating</span>
                <span className="text-2xl font-black text-yellow-400">
                  {feedbacks.length > 0 
                    ? (feedbacks.reduce((acc, curr) => acc + curr.rating, 0) / feedbacks.length).toFixed(1)
                    : 'N/A'
                  }
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Feedback List */}
        <div className="lg:col-span-2 space-y-8">
          <div className="mb-4">
            <h2 className="text-2xl font-black text-gray-900 tracking-tight flex items-center gap-3">
              <MessageSquare className="w-6 h-6 text-blue-600" /> Interview Evaluations
            </h2>
            <p className="text-gray-500 font-medium mt-1">Direct feedback from the hiring team.</p>
          </div>

          {feedbacks.length === 0 ? (
            <div className="bg-white rounded-[2rem] p-16 border-2 border-dashed border-gray-100 text-center">
              <Clock className="w-12 h-12 text-gray-200 mx-auto mb-4" />
              <p className="text-gray-400 font-bold uppercase tracking-widest text-xs">No evaluations submitted yet</p>
            </div>
          ) : (
            <div className="space-y-6">
              {feedbacks.map((f, idx) => (
                <motion.div
                  key={f.id}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: idx * 0.1 }}
                  className="bg-white rounded-3xl p-8 border border-gray-100 shadow-sm hover:shadow-md transition-shadow relative overflow-hidden"
                >
                  <div className="flex justify-between items-start mb-6">
                    <div>
                      <div className="flex items-center gap-3 mb-2">
                        <span className="text-blue-600 text-[10px] font-black uppercase tracking-widest bg-blue-50 px-2 py-0.5 rounded-full">
                          {f.stage_name}
                        </span>
                        <ChevronRight className="w-3 h-3 text-gray-300" />
                        <span className="text-gray-900 font-black text-sm uppercase tracking-wider">{f.interviewer_name}</span>
                      </div>
                      <div className="flex gap-1 text-yellow-400">
                        {[1, 2, 3, 4, 5].map(s => (
                          <Star key={s} className={`w-4 h-4 ${f.rating >= s ? 'fill-current' : 'text-gray-100'}`} />
                        ))}
                      </div>
                    </div>
                    <div className={`px-4 py-2 rounded-xl border text-[10px] font-black uppercase tracking-widest shadow-sm ${getDecisionStyles(f.decision)}`}>
                      {f.decision.replace('_', ' ')}
                    </div>
                  </div>

                  <div className="bg-gray-50 rounded-2xl p-6 relative">
                    <MessageSquare className="absolute -top-3 -left-3 w-8 h-8 text-gray-100 fill-current" />
                    <p className="text-gray-700 font-medium leading-relaxed italic">
                      "{f.feedback_text}"
                    </p>
                  </div>

                  <div className="mt-6 text-[10px] font-black text-gray-300 uppercase tracking-[0.2em] flex items-center gap-2 justify-end">
                    <Clock className="w-3 h-3" /> {new Date(f.created_at).toLocaleDateString()}
                  </div>
                </motion.div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
