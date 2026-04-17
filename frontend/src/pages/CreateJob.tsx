import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Briefcase, ArrowLeft, Loader2, Sparkles, Plus, Trash2, Check, Settings, MessageSquare, ClipboardList, MapPin, X, Send } from 'lucide-react';
import { api } from '../services/api';

export default function CreateJob() {
  const navigate = useNavigate();

  // Left side form state
  const [formData, setFormData] = useState({
    job_title: '',
    department: '',
    location: '',
    employment_type: 'Full-Time',
    experience_required: '',
    salary_range: '',
    joining_requirement: 'Immediate',
    technical_test_type: 'None',
    technical_test_link: '',
  });

  // JD Template State
  const [templates, setTemplates] = useState<{key: string, name: string, description: string}[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState('startup');

  const [skills, setSkills] = useState<string[]>([]);
  const [skillInput, setSkillInput] = useState('');

  const [screeningQuestions, setScreeningQuestions] = useState<string[]>([]);
  const [questionInput, setQuestionInput] = useState('');

  const [stages, setStages] = useState<{ stage_name: string, interviewer_id: string }[]>([
    { stage_name: 'Resume Screening', interviewer_id: '' },
    { stage_name: 'Technical Assessment', interviewer_id: '' },
    { stage_name: 'Final Interview', interviewer_id: '' }
  ]);
  const [team, setTeam] = useState<{ id: string, name: string, email: string }[]>([]);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [toast, setToast] = useState<{ message: string, type: 'success' | 'error' } | null>(null);

  // Right side AI state
  const [isAiLoading, setIsAiLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<{
    suggested_skills: string[],
    suggested_screening_questions: string[],
    suggested_interview_questions: string[]
  } | null>(null);

  // Chat state
  const [chatMessage, setChatMessage] = useState('');
  const [chatHistory, setChatHistory] = useState<{ role: 'user' | 'hr_assistant', content: string }[]>([]);
  const [isChatLoading, setIsChatLoading] = useState(false);

  // Predefined locations
  const predefinedLocations = [
    "Remote",
    "Remote - India", "Remote - US", "Remote - EMEA",
    "Bangalore, India", "Hyderabad, India", "Pune, India", "Chennai, India",
    "Mumbai, India", "New Delhi, India", "Gurgaon, India", "Noida, India",
    "Kolkata, India", "Ahmedabad, India", "Chandigarh, India", "Kochi, India",
    "San Francisco, CA", "New York, NY", "Austin, TX", "Seattle, WA", "Chicago, IL",
    "London, UK", "Berlin, Germany", "Toronto, Canada", "Sydney, Australia",
    "Singapore, SG", "Dubai, UAE"
  ];
  const [showLocationSelect, setShowLocationSelect] = useState(false);
  const filteredLocations = predefinedLocations.filter(loc => loc.toLowerCase().includes(formData.location.toLowerCase()));

  // Auto-fetch suggestions when job title finishes typing (debounced)
  useEffect(() => {
    if (formData.job_title.length > 3) {
      const timer = setTimeout(() => {
        fetchSuggestions();
      }, 1000);
      return () => clearTimeout(timer);
    }
  }, [formData.job_title]);

  useEffect(() => {
    const fetchTeam = async () => {
      try {
        const members = await api.getTeam();
        setTeam(members);
      } catch (e) {
        console.error("Failed to fetch team", e);
      }
    };
    const fetchTemplates = async () => {
      try {
        const data = await api.getJdTemplates();
        setTemplates(data);
      } catch (e) {
        console.error("Failed to fetch templates", e);
      }
    };
    fetchTeam();
    fetchTemplates();
  }, []);

  const fetchSuggestions = async () => {
    if (!formData.job_title) return;
    setIsAiLoading(true);
    try {
      const data = await api.suggestJobFields({
        job_title: formData.job_title,
        skills: skills
      });
      setSuggestions(data);
    } catch (e) {
      console.error("AI Assistant unavailable", e);
    } finally {
      setIsAiLoading(false);
    }
  };

  const handleSendChat = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatMessage.trim() || !formData.job_title) return;

    const userMsg = chatMessage.trim();
    setChatHistory([...chatHistory, { role: 'user', content: userMsg }]);
    setChatMessage('');
    setIsChatLoading(true);

    try {
      const response = await api.chatWithHRAssistant({
        job_title: formData.job_title,
        skills: skills,
        message: userMsg
      });
      setChatHistory(prev => [...prev, { role: 'hr_assistant', content: response.reply }]);
    } catch (err) {
      setChatHistory(prev => [...prev, { role: 'hr_assistant', content: "Sorry, I'm having trouble connecting right now." }]);
    } finally {
      setIsChatLoading(false);
    }
  };

  const handleAddSkill = (e: React.KeyboardEvent | React.MouseEvent, skillToAdd = skillInput) => {
    // Only accept enter key or mouse click from AI button
    if ('key' in e && e.key !== 'Enter') return;
    e.preventDefault();
    if (skillToAdd.trim() && !skills.includes(skillToAdd.trim())) {
      setSkills([...skills, skillToAdd.trim()]);
      setSkillInput('');
    }
  };

  const handleAddQuestion = (e: React.KeyboardEvent | React.MouseEvent, qToAdd = questionInput) => {
    if ('key' in e && e.key !== 'Enter') return;
    e.preventDefault();
    if (qToAdd.trim() && !screeningQuestions.includes(qToAdd.trim())) {
      setScreeningQuestions([...screeningQuestions, qToAdd.trim()]);
      setQuestionInput('');
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      // Assemble the massive backend payload
      const payload = {
        ...formData,
        template_type: selectedTemplate,
        hiring_manager_name: localStorage.getItem('hiring_ai_name') || 'Admin Admin',
        hiring_manager_email: localStorage.getItem('hiring_ai_email') || '',
        required_skills: skills,
        preferred_skills: [],
        screening_questions: screeningQuestions.map(q => ({ question: q, ideal_answer: "Open", is_mandatory: true })),
        technical_test_mcq: [], // Empty, lets AI generate during pipeline processing
        stages: stages.map((s, idx) => ({
          stage_name: s.stage_name,
          stage_order: idx + 1,
          interviewer_id: s.interviewer_id || null
        })),
        scoring_weights: { "Screening": 30, "Technical Test": 40, "Interview": 30 },
      };

      await api.createJob(payload);
      setToast({ message: 'Job successfully created and pipeline launched!', type: 'success' });
      setTimeout(() => navigate('/dashboard'), 1500);
    } catch (err: any) {
      setToast({ message: err.response?.data?.detail || 'Failed to create job', type: 'error' });
      setIsSubmitting(false);
    }
  };

  const renderChatContent = (content: string) => {
    // Split by backticks to extract inline skills
    const parts = content.split(/`([^`]+)`/);

    if (parts.length === 1) {
      // If no backticks, check if it's a simple comma-separated list
      if (content.length < 150 && content.includes(',')) {
        return (
          <div className="flex flex-wrap gap-2">
            {content.split(',').map((skill, i) => {
              const clean = skill.replace(/^[-*•\\d.]+\\s*/, '').trim();
              const isAdded = skills.includes(clean);
              return clean ? (
                <button key={i} onClick={(e) => handleAddSkill(e, clean)} disabled={isAdded} className="text-xs font-semibold px-2.5 py-1.5 rounded-lg border bg-indigo-500/20 border-indigo-500/40 text-indigo-200 hover:bg-indigo-500/40 transition-colors disabled:opacity-50 flex items-center">
                  {clean} {isAdded ? <Check className="w-3 h-3 ml-1" /> : <Plus className="w-3 h-3 ml-1 opacity-70" />}
                </button>
              ) : null;
            })}
          </div>
        );
      }

      // Otherwise, standard line parsing for bullet points
      return (
        <div className="space-y-2">
          {content.split('\\n').map((line, i) => {
            const cleanLine = line.replace(/^[-*•\\d.]+\\s*/, '').trim();
            if (!cleanLine) return null;

            if (cleanLine.length < 60 && line.match(/^[-*•\\d.]/)) {
              const isAdded = skills.includes(cleanLine) || screeningQuestions.includes(cleanLine);
              return (
                <div key={i} className="flex items-center justify-between group bg-white/5 border border-white/10 px-3 py-2 rounded-lg">
                  <span className="text-sm font-medium text-indigo-50">{cleanLine}</span>
                  <button
                    onClick={(e) => {
                      if (cleanLine.includes("?")) handleAddQuestion(e, cleanLine);
                      else handleAddSkill(e, cleanLine);
                    }}
                    disabled={isAdded}
                    className="opacity-0 group-hover:opacity-100 text-[10px] font-bold uppercase tracking-wider text-emerald-400 hover:text-emerald-300 disabled:opacity-50 disabled:text-indigo-500 transition-opacity whitespace-nowrap ml-3"
                  >
                    {isAdded ? '✓ Added' : '+ Add ⚡'}
                  </button>
                </div>
              );
            }
            return <p key={i} className="leading-relaxed">{line}</p>;
          })}
        </div>
      );
    }

    // Mix of text and backticked skills
    return (
      <div className="leading-relaxed whitespace-pre-wrap">
        {parts.map((part, i) => {
          if (i % 2 === 1) {
            // Backticked item
            const cleanPart = part.trim();
            const isAdded = skills.includes(cleanPart);
            return (
              <button
                key={i}
                onClick={(e) => handleAddSkill(e, cleanPart)}
                disabled={isAdded}
                className="inline-flex items-center mx-1 px-2 py-0.5 rounded border bg-emerald-500/20 border-emerald-500/40 text-emerald-200 hover:bg-emerald-500/40 transition-colors disabled:opacity-50 text-xs font-bold align-middle my-1"
              >
                {cleanPart} {isAdded ? <Check className="w-3 h-3 ml-1" /> : <Plus className="w-3 h-3 ml-1" />}
              </button>
            );
          }
          return <span key={i}>{part}</span>;
        })}
      </div>
    );
  };


  return (
    <div className="max-w-[1400px] mx-auto min-h-[calc(100vh-6rem)] animate-fade-in pb-12">
      <AnimatePresence>
        {toast && (
          <motion.div initial={{ opacity: 0, y: -50 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, scale: 0.9 }} className={`fixed top-8 right-8 z-[100] px-6 py-4 rounded-xl shadow-2xl flex items-center gap-3 border ${toast.type === 'success' ? 'bg-white border-green-100' : 'bg-red-50 border-red-100'}`}>
            <span className="font-semibold text-gray-900">{toast.message}</span>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="mb-8 flex items-center justify-between">
        <div>
          <button onClick={() => navigate('/dashboard')} className="flex items-center text-sm font-medium text-gray-500 hover:text-gray-900 transition-colors mb-3">
            <ArrowLeft className="w-4 h-4 mr-1.5" /> Back to Dashboard
          </button>
          <h1 className="text-3xl font-bold text-gray-900 tracking-tight flex items-center">
            <Briefcase className="w-8 h-8 mr-3 text-blue-600" /> Construct New Hiring Pipeline
          </h1>
          <p className="text-gray-500 mt-1">Configure your job posting, tests, and screening questions.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Form */}
        <div className="lg:col-span-8 bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
          <form onSubmit={handleCreate} className="space-y-8">

            {/* Section 1: Basics */}
            <div>
              <h2 className="text-lg font-bold text-gray-900 mb-4 flex items-center">
                <Settings className="w-5 h-5 mr-2 text-gray-400" /> Basic Details
              </h2>
              <div className="grid grid-cols-2 gap-5">
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Job Title *</label>
                  <input
                    type="text" required
                    placeholder="e.g. Senior Frontend Engineer"
                    className="w-full px-4 py-2.5 rounded-xl border border-gray-300 focus:ring-2 focus:ring-blue-500 transition-colors outline-none bg-gray-50 focus:bg-white text-gray-900 font-semibold"
                    value={formData.job_title}
                    onChange={e => setFormData({ ...formData, job_title: e.target.value })}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Department</label>
                  <input type="text" placeholder="e.g. Engineering" className="w-full px-4 py-2.5 rounded-xl border border-gray-300 focus:ring-2 focus:ring-blue-500 transition-colors bg-gray-50 focus:bg-white"
                    value={formData.department} onChange={e => setFormData({ ...formData, department: e.target.value })} />
                </div>
                <div className="relative">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Location *</label>
                  <input type="text" required placeholder="e.g. Remote, NY" className="w-full px-4 py-2.5 rounded-xl border border-gray-300 focus:ring-2 focus:ring-blue-500 transition-colors bg-gray-50 focus:bg-white"
                    value={formData.location}
                    onChange={e => {
                      setFormData({ ...formData, location: e.target.value });
                      setShowLocationSelect(true);
                    }}
                    onFocus={() => setShowLocationSelect(true)}
                    onBlur={() => setTimeout(() => setShowLocationSelect(false), 200)}
                  />
                  <AnimatePresence>
                    {showLocationSelect && filteredLocations.length > 0 && (
                      <motion.div initial={{ opacity: 0, y: -5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -5 }}
                        className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-xl shadow-lg max-h-48 overflow-y-auto"
                      >
                        {filteredLocations.map(loc => (
                          <div
                            key={loc}
                            onClick={() => {
                              setFormData({ ...formData, location: loc });
                              setShowLocationSelect(false);
                            }}
                            className="px-4 py-2 hover:bg-blue-50 cursor-pointer text-sm text-gray-700 hover:text-blue-700"
                          >
                            {loc}
                          </div>
                        ))}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Years of Experience *</label>
                  <input type="text" required placeholder="e.g. 5+ years" className="w-full px-4 py-2.5 rounded-xl border border-gray-300 focus:ring-2 focus:ring-blue-500 transition-colors bg-gray-50 focus:bg-white"
                    value={formData.experience_required} onChange={e => setFormData({ ...formData, experience_required: e.target.value })} />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Salary Range</label>
                  <input type="text" placeholder="e.g. $120k - $150k" className="w-full px-4 py-2.5 rounded-xl border border-gray-300 focus:ring-2 focus:ring-blue-500 transition-colors bg-gray-50 focus:bg-white"
                    value={formData.salary_range} onChange={e => setFormData({ ...formData, salary_range: e.target.value })} />
                </div>
              </div>
            </div>

            <hr className="border-gray-100" />

            {/* Section 2: Requirements */}
            <div>
              <h2 className="text-lg font-bold text-gray-900 mb-4 flex items-center">
                <ClipboardList className="w-5 h-5 mr-2 text-gray-400" /> Requirements & Process
              </h2>

              {/* Template Section */}
              <div className="mb-6">
                <label className="block text-sm font-medium text-gray-700 mb-2">JD Generation Style (Tone & Format) *</label>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {templates.map(tpl => (
                    <div 
                      key={tpl.key} 
                      onClick={() => setSelectedTemplate(tpl.key)}
                      className={`p-3 border-2 rounded-xl cursor-pointer transition-all ${selectedTemplate === tpl.key ? 'border-blue-500 bg-blue-50 text-blue-900' : 'border-gray-200 hover:border-blue-200 text-gray-700 bg-gray-50 hover:bg-white'}`}
                    >
                      <div className="font-bold text-sm mb-0.5">{tpl.name}</div>
                      <p className="text-[10px] opacity-70 leading-snug">{tpl.description}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-5 mb-5">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Employment Type</label>
                  <select className="w-full px-4 py-2.5 rounded-xl border border-gray-300 bg-gray-50 focus:ring-2 focus:ring-blue-500 outline-none"
                    value={formData.employment_type} onChange={e => setFormData({ ...formData, employment_type: e.target.value })}>
                    <option>Full-Time</option>
                    <option>Part-Time</option>
                    <option>Internship</option>
                    <option>Freelance</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Joining Availability</label>
                  <select className="w-full px-4 py-2.5 rounded-xl border border-gray-300 bg-gray-50 focus:ring-2 focus:ring-blue-500 outline-none"
                    value={formData.joining_requirement} onChange={e => setFormData({ ...formData, joining_requirement: e.target.value })}>
                    <option>Immediate Joiner</option>
                    <option>15 Days</option>
                    <option>30 Days</option>
                    <option>2 Months</option>
                  </select>
                </div>
              </div>

              <div className="mb-5">
                <label className="block text-sm font-medium text-gray-700 mb-1">Required Skills</label>
                <p className="text-xs text-gray-400 mb-2">Press enter to add. Used by AI to tailor the test & JD.</p>
                <div className="flex border border-gray-300 rounded-xl bg-gray-50 focus-within:ring-2 focus-within:ring-blue-500 overflow-hidden pr-2">
                  <input type="text" placeholder="e.g. React" className="flex-1 px-4 py-2 bg-transparent outline-none"
                    value={skillInput} onChange={e => setSkillInput(e.target.value)} onKeyDown={handleAddSkill} />
                  <button type="button" onClick={(e) => handleAddSkill(e)} className="text-blue-600 font-bold px-2 hover:text-blue-700">Add</button>
                </div>
                <div className="flex flex-wrap gap-2 mt-3">
                  <AnimatePresence>
                    {skills.map((s, i) => (
                      <motion.span initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.8, opacity: 0 }}
                        key={i} className="px-3 py-1 bg-blue-100 text-blue-800 rounded-lg text-sm font-semibold flex items-center">
                        {s} <button type="button" onClick={() => setSkills(skills.filter(sk => sk !== s))} className="ml-2 text-blue-400 hover:text-blue-900"><X className="w-3 h-3" /></button>
                      </motion.span>
                    ))}
                  </AnimatePresence>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Application Screening Questions</label>
                <p className="text-xs text-gray-400 mb-2">Candidates must answer these when applying.</p>
                <div className="flex gap-2">
                  <input type="text" placeholder="e.g. Do you have a valid working visa?" className="flex-1 px-4 py-2.5 rounded-xl border border-gray-300 bg-gray-50 focus:ring-2 focus:ring-blue-500 outline-none"
                    value={questionInput} onChange={e => setQuestionInput(e.target.value)} onKeyDown={handleAddQuestion} />
                  <button type="button" onClick={(e) => handleAddQuestion(e)} className="px-4 py-2 bg-gray-100 text-gray-700 font-bold rounded-xl hover:bg-gray-200 transition-colors whitespace-nowrap">Add Q</button>
                </div>
                <div className="space-y-2 mt-3">
                  <AnimatePresence>
                    {screeningQuestions.map((q, i) => (
                      <motion.div initial={{ opacity: 0, y: -5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, height: 0 }}
                        key={i} className="px-4 py-3 bg-gray-50 border border-gray-100 rounded-xl text-sm font-medium flex justify-between items-center group">
                        <span className="text-gray-700">Q{i + 1}: {q}</span>
                        <button type="button" onClick={() => setScreeningQuestions(screeningQuestions.filter(x => x !== q))} className="text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"><Trash2 className="w-4 h-4" /></button>
                      </motion.div>
                    ))}
                  </AnimatePresence>
                </div>
              </div>
            </div>

            <hr className="border-gray-100" />

            {/* Section 3: Technical Test */}
            <div>
              <h2 className="text-lg font-bold text-gray-900 mb-4 flex items-center">
                <MessageSquare className="w-5 h-5 mr-2 text-gray-400" /> Technical Evaluation
              </h2>
              <p className="text-sm text-gray-500 mb-4">Choose how you want to evaluate candidates in State 2.</p>

              <div className="grid grid-cols-2 gap-5 mb-4">
                <div className={`p-4 border-2 rounded-xl cursor-pointer transition-all ${formData.technical_test_type === 'AI' ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-blue-200'}`} onClick={() => setFormData({ ...formData, technical_test_type: 'AI' })}>
                  <div className="flex items-center mb-1">
                    <Sparkles className={`w-5 h-5 mr-2 ${formData.technical_test_type === 'AI' ? 'text-blue-600' : 'text-gray-400'}`} />
                    <span className={`font-bold ${formData.technical_test_type === 'AI' ? 'text-blue-900' : 'text-gray-700'}`}>Let AI Generate Tests</span>
                  </div>
                  <p className="text-xs text-gray-500">Autonomous MCQ generation</p>
                </div>
                <div className={`p-4 border-2 rounded-xl cursor-pointer transition-all ${formData.technical_test_type === 'External' ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-blue-200'}`} onClick={() => setFormData({ ...formData, technical_test_type: 'External' })}>
                  <div className="flex items-center mb-1">
                    <MapPin className={`w-5 h-5 mr-2 ${formData.technical_test_type === 'External' ? 'text-blue-600' : 'text-gray-400'}`} />
                    <span className={`font-bold ${formData.technical_test_type === 'External' ? 'text-blue-900' : 'text-gray-700'}`}>External Test Link</span>
                  </div>
                  <p className="text-xs text-gray-500">HackerRank, LeetCode, etc.</p>
                </div>
              </div>

              {formData.technical_test_type === 'External' && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Assessment URL</label>
                  <input type="url" placeholder="https://app.hackerrank.com/..." className="w-full px-4 py-2.5 rounded-xl border border-gray-300 bg-gray-50 focus:ring-2 focus:ring-blue-500 outline-none"
                    value={formData.technical_test_link} onChange={e => setFormData({ ...formData, technical_test_link: e.target.value })} />
                </motion.div>
              )}
            </div>

            <hr className="border-gray-100" />

            {/* Section 4: Hiring Workflow */}
            <div>
              <h2 className="text-lg font-bold text-gray-900 mb-4 flex items-center">
                <Settings className="w-5 h-5 mr-2 text-gray-400" /> Hiring Stages & Interviewers
              </h2>
              <p className="text-sm text-gray-500 mb-4">Define the sequence of stages and assign interviewers.</p>

              <div className="space-y-4">
                {stages.map((stage, idx) => (
                  <motion.div
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    key={idx}
                    className="flex gap-4 items-end bg-gray-50 p-4 rounded-2xl border border-gray-100 group"
                  >
                    <div className="flex-1">
                      <label className="block text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-1">Stage {idx + 1} Name</label>
                      <input
                        type="text"
                        value={stage.stage_name}
                        onChange={(e) => {
                          const newStages = [...stages];
                          newStages[idx].stage_name = e.target.value;
                          setStages(newStages);
                        }}
                        className="w-full px-4 py-2 rounded-xl border border-gray-200 focus:ring-2 focus:ring-blue-500 outline-none"
                      />
                    </div>
                    <div className="flex-1">
                      <label className="block text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-1">Assign Interviewer</label>
                      <select
                        value={stage.interviewer_id}
                        onChange={(e) => {
                          const newStages = [...stages];
                          newStages[idx].interviewer_id = e.target.value;
                          setStages(newStages);
                        }}
                        className="w-full px-4 py-2 rounded-xl border border-gray-200 focus:ring-2 focus:ring-blue-500 outline-none bg-white"
                      >
                        <option value="">Auto-assign (HR)</option>
                        {team.map(member => (
                          <option key={member.id} value={member.id}>{member.name} ({member.email})</option>
                        ))}
                      </select>
                    </div>
                    <button
                      type="button"
                      onClick={() => setStages(stages.filter((_, i) => i !== idx))}
                      className="p-2 text-gray-400 hover:text-red-500 transition-colors mb-1"
                    >
                      <Trash2 className="w-5 h-5" />
                    </button>
                  </motion.div>
                ))}
              </div>

              <button
                type="button"
                onClick={() => setStages([...stages, { stage_name: '', interviewer_id: '' }])}
                className="mt-4 flex items-center text-sm font-bold text-blue-600 hover:text-blue-700 transition-colors"
              >
                <Plus className="w-4 h-4 mr-1" /> Add Custom Stage
              </button>
            </div>

            <div className="pt-6 border-t border-gray-100 flex justify-end">
              <button disabled={isSubmitting} type="submit" className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-3.5 rounded-2xl font-bold shadow-xl shadow-blue-600/20 active:scale-95 transition-all flex items-center disabled:opacity-50">
                {isSubmitting ? <><Loader2 className="w-5 h-5 mr-2 animate-spin" /> Launching Pipeline...</> : 'Launch Hiring Pipeline 🚀'}
              </button>
            </div>
          </form>
        </div>

        {/* Right Column: AI Assistant */}
        <div className="lg:col-span-4 hidden lg:block">
          <div className="sticky top-8 bg-gradient-to-b from-indigo-900 to-slate-900 rounded-3xl p-6 shadow-2xl text-white border border-indigo-800">
            <div className="flex items-center mb-6 border-b border-indigo-800/50 pb-4">
              <div className="w-10 h-10 bg-indigo-500/20 rounded-xl flex items-center justify-center mr-3 backdrop-blur-sm border border-indigo-500/30">
                <Sparkles className="w-6 h-6 text-indigo-300" />
              </div>
              <h3 className="text-lg font-black tracking-tight">HR AI Assistant</h3>
            </div>

            {!formData.job_title ? (
              <div className="text-center py-6">
                <p className="text-indigo-200/60 text-sm">Start typing a <strong>Job Title</strong> on the left, and I will instantly suggest skills and screening questions based on the market.</p>
              </div>
            ) : isAiLoading ? (
              <div className="flex flex-col items-center py-8">
                <Loader2 className="w-8 h-8 animate-spin text-indigo-400 mb-4" />
                <p className="text-sm font-medium text-indigo-200 animate-pulse">Analyzing role profile...</p>
              </div>
            ) : suggestions ? (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">

                {/* Skills Suggestions */}
                <div className="space-y-3">
                  <h4 className="text-xs font-black uppercase tracking-widest text-indigo-400">Suggested Skills</h4>
                  <div className="flex flex-wrap gap-2">
                    {suggestions.suggested_skills.map((skill, idx) => (
                      <button
                        key={idx}
                        onClick={(e) => handleAddSkill(e, skill)}
                        className={`text-xs font-semibold px-2.5 py-1.5 rounded-lg border transition-all ${skills.includes(skill) ? 'bg-indigo-500/20 border-indigo-500/40 text-indigo-200 opacity-50 cursor-not-allowed' : 'bg-white/5 border-white/10 hover:bg-white/10 text-white'}`}
                        disabled={skills.includes(skill)}
                      >
                        {skill} {skills.includes(skill) ? <Check className="w-3 h-3 inline ml-1" /> : <Plus className="w-3 h-3 inline ml-1 opacity-70" />}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Screening Suggestions */}
                <div className="space-y-3 pt-4 border-t border-indigo-800/50">
                  <h4 className="text-xs font-black uppercase tracking-widest text-indigo-400">Top Screening Questions</h4>
                  <div className="space-y-2">
                    {suggestions.suggested_screening_questions.map((q, idx) => (
                      <div key={idx} className="bg-white/5 border border-white/10 p-3 rounded-xl">
                        <p className="text-sm font-medium text-indigo-100 mb-2 leading-snug">{q}</p>
                        <button
                          onClick={(e) => handleAddQuestion(e, q)}
                          disabled={screeningQuestions.includes(q)}
                          className="text-[10px] font-bold uppercase tracking-wider text-emerald-400 hover:text-emerald-300 disabled:text-indigo-500/50 transition-colors flex items-center"
                        >
                          {screeningQuestions.includes(q) ? '✓ Added to form' : '+ Add to Form ⚡'}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Technical Suggestions */}
                <div className="space-y-3 pt-4 border-t border-indigo-800/50">
                  <h4 className="text-xs font-black uppercase tracking-widest text-indigo-400">AI Assessment Focus</h4>
                  <p className="text-xs text-indigo-200/70 leading-relaxed mb-2">If you select "Let AI Generate Tests", the LangGraph agent will base the MCQ on these core areas:</p>
                  <ul className="list-disc list-inside text-xs font-medium text-indigo-100 space-y-1 ml-1">
                    {suggestions.suggested_interview_questions.slice(0, 3).map((iq, idx) => (
                      <li key={idx} className="truncate">{iq}</li>
                    ))}
                  </ul>
                </div>

                {/* AI Chat */}
                <div className="pt-4 border-t border-indigo-800/50">
                  <h4 className="text-xs font-black uppercase tracking-widest text-indigo-400 mb-3 flex items-center gap-2"><MessageSquare className="w-4 h-4" /> Ask AI Anything</h4>

                  <div className="space-y-3 max-h-48 overflow-y-auto mb-3 pr-1">
                    {chatHistory.map((msg, idx) => (
                      <div key={idx} className={`p-3 rounded-xl text-sm ${msg.role === 'user' ? 'bg-indigo-500/20 text-white ml-6 rounded-tr-sm' : 'bg-white/5 border border-white/10 text-indigo-100 mr-6 rounded-tl-sm'}`}>
                        {msg.role === 'hr_assistant' ? renderChatContent(msg.content) : msg.content}
                      </div>
                    ))}
                    {isChatLoading && (
                      <div className="flex bg-white/5 border border-white/10 text-indigo-100 mr-6 rounded-xl rounded-tl-sm p-3 w-fit">
                        <Loader2 className="w-4 h-4 animate-spin opacity-70" />
                      </div>
                    )}
                  </div>

                  <form onSubmit={handleSendChat} className="flex gap-2">
                    <input type="text" placeholder="e.g. Can you suggest more skills?" className="flex-1 px-3 py-2 bg-white/5 border border-indigo-800 focus:border-indigo-500 rounded-lg text-sm text-white placeholder:text-indigo-300 outline-none" value={chatMessage} onChange={e => setChatMessage(e.target.value)} disabled={isChatLoading} />
                    <button type="submit" disabled={isChatLoading || !chatMessage.trim()} className="p-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:hover:bg-indigo-600 rounded-lg transition-colors text-white"><Send className="w-4 h-4" /></button>
                  </form>
                </div>

              </motion.div>
            ) : null}

            <div className="mt-8 p-4 bg-black/20 rounded-2xl flex items-start">
              <div className="bg-indigo-500 w-2 h-2 rounded-full mt-1.5 mr-3 animate-pulse flex-shrink-0" />
              <p className="text-xs text-indigo-200/80 leading-relaxed">
                <strong>LangGraph Powered.</strong> Fully automated JD and technical question generation happens asynchronously after form submission to save you time.
              </p>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
