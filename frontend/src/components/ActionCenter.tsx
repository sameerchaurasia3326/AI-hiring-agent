import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { Zap, UserCheck, Calendar, FileText, ChevronRight, CheckCircle2 } from 'lucide-react';

interface Job {
  id: string;
  title: string;
  department: string;
  status: string;
  applicants_count: number;
  shortlist_count: number;
}

interface ActionItem {
  id: string;
  type: 'review' | 'schedule' | 'jd';
  priority: 'high' | 'medium';
  icon: React.ElementType;
  iconColor: string;
  iconBg: string;
  title: string;
  description: string;
  actionLabel: string;
  jobId: string;
}

interface ActionCenterProps {
  jobs: Job[];
}

export default function ActionCenter({ jobs }: ActionCenterProps) {
  const navigate = useNavigate();

  // Derive actionable items from live job data
  const items: ActionItem[] = [];

  jobs.forEach((job) => {
    // Candidates shortlisted but likely not reviewed yet
    if (job.shortlist_count > 0) {
      items.push({
        id: `review-${job.id}`,
        type: 'review',
        priority: 'high',
        icon: UserCheck,
        iconColor: 'text-emerald-600',
        iconBg: 'bg-emerald-50',
        title: `${job.shortlist_count} candidate${job.shortlist_count > 1 ? 's' : ''} shortlisted`,
        description: `${job.title} — Review shortlisted profiles and approve for interview.`,
        actionLabel: 'Review Now',
        jobId: job.id,
      });
    }

    // Job has applicants but nothing shortlisted — scoring may be stuck or waiting
    if (job.applicants_count > 0 && job.shortlist_count === 0) {
      items.push({
        id: `score-${job.id}`,
        type: 'schedule',
        priority: 'medium',
        icon: Calendar,
        iconColor: 'text-amber-600',
        iconBg: 'bg-amber-50',
        title: `${job.applicants_count} applicant${job.applicants_count > 1 ? 's' : ''} pending scoring`,
        description: `${job.title} — AI is screening; no one shortlisted yet. Check pipeline progress.`,
        actionLabel: 'View Pipeline',
        jobId: job.id,
      });
    }

    // Jobs in draft/pending state — JD may need review
    if (job.status === 'pending' || job.status === 'draft') {
      items.push({
        id: `jd-${job.id}`,
        type: 'jd',
        priority: 'high',
        icon: FileText,
        iconColor: 'text-blue-600',
        iconBg: 'bg-blue-50',
        title: 'Job Description needs approval',
        description: `${job.title} — AI has generated a JD draft. Review and publish to start receiving applicants.`,
        actionLabel: 'Review JD',
        jobId: job.id,
      });
    }
  });

  if (items.length === 0) return null;

  // Sort: high priority first
  items.sort((a, _b) => (a.priority === 'high' ? -1 : 1));

  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
      className="mb-8"
    >
      {/* Section header */}
      <div className="flex items-center gap-2.5 mb-4">
        <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 text-amber-700 text-xs font-black uppercase tracking-widest px-3 py-1.5 rounded-full">
          <Zap className="w-3.5 h-3.5 fill-current" />
          Needs Your Attention
          <span className="ml-1 bg-amber-500 text-white text-[10px] font-black rounded-full px-1.5 py-0.5">
            {items.length}
          </span>
        </div>
        <div className="flex-1 h-px bg-gray-100" />
      </div>

      {/* Action items list */}
      <div className="flex flex-col gap-3">
        <AnimatePresence>
          {items.map((item, idx) => (
            <motion.div
              key={item.id}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 12 }}
              transition={{ delay: idx * 0.06 }}
              className={`group flex items-center gap-4 bg-white border rounded-2xl px-5 py-4 shadow-sm hover:shadow-md transition-all ${
                item.priority === 'high'
                  ? 'border-l-4 border-amber-400 hover:border-amber-500'
                  : 'border-gray-100 hover:border-gray-200'
              }`}
            >
              {/* Icon */}
              <div className={`shrink-0 w-10 h-10 rounded-xl flex items-center justify-center ${item.iconBg}`}>
                <item.icon className={`w-5 h-5 ${item.iconColor}`} />
              </div>

              {/* Text */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-bold text-gray-900 leading-tight">{item.title}</p>
                <p className="text-xs text-gray-500 mt-0.5 truncate">{item.description}</p>
              </div>

              {/* Priority badge */}
              {item.priority === 'high' && (
                <span className="shrink-0 hidden sm:inline-flex items-center gap-1 text-[10px] font-black text-amber-600 bg-amber-50 border border-amber-200 px-2 py-1 rounded-full uppercase tracking-widest">
                  High Priority
                </span>
              )}

              {/* Action button */}
              <button
                onClick={() => navigate(`/dashboard/jobs/${item.jobId}`)}
                className="shrink-0 inline-flex items-center gap-1.5 bg-slate-900 hover:bg-blue-600 text-white text-xs font-bold px-4 py-2 rounded-xl transition-all whitespace-nowrap group-hover:scale-[1.03] active:scale-[0.97]"
              >
                {item.actionLabel}
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* All clear state (won't render because we return null above, but good for direct use) */}
      {items.length === 0 && (
        <div className="flex items-center gap-3 bg-emerald-50 border border-emerald-200 rounded-2xl px-5 py-4">
          <CheckCircle2 className="w-5 h-5 text-emerald-600" />
          <p className="text-sm font-semibold text-emerald-700">You're all caught up! No pending actions.</p>
        </div>
      )}
    </motion.section>
  );
}
