import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Users, ArrowLeft, Loader2, Briefcase, MapPin, DollarSign, Layers, FileText, AlertCircle, RefreshCw, Trash2 } from 'lucide-react';
import { api } from '../services/api';
import JobProgress from '../components/JobProgress';

interface JobDetailData {
  id: string;
  title: string;
  department: string;
  location: string;
  experience_required: string;
  salary_range: string;
  required_skills: string[];
  status: string;
  pipeline_state: string;
  is_cancelled: boolean;
  jd_draft: string | null;
  technical_test_mcq: any[] | null;
  hiring_workflow: any[];
  applications: any[];
}

export default function JobDetail() {
  const { job_id } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState<JobDetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(false);
  const [activeTab, setActiveTab] = useState<'overview' | 'candidates' | 'workflow'>('overview');

  const fetchJob = async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      const data = await api.getJob(job_id!);
      setJob(data);
      setFetchError(false);
    } catch (err) {
      console.error(err);
      if (!job) setFetchError(true);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    fetchJob();
    const interval = setInterval(() => fetchJob(true), 5000);
    return () => clearInterval(interval);
  }, [job_id]);

  if (fetchError && !job) {
    return (
      <div className="h-screen w-full flex flex-col items-center justify-center bg-gray-50 border border-gray-100">
        <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} className="bg-white p-10 rounded-2xl shadow-xl flex flex-col items-center max-w-sm text-center">
          <div className="bg-red-50 p-4 rounded-full mb-6">
            <AlertCircle className="w-10 h-10 text-red-500" />
          </div>
          <h2 className="text-2xl font-bold text-gray-900 tracking-tight">Failed to load details</h2>
          <p className="text-gray-500 mt-2 mb-8 text-sm">We couldn't reach the Hiring.AI servers. Please ensure network connectivity.</p>
          <button 
            onClick={() => { setFetchError(false); fetchJob(); }}
            className="w-full bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 px-6 py-3 rounded-xl font-medium shadow-sm transition-all flex items-center justify-center hover:shadow"
          >
            <RefreshCw className="w-5 h-5 mr-2" />
            Retry Connection
          </button>
        </motion.div>
      </div>
    );
  }

  if (loading && !job) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-gray-50">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    );
  }

  if (!job) {
    return (
      <div className="h-screen w-full flex flex-col items-center justify-center bg-gray-50">
        <h2 className="text-2xl font-bold text-gray-900">Job Not Found</h2>
        <button onClick={() => navigate('/dashboard')} className="mt-4 text-blue-600 hover:underline">
          Return to Dashboard
        </button>
      </div>
    );
  }

  const statusColors: Record<string, string> = {
    'draft': 'bg-gray-100 text-gray-800',
    'processing': 'bg-blue-100 text-blue-800',
    'active': 'bg-green-100 text-green-800 border border-green-200',
    'closed': 'bg-red-50 text-red-800'
  };

  return (
    <div className="max-w-5xl mx-auto">
          
          <button onClick={() => navigate('/dashboard')} className="flex items-center text-sm font-medium text-gray-500 hover:text-gray-900 transition-colors mb-6">
            <ArrowLeft className="w-4 h-4 mr-1.5" /> Back to Jobs
          </button>

          {/* Header */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8 mb-6">
            <div className="flex justify-between items-start">
              <div>
                <h1 className="text-3xl font-bold text-gray-900 mb-3">{job.title}</h1>
                <div className="flex flex-wrap items-center gap-4 text-sm text-gray-600 font-medium">
                  <span className="flex items-center"><Briefcase className="w-4 h-4 mr-1.5 text-gray-400" /> {job.department}</span>
                  <span className="flex items-center"><MapPin className="w-4 h-4 mr-1.5 text-gray-400" /> {job.location}</span>
                  <span className="flex items-center"><DollarSign className="w-4 h-4 mr-1.5 text-gray-400" /> {job.salary_range || 'Competitive'}</span>
                  <span className="flex items-center"><Layers className="w-4 h-4 mr-1.5 text-gray-400" /> {job.experience_required}</span>
                </div>
              </div>
              <div className="flex flex-col items-end gap-3">
                <span className={`px-4 py-1.5 rounded-full text-sm font-bold uppercase tracking-wide flex items-center shadow-sm ${statusColors[job.status] || 'bg-gray-100 text-gray-800'}`}>
                  {job.status === 'processing' && <Loader2 className="w-3 h-3 mr-2 animate-spin" />}
                  {job.status.replace(/_/g, ' ')}
                </span>
                {!job.is_cancelled && !job.status.includes('CLOSED') && !job.status.includes('FAILED') && !job.status.includes('OFFER') && (
                  <button 
                    onClick={async () => {
                      if (confirm('Are you sure you want to cancel this AI pipeline? This will stop future automation and save costs.')) {
                         await api.cancelJob(job.id);
                         fetchJob();
                      }
                    }}
                    className="text-xs text-red-600 font-semibold hover:bg-red-50 px-3 py-1.5 rounded-md border border-transparent hover:border-red-200 transition-colors flex items-center shadow-sm"
                  >
                    Cancel AI Pipeline
                  </button>
                )}
                {job.is_cancelled && (
                  <button
                    onClick={async () => {
                      if (confirm(`⚠️ Permanently delete "${job.title}"?\n\nThis will remove all associated data and cannot be undone.`)) {
                        await api.deleteJob(job.id);
                        navigate('/dashboard');
                      }
                    }}
                    className="text-xs text-gray-500 font-semibold hover:bg-red-50 hover:text-red-600 px-3 py-1.5 rounded-md border border-gray-200 hover:border-red-200 transition-colors flex items-center gap-1.5 shadow-sm"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    Delete Job
                  </button>
                )}
              </div>
            </div>
            
            <div className="mt-6 flex gap-2">
              {job.required_skills?.map((skill, idx) => (
                <span key={idx} className="px-3 py-1 bg-gray-100 text-gray-700 rounded-md text-xs font-semibold">{skill}</span>
              ))}
            </div>
            
            <div className="mt-8 border-t border-gray-100 pt-6">
               <JobProgress pipelineState={job.pipeline_state || 'JD_DRAFT'} isCancelled={job.is_cancelled} />
            </div>
          </div>

          {/* Tabs */}
          <div className="flex border-b border-gray-200 mb-6">
            {[
              { id: 'overview', label: 'Overview & JD' },
              { id: 'candidates', label: `Candidates (${job.applications?.length || 0})` },
              { id: 'workflow', label: 'Interview Stages' }
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`py-3 px-6 text-sm font-semibold border-b-2 transition-colors ${activeTab === tab.id ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2 }}
            >
              {activeTab === 'overview' && (
                <>
                  <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
                    <h3 className="text-xl font-bold text-gray-900 mb-6 flex items-center">
                      <FileText className="w-5 h-5 mr-2 text-blue-600" /> Generated Job Description
                    </h3>
                    {job.jd_draft ? (
                      <div className="prose prose-sm max-w-none text-gray-700 whitespace-pre-wrap">
                        {job.jd_draft}
                      </div>
                    ) : job.status === 'closed' || job.status === 'CLOSED' ? (
                      <div className="text-center py-12">
                        <div className="w-14 h-14 bg-red-50 rounded-full flex items-center justify-center mx-auto mb-4">
                          <AlertCircle className="w-7 h-7 text-red-400" />
                        </div>
                        <p className="text-gray-700 font-semibold text-base">Pipeline Cancelled</p>
                        <p className="text-gray-400 text-sm mt-2">This job was cancelled before the AI could complete the Job Description.</p>
                      </div>
                    ) : (
                      <div className="text-center py-12">
                        <Loader2 className="w-8 h-8 animate-spin text-gray-300 mx-auto mb-4" />
                        <p className="text-gray-500 font-medium">The AI is currently drafting this description...</p>
                      </div>
                    )}
                  </div>

                  {/* Technical Test Assessment Section */}
                  {job.technical_test_mcq && job.technical_test_mcq.length > 0 && (
                    <div className="mt-6 bg-white rounded-2xl shadow-sm border border-gray-200 p-8 pt-6">
                      <h3 className="text-xl font-bold text-gray-900 mb-6 flex items-center">
                        <Layers className="w-5 h-5 mr-2 text-indigo-600" /> AI-Generated Technical Assessment
                      </h3>
                      <div className="space-y-6">
                        {job.technical_test_mcq.map((q: any, idx: number) => (
                          <div key={idx} className="p-5 bg-slate-50 rounded-xl border border-slate-100">
                            <p className="font-bold text-gray-900 mb-4 flex items-start gap-3 leading-snug">
                              <span className="bg-indigo-600 text-white w-5 h-5 rounded-full flex items-center justify-center text-[10px] shrink-0 mt-0.5">{idx + 1}</span>
                              {q.question}
                            </p>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pl-8">
                              {q.options.map((opt: string, optIdx: number) => (
                                <div 
                                  key={optIdx} 
                                  className={`px-4 py-2.5 rounded-lg border text-sm font-medium transition-all ${optIdx === q.correct_index ? 'bg-emerald-50 border-emerald-200 text-emerald-700 font-bold' : 'bg-white border-gray-200 text-gray-600'}`}
                                >
                                  {String.fromCharCode(65 + optIdx)}. {opt}
                                  {optIdx === q.correct_index && <span className="ml-2 text-[10px] bg-emerald-500 text-white px-1.5 py-0.5 rounded">Correct</span>}
                                </div>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}

              {activeTab === 'candidates' && (
                <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
                  <h3 className="text-xl font-bold text-gray-900 mb-6 flex items-center">
                    <Users className="w-5 h-5 mr-2 text-blue-600" /> Active Candidates
                  </h3>
                  {job.applications && job.applications.length > 0 ? (
                    <div className="divide-y divide-gray-100 text-sm">
                      {job.applications.map((app, idx) => (
                        <div 
                          key={idx} 
                          className="py-4 flex justify-between items-center hover:bg-gray-50 px-4 rounded-lg transition-colors cursor-pointer"
                          onClick={() => navigate(`/dashboard/jobs/${job.id}/candidates/${app.candidate_id || app.id}`)}
                        >
                          <div>
                            <p className="font-bold text-gray-900">{app.candidate_name}</p>
                            <p className="text-gray-500">{app.candidate_email}</p>
                          </div>
                          <div className="flex items-center gap-4">
                            <span className="font-semibold text-blue-600">Score: {app.score || 'N/A'}</span>
                            <span className="px-2 py-1 bg-gray-100 text-xs font-bold rounded text-gray-600 uppercase">{app.status}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-gray-500 text-center py-8">No candidates have applied or been parsed yet.</p>
                  )}
                </div>
              )}

              {activeTab === 'workflow' && (
                <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
                  <h3 className="text-xl font-bold text-gray-900 mb-6 flex items-center">
                    <Layers className="w-5 h-5 mr-2 text-blue-600" /> Automated Pipeline Stages
                  </h3>
                  {job.hiring_workflow && job.hiring_workflow.length > 0 ? (
                    <div className="space-y-4">
                      {job.hiring_workflow.map((stage: any, idx) => (
                        <div key={idx} className="flex flex-col p-4 bg-gray-50 rounded-lg border border-gray-100">
                          <span className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-1">Stage {idx + 1}</span>
                          <span className="font-semibold text-gray-900">{stage.stage_name}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-gray-500 text-center py-8">No formal stages defined.</p>
                  )}
                </div>
              )}
            </motion.div>
          </AnimatePresence>
    </div>
  );
}
