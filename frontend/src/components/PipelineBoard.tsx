import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { UserCheck, Calendar, Search, CheckCircle2, XCircle, Star, ArrowUpRight } from 'lucide-react';

interface CandidateCard {
  application_id: string;
  candidate_id: string | null;
  name: string;
  email: string | null;
  job_id: string;
  job_title: string;
  ai_score: number | null;
  is_shortlisted: boolean;
  hr_selected: boolean | null;
  has_interview: boolean;
  meeting_link: string | null;
  offer_sent: boolean;
  rejected: boolean;
}

interface BoardData {
  screening: CandidateCard[];
  hr_review: CandidateCard[];
  interview: CandidateCard[];
  final: CandidateCard[];
}

const COLUMNS = [
  {
    key: 'screening' as const,
    label: 'Screening',
    icon: Search,
    color: 'text-blue-600',
    bg: 'bg-blue-50',
    border: 'border-blue-200',
    headerBg: 'bg-blue-600',
    dot: 'bg-blue-500',
  },
  {
    key: 'hr_review' as const,
    label: 'HR Review',
    icon: UserCheck,
    color: 'text-amber-600',
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    headerBg: 'bg-amber-500',
    dot: 'bg-amber-500',
  },
  {
    key: 'interview' as const,
    label: 'Interview',
    icon: Calendar,
    color: 'text-violet-600',
    bg: 'bg-violet-50',
    border: 'border-violet-200',
    headerBg: 'bg-violet-600',
    dot: 'bg-violet-500',
  },
  {
    key: 'final' as const,
    label: 'Final Decision',
    icon: CheckCircle2,
    color: 'text-emerald-600',
    bg: 'bg-emerald-50',
    border: 'border-emerald-200',
    headerBg: 'bg-emerald-600',
    dot: 'bg-emerald-500',
  },
];

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return <span className="text-[10px] text-gray-400 font-medium italic">Scoring…</span>;
  const color =
    score >= 80 ? 'bg-emerald-100 text-emerald-700' :
    score >= 60 ? 'bg-amber-100 text-amber-700' :
                  'bg-red-100 text-red-600';
  return (
    <span className={`inline-flex items-center gap-0.5 text-[11px] font-black px-2 py-0.5 rounded-full ${color}`}>
      <Star className="w-2.5 h-2.5 fill-current" />
      {score}
    </span>
  );
}

function CandidateCardItem({ card, onNavigate }: { card: CandidateCard; onNavigate: (id: string) => void }) {
  const initials = card.name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="group bg-white border border-gray-100 rounded-2xl p-4 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all cursor-pointer"
      onClick={() => onNavigate(card.job_id)}
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        {/* Avatar */}
        <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shrink-0">
          <span className="text-[10px] font-black text-white">{initials}</span>
        </div>
        <ScoreBadge score={card.ai_score} />
      </div>

      <p className="text-sm font-bold text-gray-900 leading-snug mb-0.5 truncate">{card.name}</p>
      <p className="text-[11px] text-gray-400 truncate mb-3">{card.job_title}</p>

      {/* Status indicators */}
      <div className="flex items-center gap-2 flex-wrap">
        {card.offer_sent && (
          <span className="inline-flex items-center gap-1 bg-emerald-50 text-emerald-700 text-[10px] font-bold px-2 py-0.5 rounded-full border border-emerald-200">
            <CheckCircle2 className="w-2.5 h-2.5" /> Offer Sent
          </span>
        )}
        {card.rejected && (
          <span className="inline-flex items-center gap-1 bg-red-50 text-red-600 text-[10px] font-bold px-2 py-0.5 rounded-full border border-red-200">
            <XCircle className="w-2.5 h-2.5" /> Rejected
          </span>
        )}
        {card.has_interview && !card.offer_sent && !card.rejected && (
          <span className="inline-flex items-center gap-1 bg-violet-50 text-violet-700 text-[10px] font-bold px-2 py-0.5 rounded-full border border-violet-200">
            <Calendar className="w-2.5 h-2.5" /> Scheduled
          </span>
        )}
      </div>

      {/* Navigate arrow */}
      <div className="mt-3 flex justify-end opacity-0 group-hover:opacity-100 transition-opacity">
        <ArrowUpRight className="w-3.5 h-3.5 text-blue-500" />
      </div>
    </motion.div>
  );
}

export default function PipelineBoard() {
  const navigate = useNavigate();
  const [board, setBoard] = useState<BoardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchBoard = async () => {
      try {
        const data = await axios.get('/api/pipeline-board');
        setBoard(data.data);
      } catch (err) {
        console.error('Pipeline board fetch failed', err);
      } finally {
        setLoading(false);
      }
    };
    fetchBoard();
    const interval = setInterval(fetchBoard, 15000);
    return () => clearInterval(interval);
  }, []);

  const totalCandidates = board
    ? Object.values(board).reduce((acc, col) => acc + col.length, 0)
    : 0;

  return (
    <section className="mb-10">
      {/* Section header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 tracking-tight">Pipeline Board</h2>
          {!loading && (
            <p className="text-sm text-gray-400 mt-0.5">
              {totalCandidates} candidate{totalCandidates !== 1 ? 's' : ''} across all active jobs
            </p>
          )}
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="flex flex-col">
              <div className="h-[46px] bg-gray-100 rounded-2xl mb-3 animate-pulse border border-gray-100/50" />
              <div className="flex flex-col gap-2">
                {[1, 2].map(j => (
                  <div key={j} className="h-[120px] bg-gray-50 rounded-2xl animate-pulse" />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : totalCandidates === 0 ? (
        <div className="bg-white border border-dashed border-gray-200 rounded-3xl p-14 text-center">
          <div className="w-16 h-16 bg-gray-50 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <Search className="w-8 h-8 text-gray-300" />
          </div>
          <h3 className="text-lg font-bold text-gray-700 mb-1">No candidates in the pipeline yet</h3>
          <p className="text-sm text-gray-400">Once candidates apply and AI scoring begins, they'll appear here across stages.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {COLUMNS.map((col) => {
            const cards = board![col.key];
            return (
              <div key={col.key} className="flex flex-col">
                {/* Column header */}
                <div className={`flex items-center justify-between px-4 py-2.5 rounded-2xl mb-3 ${col.bg} border ${col.border}`}>
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${col.dot}`} />
                    <span className={`text-xs font-black uppercase tracking-widest ${col.color}`}>{col.label}</span>
                  </div>
                  <span className={`text-xs font-black ${col.color} bg-white px-2 py-0.5 rounded-full border ${col.border}`}>
                    {cards.length}
                  </span>
                </div>

                {/* Cards */}
                <div className="flex flex-col gap-2 min-h-[120px]">
                  {cards.length === 0 ? (
                    <div className="flex-1 flex items-center justify-center border-2 border-dashed border-gray-100 rounded-2xl py-8">
                      <p className="text-xs text-gray-300 font-medium">No candidates</p>
                    </div>
                  ) : (
                    cards.map((card, idx) => (
                      <motion.div key={card.application_id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: idx * 0.04 }}>
                      <CandidateCardItem card={card} onNavigate={(id) => navigate(`/dashboard/jobs/${id}`)} />
                      </motion.div>
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
