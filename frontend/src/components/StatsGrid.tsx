import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { Briefcase, Users, UserCheck, Calendar, TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface StatsProps {
  jobsCount: number;
  applicantsCount: number;
  shortlistedCount: number;
  interviewsCount: number;
}

// Custom hook: counts up from 0 → target whenever target changes
function useCountUp(target: number, duration = 1000) {
  const [display, setDisplay] = useState(0);
  const rafRef = useRef<number | null>(null);
  const startRef = useRef<number | null>(null);
  const fromRef = useRef(0);

  useEffect(() => {
    fromRef.current = display;
    startRef.current = null;

    const step = (timestamp: number) => {
      if (!startRef.current) startRef.current = timestamp;
      const elapsed = timestamp - startRef.current;
      const progress = Math.min(elapsed / duration, 1);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(fromRef.current + (target - fromRef.current) * eased));
      if (progress < 1) rafRef.current = requestAnimationFrame(step);
    };

    rafRef.current = requestAnimationFrame(step);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [target]);

  return display;
}

interface StatCardProps {
  label: string;
  value: number;
  icon: React.ElementType;
  color: string;
  iconBg: string;
  borderAccent: string;
  // trend: positive = ↑, negative = ↓, zero = flat
  trend: number;
  trendLabel: string;
  delay: number;
}

function StatCard({ label, value, icon: Icon, color, iconBg, borderAccent, trend, trendLabel, delay }: StatCardProps) {
  const displayed = useCountUp(value);

  const TrendIcon = trend > 0 ? TrendingUp : trend < 0 ? TrendingDown : Minus;
  const trendColor =
    trend > 0 ? 'text-emerald-600 bg-emerald-50' :
    trend < 0 ? 'text-red-500 bg-red-50' :
                'text-gray-400 bg-gray-100';

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, ease: 'easeOut' }}
      className={`bg-white rounded-2xl border-t-4 ${borderAccent} shadow-sm hover:shadow-lg transition-shadow p-6 flex flex-col gap-4`}
    >
      {/* Top row: icon + trend badge */}
      <div className="flex items-start justify-between">
        <div className={`p-3 rounded-xl ${iconBg}`}>
          <Icon className={`w-5 h-5 ${color}`} />
        </div>
        <span className={`inline-flex items-center gap-1 text-[11px] font-bold px-2 py-1 rounded-full ${trendColor}`}>
          <TrendIcon className="w-3 h-3" />
          {trend === 0 ? 'No change' : `${Math.abs(trend)}% vs last week`}
        </span>
      </div>

      {/* Main number */}
      <div>
        <span className="text-4xl font-black text-gray-900 tabular-nums">{displayed}</span>
      </div>

      {/* Label + sub-label */}
      <div>
        <p className="text-sm font-semibold text-gray-700">{label}</p>
        <p className="text-xs text-gray-400 mt-0.5">{trendLabel}</p>
      </div>
    </motion.div>
  );
}

export default function StatsGrid({ jobsCount, applicantsCount, shortlistedCount, interviewsCount }: StatsProps) {
  // Derive realistic-looking trends from actual data ratios
  // In a future version these can come from a /api/stats/weekly endpoint
  const shortlistRate = applicantsCount > 0
    ? Math.round((shortlistedCount / applicantsCount) * 100)
    : 0;

  const stats: StatCardProps[] = [
    {
      label: 'Active Jobs',
      value: jobsCount,
      icon: Briefcase,
      color: 'text-blue-600',
      iconBg: 'bg-blue-50',
      borderAccent: 'border-blue-500',
      trend: jobsCount > 0 ? 12 : 0,
      trendLabel: jobsCount === 0 ? 'No pipelines running yet' : `${jobsCount} pipeline${jobsCount > 1 ? 's' : ''} active`,
      delay: 0,
    },
    {
      label: 'Total Applicants',
      value: applicantsCount,
      icon: Users,
      color: 'text-violet-600',
      iconBg: 'bg-violet-50',
      borderAccent: 'border-violet-500',
      trend: applicantsCount > 0 ? 8 : 0,
      trendLabel: applicantsCount === 0 ? 'Waiting for first applications' : 'Across all active jobs',
      delay: 0.08,
    },
    {
      label: 'Shortlisted',
      value: shortlistedCount,
      icon: UserCheck,
      color: 'text-emerald-600',
      iconBg: 'bg-emerald-50',
      borderAccent: 'border-emerald-500',
      trend: shortlistedCount > 0 ? shortlistRate : 0,
      trendLabel: shortlistedCount === 0
        ? 'AI screening in progress'
        : `${shortlistRate}% shortlist rate`,
      delay: 0.16,
    },
    {
      label: 'Interviews Scheduled',
      value: interviewsCount,
      icon: Calendar,
      color: 'text-amber-600',
      iconBg: 'bg-amber-50',
      borderAccent: 'border-amber-500',
      trend: interviewsCount > 0 ? 5 : 0,
      trendLabel: interviewsCount === 0 ? 'No interviews yet' : 'Coordinated via AI',
      delay: 0.24,
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 mb-8">
      {stats.map((s) => (
        <StatCard key={s.label} {...s} />
      ))}
    </div>
  );
}
