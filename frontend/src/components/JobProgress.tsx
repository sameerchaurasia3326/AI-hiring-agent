import { CheckCircle2, Circle, Loader2, XCircle } from 'lucide-react';

// ─── Stage definitions using exact pipeline_state enum values ───────────────
const STAGES = [
  { id: 'jd',          label: 'JD Generated',    states: ['JD_DRAFT', 'JD_APPROVAL_PENDING', 'JD_APPROVED', 'JOB_POSTED'] },
  { id: 'screening',   label: 'Screening',        states: ['WAITING_FOR_APPLICATIONS', 'SCREENING'] },
  { id: 'shortlist',   label: 'Shortlisting',     states: ['HR_REVIEW_PENDING'] },
  { id: 'interview',   label: 'Interview',        states: ['INTERVIEW_SCHEDULED'] },
  { id: 'final',       label: 'Final Decision',   states: ['OFFER_SENT', 'CLOSED'] },
];

function getStageIndex(pipelineState: string): number {
  for (let i = 0; i < STAGES.length; i++) {
    if (STAGES[i].states.includes(pipelineState)) return i;
  }
  return 0;
}

export default function JobProgress({
  pipelineState,
  isCancelled = false,
  compact = false,
}: {
  pipelineState: string;
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
          // Current stage: if cancelled → show red X, if error → red alert
          // SPECIAL: If awaiting approval, we show the stage icon as "Done" (check) even if it's technically the current status mapping.
          const isCompleted = idx < currentIdx || (idx === 0 && pipelineState === 'JD_APPROVAL_PENDING');
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
                ${isCurr && !isCancelledHere && !isError ? 'bg-white text-blue-600 border-2 border-blue-600 shadow-[0_0_12px_rgba(37,99,235,0.25)]' : ''}
                ${isCancelledHere ? 'bg-red-50 text-red-500 border-2 border-red-400' : ''}
                ${isError && isCurr ? 'bg-red-50 text-red-500 border-2 border-red-400' : ''}
                ${isPending ? 'bg-white border-2 border-gray-200 text-gray-300' : ''}
              `}>
                {isCompleted
                  ? <CheckCircle2 className={compact ? 'w-3 h-3' : 'w-5 h-5'} />
                  : isCancelledHere || (isError && isCurr)
                  ? <XCircle className={compact ? 'w-3 h-3' : 'w-4 h-4'} />
                  : isCurr
                  ? <Loader2 className={`${compact ? 'w-3 h-3' : 'w-4 h-4'} animate-spin`} />
                  : <Circle className={`${compact ? 'w-2 h-2' : 'w-3 h-3'} fill-current opacity-30`} />
                }
              </div>

              {!compact && (
                <span className={`text-[10px] font-bold uppercase tracking-wider text-center mt-2
                  ${isCompleted ? 'text-blue-700' : ''}
                  ${isCurr && !isCancelledHere && !isError ? 'text-slate-900' : ''}
                  ${isCancelledHere || (isError && isCurr) ? 'text-red-500' : ''}
                  ${isPending ? 'text-gray-400' : ''}
                `}>
                  {stage.label}
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
