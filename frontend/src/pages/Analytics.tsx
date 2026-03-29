import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { BarChart3, Users, Star, TrendingUp, UserCheck, Clock, AlertCircle, ChevronRight, Target } from 'lucide-react';
import { api } from '../services/api';

interface CandidateRating {
  name: string;
  rating: number;
}

interface StagePassRate {
  stage: string;
  pass_rate: number;
  total: number;
}

interface InterviewerMetric {
  name: string;
  avg_rating_given: number;
  interview_count: number;
}

interface AnalyticsData {
  candidate_ratings: CandidateRating[];
  stage_pass_rates: StagePassRate[];
  interviewer_metrics: InterviewerMetric[];
}

export default function Analytics() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchAnalytics = async () => {
      try {
        const res = await api.getFeedbackAnalytics();
        setData(res);
      } catch (err: any) {
        console.error('Failed to fetch analytics:', err);
        setError('Could not load analytics data. Please try again later.');
      } finally {
        setLoading(false);
      }
    };

    fetchAnalytics();
  }, []);

  if (loading) {
    return (
      <div className="h-[60vh] flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Clock className="w-10 h-10 text-blue-600 animate-spin" />
          <p className="text-gray-500 font-bold uppercase tracking-widest text-xs">Generating Insights...</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="h-[60vh] flex items-center justify-center p-8">
        <div className="bg-red-50 border border-red-100 p-8 rounded-[2rem] text-center max-w-md">
          <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <h3 className="text-xl font-black text-gray-900 mb-2">Analytics Offline</h3>
          <p className="text-red-600 font-medium mb-6">{error || 'Something went wrong'}</p>
          <button onClick={() => window.location.reload()} className="px-6 py-3 bg-white border border-red-200 text-red-600 rounded-xl font-bold hover:bg-red-100 transition-colors">Retry</button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 pb-20">
      <header className="mb-12">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2 bg-blue-600 rounded-lg">
            <BarChart3 className="w-5 h-5 text-white" />
          </div>
          <span className="text-blue-600 font-black uppercase tracking-widest text-xs">Intelligence Dashboard</span>
        </div>
        <h1 className="text-5xl font-black text-gray-900 tracking-tight">Hiring Analytics</h1>
        <p className="text-gray-500 mt-3 text-lg font-medium">Data-driven insights into your recruitment pipeline and interviewer performance.</p>
      </header>

      {/* Primary Stats */}
      <div className="grid md:grid-cols-3 gap-8 mb-12">
        <StatCard 
          icon={<Users className="w-6 h-6 text-blue-600" />} 
          label="Interviews Conducted" 
          value={data.interviewer_metrics.reduce((acc, curr) => acc + curr.interview_count, 0)} 
          sub="Total evaluations submitted"
        />
        <StatCard 
          icon={<Target className="w-6 h-6 text-emerald-600" />} 
          label="Avg. Pass Rate" 
          value={`${Math.round(data.stage_pass_rates.reduce((acc, curr) => acc + curr.pass_rate, 0) / (data.stage_pass_rates.length || 1))}%`} 
          sub="Across all active stages"
        />
        <StatCard 
          icon={<Star className="w-6 h-6 text-amber-500" />} 
          label="Top Candidate Score" 
          value={data.candidate_ratings[0]?.rating.toFixed(1) || '0.0'} 
          sub="Highest average evaluation"
        />
      </div>

      <div className="grid lg:grid-cols-2 gap-8 mb-12">
        {/* Stage Pass Rates */}
        <motion.section 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-white rounded-[2.5rem] border border-gray-100 shadow-xl shadow-gray-100/50 p-10"
        >
          <div className="flex items-center justify-between mb-10">
            <h2 className="text-2xl font-black text-gray-900 flex items-center gap-3">
              <TrendingUp className="w-6 h-6 text-emerald-500" /> Pipeline Efficiency
            </h2>
            <span className="text-[10px] font-black uppercase tracking-widest bg-emerald-50 text-emerald-600 px-3 py-1 rounded-full border border-emerald-100">Pass Rate %</span>
          </div>
          
          <div className="space-y-8">
            {data.stage_pass_rates.map((stage, idx) => (
              <div key={idx} className="group">
                <div className="flex justify-between items-end mb-3">
                  <div className="flex flex-col">
                    <span className="text-sm font-black text-gray-900 group-hover:text-blue-600 transition-colors uppercase tracking-tight">{stage.stage}</span>
                    <span className="text-[10px] text-gray-400 font-bold">{stage.total} total evaluations</span>
                  </div>
                  <span className="text-lg font-black text-gray-900">{Math.round(stage.pass_rate)}%</span>
                </div>
                <div className="h-3 w-full bg-gray-50 rounded-full overflow-hidden border border-gray-100">
                  <motion.div 
                    initial={{ width: 0 }}
                    animate={{ width: `${stage.pass_rate}%` }}
                    transition={{ duration: 1, delay: idx * 0.1, ease: "easeOut" }}
                    className={`h-full rounded-full ${stage.pass_rate > 70 ? 'bg-emerald-500' : stage.pass_rate > 40 ? 'bg-blue-500' : 'bg-amber-500'}`}
                  />
                </div>
              </div>
            ))}
          </div>
        </motion.section>

        {/* Top Candidates */}
        <motion.section 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-white rounded-[2.5rem] border border-gray-100 shadow-xl shadow-gray-100/50 p-10"
        >
          <div className="flex items-center justify-between mb-10">
            <h2 className="text-2xl font-black text-gray-900 flex items-center gap-3">
              <UserCheck className="w-6 h-6 text-blue-500" /> Top Ranked Talent
            </h2>
            <span className="text-[10px] font-black uppercase tracking-widest bg-blue-50 text-blue-600 px-3 py-1 rounded-full border border-blue-100">Avg Rating</span>
          </div>

          <div className="space-y-4">
            {data.candidate_ratings.map((cand, idx) => (
              <div key={idx} className="flex items-center justify-between p-4 rounded-2xl hover:bg-gray-50 transition-all border border-transparent hover:border-gray-100">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-xl bg-slate-900 flex items-center justify-center font-black text-white text-sm">
                    {idx + 1}
                  </div>
                  <span className="font-bold text-gray-900">{cand.name}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Star className="w-4 h-4 text-amber-400 fill-current" />
                  <span className="font-black text-gray-900">{cand.rating.toFixed(1)}</span>
                </div>
              </div>
            ))}
            {data.candidate_ratings.length === 0 && (
              <div className="text-center py-10">
                <p className="text-gray-400 font-medium italic">No candidate data available yet.</p>
              </div>
            )}
          </div>
        </motion.section>
      </div>

      {/* Interviewer Performance Table */}
      <motion.section 
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.2 }}
        className="bg-slate-900 rounded-[3rem] p-12 text-white overflow-hidden relative"
      >
        <div className="absolute top-0 right-0 w-96 h-96 bg-blue-600/10 blur-[100px] rounded-full -mr-48 -mt-48" />
        
        <div className="relative z-10">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-12">
            <div>
              <h2 className="text-3xl font-black tracking-tight">Interviewer Performance</h2>
              <p className="text-slate-400 mt-2 font-medium">Tracking evaluation volume and objectivity across the team.</p>
            </div>
            <button className="bg-white/10 hover:bg-white/20 transition-all border border-white/10 px-6 py-3 rounded-xl font-bold text-sm flex items-center gap-2">
              Export Full Report <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-slate-500 text-[10px] font-black uppercase tracking-[0.2em] border-b border-white/5">
                  <th className="pb-6">Interviewer Name</th>
                  <th className="pb-6">Total Interviews</th>
                  <th className="pb-6">Average Rating Given</th>
                  <th className="pb-6">Leniency Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {data.interviewer_metrics.map((int, idx) => (
                  <tr key={idx} className="group hover:bg-white/5 transition-colors">
                    <td className="py-6 font-bold text-lg">{int.name}</td>
                    <td className="py-6">
                      <div className="flex items-center gap-3">
                        <span className="font-black text-xl">{int.interview_count}</span>
                        <div className="h-1 w-12 bg-white/10 rounded-full overflow-hidden">
                          <div className="h-full bg-blue-500 rounded-full" style={{ width: `${Math.min(int.interview_count * 5, 100)}%` }} />
                        </div>
                      </div>
                    </td>
                    <td className="py-6">
                      <div className="flex items-center gap-2">
                        <Star className="w-4 h-4 text-amber-400 fill-current" />
                        <span className="font-black text-lg">{int.avg_rating_given.toFixed(1)}</span>
                      </div>
                    </td>
                    <td className="py-6">
                      <span className={`px-4 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest border ${
                        int.avg_rating_given > 4 ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' : 
                        int.avg_rating_given < 2 ? 'bg-red-500/10 text-red-400 border-red-500/20' : 
                        'bg-blue-500/10 text-blue-400 border-blue-500/20'
                      }`}>
                        {int.avg_rating_given > 4 ? 'High Leniency' : int.avg_rating_given < 2 ? 'High Severity' : 'Balanced'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </motion.section>
    </div>
  );
}

function StatCard({ icon, label, value, sub }: { icon: any, label: string, value: string | number, sub: string }) {
  return (
    <motion.div 
      whileHover={{ y: -5 }}
      className="bg-white p-8 rounded-[2rem] border border-gray-100 shadow-lg shadow-gray-100/50 flex flex-col"
    >
      <div className="w-12 h-12 rounded-2xl bg-gray-50 flex items-center justify-center mb-6">
        {icon}
      </div>
      <span className="text-gray-400 text-[10px] font-black uppercase tracking-widest mb-1">{label}</span>
      <span className="text-4xl font-black text-gray-900 mb-2">{value}</span>
      <span className="text-xs font-bold text-gray-400">{sub}</span>
    </motion.div>
  );
}
