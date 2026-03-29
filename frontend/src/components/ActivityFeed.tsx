import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import {
  Upload, Star, Calendar, CheckCircle2, XCircle,
  Activity, RefreshCw, Layers, Mail
} from 'lucide-react';

interface ActivityEvent {
  type: string;
  icon: string;
  title: string;
  description: string;
  timestamp: string;
  job_id: string;
  job_title: string;
  candidate_name: string;
}

// ─── Event config ────────────────────────────────────────────
const EVENT_CONFIG: Record<string, {
  Icon: React.ElementType;
  dot: string;
  pill: string;
}> = {
  resume_uploaded:     { Icon: Upload,       dot: 'bg-blue-500',    pill: 'bg-blue-50 text-blue-600 border-blue-200' },
  scoring:             { Icon: Layers,       dot: 'bg-indigo-500',  pill: 'bg-indigo-50 text-indigo-700 border-indigo-200' },
  shortlisted:         { Icon: Star,         dot: 'bg-amber-500',   pill: 'bg-amber-50 text-amber-700 border-amber-200' },
  interview_scheduled: { Icon: Calendar,     dot: 'bg-violet-500',  pill: 'bg-violet-50 text-violet-700 border-violet-200' },
  email_sent:          { Icon: Mail,         dot: 'bg-fuchsia-500', pill: 'bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200' },
  offer_sent:          { Icon: CheckCircle2, dot: 'bg-emerald-500', pill: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  rejected:            { Icon: XCircle,      dot: 'bg-red-400',     pill: 'bg-red-50 text-red-600 border-red-200' },
  rejection_email:     { Icon: Mail,         dot: 'bg-rose-500',    pill: 'bg-rose-50 text-rose-700 border-rose-200' },
  rejection_email_bulk: { Icon: Mail,         dot: 'bg-rose-600',    pill: 'bg-rose-100 text-rose-800 border-rose-300' },
};

// ─── Relative time helper ─────────────────────────────────────
function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1)    return 'just now';
  if (diffMins < 60)   return `${diffMins}m ago`;
  const diffHrs = Math.floor(diffMins / 60);
  if (diffHrs < 24)    return `${diffHrs}h ago`;
  const diffDays = Math.floor(diffHrs / 24);
  if (diffDays < 7)    return `${diffDays}d ago`;
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// ─── Event type label ─────────────────────────────────────────
const TYPE_LABELS: Record<string, string> = {
  resume_uploaded:     'Parsed',
  scoring:             'Scored',
  shortlisted:         'Shortlisted',
  interview_scheduled: 'Scheduled',
  email_sent:          'Email',
  offer_sent:          'Offer',
  rejected:            'Rejected',
  rejection_email:     'Email',
  rejection_email_bulk: 'Bulk Email',
};

export default function ActivityFeed() {
  const navigate = useNavigate();
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchFeed = async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      else setRefreshing(true);
      const res = await axios.get('/api/activity-feed');
      setEvents(res.data);
    } catch (err) {
      console.error('Activity feed fetch failed', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchFeed();
    // Poll every 10 seconds for real-time feel
    const interval = setInterval(() => fetchFeed(true), 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <section className="mb-10">
      {/* Section header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2.5">
          <div className="flex items-center gap-2 bg-slate-900 text-white text-[11px] font-black uppercase tracking-widest px-3 py-1.5 rounded-full">
            <Activity className="w-3.5 h-3.5" />
            Live Activity
          </div>
          {/* Pulsing live dot */}
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </span>
        </div>
        <button
          onClick={() => fetchFeed(true)}
          disabled={refreshing}
          className="text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-50"
          title="Refresh"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading ? (
        <div className="bg-white border border-gray-100 rounded-3xl p-8">
          <div className="flex flex-col gap-4">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="flex gap-3 animate-pulse">
                <div className="w-8 h-8 bg-gray-100 rounded-xl shrink-0" />
                <div className="flex-1 space-y-1.5 py-1">
                  <div className="h-3 bg-gray-100 rounded w-2/3" />
                  <div className="h-2.5 bg-gray-100 rounded w-1/2" />
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : events.length === 0 ? (
        <div className="bg-white border border-dashed border-gray-200 rounded-3xl p-12 text-center">
          <Activity className="w-8 h-8 text-gray-200 mx-auto mb-3" />
          <p className="text-sm font-semibold text-gray-400">No activity yet</p>
          <p className="text-xs text-gray-300 mt-1">Events will appear here as candidates apply and move through the pipeline.</p>
        </div>
      ) : (
        <div className="bg-white border border-gray-100 rounded-3xl shadow-sm overflow-hidden">
          <div className="divide-y divide-gray-50">
            <AnimatePresence initial={false}>
              {events.map((event, idx) => {
                const cfg = EVENT_CONFIG[event.type] ?? EVENT_CONFIG.resume_uploaded;
                const { Icon } = cfg;

                return (
                  <motion.div
                    key={`${event.type}-${event.timestamp}-${event.candidate_name}`}
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ delay: idx * 0.03 }}
                    onClick={() => navigate(`/dashboard/jobs/${event.job_id}`)}
                    className="group flex items-center gap-4 px-5 py-4 hover:bg-gray-50 cursor-pointer transition-colors"
                  >
                    {/* Timeline: icon + line */}
                    <div className="relative shrink-0 flex flex-col items-center">
                      <div className={`w-8 h-8 rounded-xl flex items-center justify-center ${cfg.pill} border`}>
                        <Icon className="w-4 h-4" />
                      </div>
                      {idx < events.length - 1 && (
                        <div className="absolute top-8 left-1/2 -translate-x-1/2 w-px h-full bg-gray-100 mt-1" />
                      )}
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-sm font-bold text-gray-900 leading-tight">{event.title}</p>
                        <span className={`text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full border ${cfg.pill}`}>
                          {TYPE_LABELS[event.type]}
                        </span>
                      </div>
                      <p className="text-xs text-gray-400 truncate mt-0.5">{event.description}</p>
                    </div>

                    {/* Timestamp */}
                    <time className="shrink-0 text-[11px] text-gray-300 font-medium whitespace-nowrap">
                      {relativeTime(event.timestamp)}
                    </time>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          </div>

          {/* Footer */}
          {events.length >= 30 && (
            <div className="px-5 py-3 bg-gray-50 border-t border-gray-100 text-center">
              <p className="text-xs text-gray-400">Showing the 30 most recent events</p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
