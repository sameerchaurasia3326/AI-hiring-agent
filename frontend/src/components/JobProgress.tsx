import { CheckCircle2, Circle, Loader2, XCircle, AlertCircle } from 'lucide-react';

// ─── Stage definitions using exact pipeline_state enum values ───────────────
const STAGES = [
  { id: 'jd',          label: 'JD Generated',    states: ['JD_DRAFT', 'JD_APPROVAL_PENDING', 'JD_APPROVED', 'JOB_POSTED'] },
  { id: 'screening',   label: 'Screening',        states: ['WAITING_FOR_APPLICATIONS', 'SCREENING'] },
  { id: 'shortlist',   label: 'Shortlisting',     states: ['HR_REVIEW_PENDING'] },
  { id: 'interview',   label: 'Interview',        states: ['INTERVIEW_SCHEDULED'] },
  { id: 'final',       label: 'Final Decision',   states: ['OFFER_SENT', 'CLOSED'] },
];

function getStageIndex(pipelineState: string): number {
  const stateMap: Record<string, number> = {
    'JD_DRAFT': 0,
    'JD_APPROVAL_PENDING': 0,
    'JD_APPROVED': 0,
    'JOB_POSTED': 0,
    'WAITING_FOR_APPLICATIONS': 1,
    'SCREENING': 1,
    'HR_REVIEW_PENDING': 2,
    'INTERVIEW_SCHEDULED': 3,
    'OFFER_SENT': 4,
    'CLOSED': 4,
  };
  return stateMap[pipelineState] ?? 0;
}

export default function JobProgress({
  pipelineState,
  status = '',
  isCancelled = false,
  compact = false,
}: {
  pipelineState: string;
  status?: string;
  isCancelled?: boolean;
  compact?: boolean;
}) {
  const isError = pipelineState === 'FAILED' || pipelineState === 'ESCALATED';
  const currentIdx = isError ? 0 : getStageIndex(pipelineState);

  return (
    <div className={`w-full ${compact ? 'py-1' : 'py-5 px-2'}`}>
      <div className="flex items-center justify-between">
        {STAGES.map((stage, idx) => {
          // Stages BEFORE current: completed (blue check)
          const isCompleted = idx < currentIdx;
          const isAwaitingHR = ((idx === 0 && pipelineState === 'JD_APPROVAL_PENDING') ||
                               (idx === 2 && pipelineState === 'HR_REVIEW_PENDING')) && status !== 'processing' && status !== 'PROCESSING';
          
          const isCurr = idx === currentIdx && !isCompleted;
          const isPending = idx > currentIdx;
          const isCancelledHere = isCancelled && isCurr;

          return (
            <div key={stage.id} className="flex flex-col items-center relative z-10 flex-1">
              {/* Connector line */}
              {idx !== 0 && (
                <div
                  className={`absolute ${compact ? 'top-[10px]' : 'top-[16px]'} left-[-50%] w-full h-[2px] z-[-1] transition-colors duration-500 
                    ${idx <= currentIdx ? 'bg-blue-500' : 'bg-gray-200'}`}
                />
              )}

              {/* Icon bubble */}
              <div className={`
                flex items-center justify-center rounded-full shadow-sm transition-all duration-300
                ${compact ? 'w-5 h-5' : 'w-8 h-8'}
                ${isCompleted ? 'bg-blue-600 text-white' : ''}
                ${isCurr && !isCancelledHere && !isError && !isAwaitingHR ? 'bg-white text-blue-600 border-2 border-blue-600 shadow-[0_0_12px_rgba(37,99,235,0.25)]' : ''}
                ${isAwaitingHR ? 'bg-orange-50 text-orange-600 border-2 border-orange-400 shadow-[0_0_8px_rgba(249,115,22,0.15)]' : ''}
                ${isCancelledHere ? 'bg-red-50 text-red-500 border-2 border-red-400' : ''}
                ${isError && isCurr ? 'bg-red-50 text-red-500 border-2 border-red-400' : ''}
                ${isPending && !isAwaitingHR ? 'bg-white border-2 border-gray-200 text-gray-300' : ''}
              `}>
                {isCompleted
                  ? <CheckCircle2 className={compact ? 'w-3 h-3' : 'w-5 h-5'} />
                  : isCancelledHere || (isError && isCurr)
                  ? <XCircle className={compact ? 'w-3 h-3' : 'w-4 h-4'} />
                  : isAwaitingHR
                  ? <AlertCircle className={`${compact ? 'w-3 h-3' : 'w-4 h-4'} animate-pulse`} />
                  : isCurr
                  ? (status?.toUpperCase() === 'PROCESSING' ? <Loader2 className={`${compact ? 'w-3 h-3' : 'w-4 h-4'} animate-spin`} /> : <Circle className={`${compact ? 'w-2 h-2' : 'w-3 h-3'} fill-current`} />)
                  : <Circle className={`${compact ? 'w-2 h-2' : 'w-3 h-3'} fill-current opacity-30`} />
                }
              </div>

              {!compact && (
                <span className={`text-[10px] font-bold uppercase tracking-wider text-center mt-2
                  ${isCompleted ? 'text-blue-700' : ''}
                  ${isCurr && !isCancelledHere && !isError && !isAwaitingHR ? 'text-slate-900' : ''}
                  ${isAwaitingHR ? 'text-orange-700' : ''}
                  ${isCancelledHere || (isError && isCurr) ? 'text-red-500' : ''}
                  ${isPending && !isAwaitingHR ? 'text-gray-400' : ''}
                `}>
                  {stage.label}
                  {isAwaitingHR && <span className="block text-[9px] text-orange-500 font-bold normal-case">Action Required</span>}
                  {isCancelledHere && <span className="block text-[9px] text-red-400 font-normal normal-case">Cancelled here</span>}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

