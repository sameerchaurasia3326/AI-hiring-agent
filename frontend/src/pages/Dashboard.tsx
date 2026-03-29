import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Briefcase, ChevronRight, AlertCircle, Play, Sparkles, ArrowRight, Plus } from 'lucide-react';
import { api } from '../services/api';
import HeroSection from '../components/HeroSection';
import StatsGrid from '../components/StatsGrid';
import ActionCenter from '../components/ActionCenter';
import PipelineBoard from '../components/PipelineBoard';
import JobProgress from '../components/JobProgress';
import ActivityFeed from '../components/ActivityFeed';
import AiInsights from '../components/AiInsights';

interface Job {
  id: string;
  title: string;
  department: string;
  status: string;
  pipeline_state: string;
  is_cancelled: boolean;
  created_at: string;
  applicants_count: number;
  shortlist_count: number;
  interviews_count?: number;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(false);

  const role = localStorage.getItem('hiring_ai_role');
  const userName = localStorage.getItem('hiring_ai_name') || 'Admin';

  useEffect(() => {
    if (role === 'interviewer') {
      navigate('/my-tasks');
    }
  }, [role, navigate]);





  const fetchJobs = async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      const data = await api.getJobs();
      setJobs(data);
      setFetchError(false);
    } catch (err) {
      console.error("Failed to fetch jobs", err);
      if (jobs.length === 0) setFetchError(true);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(() => fetchJobs(true), 5000);
    return () => clearInterval(interval);
  }, []);

  const statsCore = {
    jobsCount: jobs.length,
    applicantsCount: jobs.reduce((acc, job) => acc + (job.applicants_count || 0), 0),
    shortlistedCount: jobs.reduce((acc, job) => acc + (job.shortlist_count || 0), 0),
    interviewsCount: jobs.reduce((acc, job) => acc + (job.interviews_count || 0), 0)
  };

  // --- Action-Driven Hero Helpers ---
  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good Morning';
    if (hour < 17) return 'Good Afternoon';
    return 'Good Evening';
  };

  const getHeroContext = () => {
    if (jobs.length === 0) {
      return {
        message: "Your workspace is ready. Launch your first AI hiring pipeline to get started.",
        urgency: 'neutral' as const,
        lastJob: null,
        canResume: false,
      };
    }
    const waitingForReview = jobs.filter(j => j.shortlist_count > 0);
    const totalApplicants = jobs.reduce((a, j) => a + (j.applicants_count || 0), 0);
    if (waitingForReview.length > 0) {
      return {
        message: `You have ${waitingForReview.reduce((a,j)=>a+j.shortlist_count,0)} shortlisted candidates waiting for review across ${waitingForReview.length} job${waitingForReview.length > 1 ? 's' : ''}.`,
        urgency: 'action' as const,
        lastJob: waitingForReview[0],
        canResume: true,
      };
    }
    if (totalApplicants > 0) {
      return {
        message: `${totalApplicants} candidate${totalApplicants > 1 ? 's' : ''} in the pipeline. AI is screening and scoring in real-time.`,
        urgency: 'info' as const,
        lastJob: jobs[0],
        canResume: true,
      };
    }
    return {
      message: `${jobs.length} active pipeline${jobs.length > 1 ? 's' : ''} running. Waiting for candidate applications to begin scoring.`,
      urgency: 'neutral' as const,
      lastJob: jobs[0],
      canResume: true,
    };
  };

  const heroContext = getHeroContext();


  if (fetchError && jobs.length === 0) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-gray-50">
        <div className="text-center p-8 bg-white rounded-2xl shadow-lg max-w-sm">
          <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <h2 className="text-xl font-bold mb-2">Something went wrong</h2>
          <p className="text-gray-500 mb-6 text-sm">We couldn't load your hiring dashboard. Check your internet connection.</p>
          <button onClick={() => fetchJobs()} className="bg-blue-600 text-white px-6 py-2 rounded-lg font-medium">Retry</button>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="max-w-7xl mx-auto">

          {/* Action-Driven Hero */}
          <motion.div
            initial={{ opacity: 0, y: -16 }}
            animate={{ opacity: 1, y: 0 }}
            className="relative overflow-hidden rounded-3xl mb-8 bg-gradient-to-br from-slate-950 via-[#0B1120] to-indigo-950 border border-white/5 shadow-2xl"
          >
            {/* Mascot background — subtle */}
            <div className="absolute inset-0 opacity-20 pointer-events-none">
              <HeroSection />
            </div>

            <div className="relative z-10 p-10 flex flex-col lg:flex-row lg:items-end gap-8">
              {/* Left: greeting + context */}
              <div className="flex-1 min-w-0">
                {/* Badge */}
                <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-[11px] font-bold tracking-widest uppercase mb-5">
                  <Sparkles className="w-3 h-3" />
                  AI Systems Online
                </div>

                {/* Dynamic greeting */}
                <h1 className="text-4xl lg:text-5xl font-black text-white tracking-tight leading-tight mb-3">
                  {getGreeting()},&nbsp;
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-violet-400">
                    {userName}
                  </span>
                </h1>

                {/* Context-aware message */}
                <p className={`text-lg leading-relaxed mb-8 font-medium ${
                  heroContext.urgency === 'action' ? 'text-amber-300' :
                  heroContext.urgency === 'info'   ? 'text-blue-200' :
                  'text-slate-400'
                }`}>
                  {heroContext.urgency === 'action' && '⚡ '}
                  {heroContext.message}
                </p>

                {/* Primary action buttons */}
                <div className="flex flex-wrap gap-3">
                  {heroContext.canResume && heroContext.lastJob && (
                    <button
                      onClick={() => navigate(`/dashboard/jobs/${heroContext.lastJob!.id}`)}
                      className="inline-flex items-center gap-2.5 bg-white text-slate-900 px-6 py-3.5 rounded-2xl font-bold hover:scale-[1.03] active:scale-[0.98] transition-all shadow-xl shadow-black/20"
                    >
                      <Play className="w-4 h-4 fill-current" />
                      Resume Pipeline
                      <span className="text-xs font-normal text-slate-500 ml-1 truncate max-w-[120px]">
                        {heroContext.lastJob.title}
                      </span>
                    </button>
                  )}
                  <button
                    onClick={() => navigate('/dashboard/jobs/new')}
                    className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-6 py-3.5 rounded-2xl font-bold transition-all shadow-xl shadow-blue-800/30 group"
                  >
                    <Plus className="w-4 h-4 group-hover:rotate-90 transition-transform duration-200" />
                    Create New Job
                  </button>
                </div>
              </div>

              {/* Right: Last active job quick-view (optional) */}
              {heroContext.lastJob && (
                <motion.div
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.15 }}
                  onClick={() => navigate(`/dashboard/jobs/${heroContext.lastJob!.id}`)}
                  className="shrink-0 w-full lg:w-64 bg-white/5 hover:bg-white/10 border border-white/10 rounded-2xl p-5 cursor-pointer group transition-all"
                >
                  <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Last Active Job</p>
                  <h3 className="text-white font-bold text-base leading-snug mb-4 group-hover:text-blue-300 transition-colors">
                    {heroContext.lastJob.title}
                  </h3>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-slate-400">
                      <span className="font-bold text-white">{heroContext.lastJob.applicants_count}</span> applicants
                    </span>
                    <span className="text-green-400 font-bold">
                      {heroContext.lastJob.shortlist_count} shortlisted
                    </span>
                  </div>
                  <div className="mt-4 flex items-center text-[11px] text-slate-500 font-semibold group-hover:text-blue-400 transition-colors">
                    Open Pipeline <ArrowRight className="w-3 h-3 ml-1" />
                  </div>
                  {/* Compact Progress Tracker */}
                  <div className="mt-5 pt-4 border-t border-gray-100">
                    <JobProgress pipelineState={heroContext.lastJob.pipeline_state || 'JD_DRAFT'} isCancelled={heroContext.lastJob.is_cancelled} compact={true} />
                  </div>
                </motion.div>
              )}
            </div>
          </motion.div>

          <StatsGrid {...statsCore} />

          <ActionCenter jobs={jobs} />

          <AiInsights />

          <PipelineBoard />

          {/* Your Jobs + Activity Feed — two column layout on large screens */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 items-start">
            {/* Your Jobs — 2/3 width */}
            <div className="xl:col-span-2">

          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-2xl font-bold text-gray-900 tracking-tight">Your Jobs</h2>
              <p className="text-sm text-gray-400 mt-0.5">Quick access to all your hiring pipelines</p>
            </div>
            {jobs.length > 0 && (
              <span className="text-xs font-black text-gray-400 uppercase tracking-widest bg-gray-100 px-3 py-1.5 rounded-full">
                {jobs.length} total
              </span>
            )}
          </div>

          {loading && jobs.length === 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 pb-12">
              {[1, 2, 3].map(i => (
                <div key={i} className="bg-white border border-gray-100 rounded-3xl p-6 shadow-sm">
                  <div className="flex items-start justify-between mb-5">
                    <div className="w-11 h-11 bg-gray-100 animate-pulse rounded-2xl" />
                    <div className="w-16 h-6 bg-gray-100 animate-pulse rounded-full" />
                  </div>
                  <div className="w-3/4 h-5 bg-gray-100 animate-pulse rounded-md mb-2" />
                  <div className="w-1/2 h-3 bg-gray-100 animate-pulse rounded-md mb-8" />
                  <div className="flex items-center gap-4 pt-4 border-t border-gray-50">
                    <div className="w-12 h-8 bg-gray-100 animate-pulse rounded-md" />
                    <div className="w-px h-7 bg-gray-100" />
                    <div className="w-12 h-8 bg-gray-100 animate-pulse rounded-md" />
                  </div>
                </div>
              ))}
            </div>
          ) : jobs.length === 0 ? (
            <div className="bg-white border-2 border-dashed border-gray-200 rounded-3xl p-16 text-center">
              <div className="w-16 h-16 bg-blue-50 rounded-2xl flex items-center justify-center mx-auto mb-5">
                <Briefcase className="w-8 h-8 text-blue-600" />
              </div>
              <h3 className="text-lg font-bold text-gray-900 mb-2">No jobs yet</h3>
              <p className="text-gray-400 mb-8 text-sm">Launch your first AI hiring pipeline to get started.</p>
              <button onClick={() => navigate('/dashboard/jobs/new')} className="bg-blue-600 text-white px-7 py-3 rounded-2xl font-bold shadow-lg shadow-blue-600/20 hover:bg-blue-500 transition-colors">
                Create First Job
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 pb-12">
              {jobs.map((job, idx) => {
                // Human-readable status label + styling
                const statusMap: Record<string, { label: string; classes: string }> = {
                  active:     { label: 'Active',     classes: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
                  processing: { label: 'In Review',  classes: 'bg-blue-100 text-blue-700 border-blue-200' },
                  draft:      { label: 'Draft',      classes: 'bg-amber-100 text-amber-700 border-amber-200' },
                  closed:     { label: 'Closed',     classes: 'bg-gray-100 text-gray-500 border-gray-200' },
                };
                const statusInfo = statusMap[job.status] ?? { label: job.status, classes: 'bg-gray-100 text-gray-600 border-gray-200' };

                // Human-readable created date
                const createdLabel = job.created_at
                  ? new Date(job.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
                  : 'Unknown date';

                return (
                  <motion.div
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: idx * 0.04 }}
                    key={job.id}
                    onClick={() => navigate(`/dashboard/jobs/${job.id}`)}
                    className="bg-white border border-gray-100 rounded-3xl p-6 shadow-sm hover:shadow-xl hover:-translate-y-0.5 transition-all cursor-pointer group"
                  >
                    {/* Top row: icon + status */}
                    <div className="flex items-start justify-between mb-5">
                      <div className="w-11 h-11 bg-slate-50 rounded-2xl flex items-center justify-center group-hover:bg-blue-50 transition-colors">
                        <Briefcase className="w-5 h-5 text-slate-400 group-hover:text-blue-600 transition-colors" />
                      </div>
                      <span className={`px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest border ${statusInfo.classes}`}>
                        {statusInfo.label}
                      </span>
                    </div>

                    {/* Title & department */}
                    <h3 className="text-base font-bold text-gray-900 leading-snug group-hover:text-blue-600 transition-colors mb-0.5">
                      {job.title}
                    </h3>
                    <p className="text-xs text-gray-400 font-medium mb-1">{job.department || 'General'}</p>

                    {/* Created date */}
                    <p className="text-[11px] text-gray-300 font-medium mb-5">Created {createdLabel}</p>

                    {/* Stats + arrow */}
                    <div className="flex items-center justify-between pt-4 border-t border-gray-50">
                      <div className="flex items-center gap-4">
                        <div>
                          <span className="text-lg font-black text-gray-900 tabular-nums">{job.applicants_count || 0}</span>
                          <span className="block text-[10px] text-gray-400 font-bold uppercase tracking-wider">Applied</span>
                        </div>
                        <div className="w-px h-7 bg-gray-100" />
                        <div>
                          <span className="text-lg font-black text-emerald-600 tabular-nums">{job.shortlist_count || 0}</span>
                          <span className="block text-[10px] text-gray-400 font-bold uppercase tracking-wider">Shortlisted</span>
                        </div>
                      </div>
                      <div className="p-2 rounded-xl bg-gray-50 group-hover:bg-blue-600 group-hover:text-white transition-all">
                        <ChevronRight className="w-4 h-4" />
                      </div>
                    </div>
                    {/* Compact Tracker */}
                    <div className="mt-5 pt-4 border-t border-gray-50">
                      <JobProgress pipelineState={job.pipeline_state || 'JD_DRAFT'} isCancelled={job.is_cancelled} compact={true} />
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}
          </div>
            {/* Activity Feed — 1/3 width */}
            <div className="xl:col-span-1 border-l border-gray-100 xl:pl-6 h-full">
              <ActivityFeed />
            </div>
          </div>
        </div>

        {/* Floating Action Button */}
        <motion.button
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => navigate('/dashboard/jobs/new')}
          className="fixed bottom-8 right-8 z-40 bg-blue-600 text-white p-4 rounded-full shadow-2xl shadow-blue-500/40 flex items-center gap-2 group border border-blue-500 hover:bg-blue-500 transition-colors"
        >
          <div className="bg-white/20 p-1 rounded-full group-hover:rotate-90 transition-transform">
            <Plus className="w-5 h-5" />
          </div>
          <span className="font-bold pr-2">Create Job</span>
        </motion.button>



    </>
  );
}
