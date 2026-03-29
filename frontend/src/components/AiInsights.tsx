import { motion } from 'framer-motion';
import { Sparkles, TrendingUp, AlertTriangle, Lightbulb, ArrowRight, BrainCircuit } from 'lucide-react';

interface Insight {
  id: string;
  type: 'warning' | 'opportunity' | 'suggestion';
  title: string;
  description: string;
  action_text?: string;
  impact: 'high' | 'medium' | 'low';
}

const INSIGHTS: Insight[] = [
  {
    id: 'jd-engagement',
    type: 'warning',
    title: 'Low JD Engagement',
    description: 'The Frontend Engineer role has a 40% drop-off rate. Consider simplifying the requirements section.',
    action_text: 'Optimize with AI',
    impact: 'high',
  },
  {
    id: 'skill-gap',
    type: 'opportunity',
    title: 'Candidates lack System Design skills',
    description: 'Only 12% of applicants for the Backend lead passed the system design screening. Should we source actively?',
    action_text: 'Source on LinkedIn',
    impact: 'high',
  },
  {
    id: 'salary-comp',
    type: 'suggestion',
    title: 'Salary below market average',
    description: 'Top candidates for Product Manager are dropping out at the offer stage. Market average is 15% higher.',
    action_text: 'View Benchmarks',
    impact: 'medium',
  }
];

const IMPACT_COLORS = {
  high: 'bg-rose-100 text-rose-700',
  medium: 'bg-amber-100 text-amber-700',
  low: 'bg-blue-100 text-blue-700',
};

const TYPE_ICONS = {
  warning: <AlertTriangle className="w-5 h-5 text-rose-500" />,
  opportunity: <TrendingUp className="w-5 h-5 text-emerald-500" />,
  suggestion: <Lightbulb className="w-5 h-5 text-amber-500" />,
};

export default function AiInsights() {
  return (
    <section className="mb-10">
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <div className="bg-gradient-to-r from-blue-600 to-indigo-600 p-2 rounded-xl text-white shadow-lg shadow-blue-500/20">
            <BrainCircuit className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-gray-900 tracking-tight flex items-center gap-2">
              AI Insights <Sparkles className="w-5 h-5 text-amber-400" />
            </h2>
            <p className="text-sm text-gray-400 mt-0.5">Platform intelligence and hiring recommendations</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {INSIGHTS.map((insight, idx) => (
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: idx * 0.1 }}
            key={insight.id}
            className="group relative bg-white border border-gray-100 rounded-3xl p-6 shadow-sm hover:shadow-xl hover:border-blue-100 hover:-translate-y-1 transition-all"
          >
            {/* Background glow effect on hover */}
            <div className="absolute inset-0 bg-gradient-to-br from-blue-50/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity rounded-3xl pointer-events-none" />

            <div className="relative">
              <div className="flex items-start justify-between mb-4">
                <div className="p-3 bg-gray-50 rounded-2xl group-hover:bg-white group-hover:shadow-sm transition-all">
                  {TYPE_ICONS[insight.type]}
                </div>
                <span className={`px-2.5 py-1 rounded-full text-[10px] font-black uppercase tracking-widest ${IMPACT_COLORS[insight.impact]}`}>
                  {insight.impact} priority
                </span>
              </div>

              <h3 className="text-lg font-bold text-gray-900 mb-2 leading-tight group-hover:text-blue-700 transition-colors">
                {insight.title}
              </h3>
              <p className="text-sm text-gray-500 mb-6 leading-relaxed">
                {insight.description}
              </p>

              {insight.action_text && (
                <button className="flex items-center gap-2 text-sm font-bold text-blue-600 group-hover:text-blue-700 transition-colors">
                  {insight.action_text}
                  <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
                </button>
              )}
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
