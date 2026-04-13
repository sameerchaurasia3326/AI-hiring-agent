import React, { useEffect, useState } from 'react';
import { Mail, Shield, User, Calendar, CheckCircle2, ChevronRight, AlertCircle, Linkedin } from 'lucide-react';
import { api } from '../services/api';
import { useUser } from '../context/UserContext';

const Settings: React.FC = () => {
  const { user: profile, loading: userLoading, refreshUser } = useUser();
  const [linkedinConnected, setLinkedinConnected] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [disconnectingCalendar, setDisconnectingCalendar] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('linkedin_connected') === 'true') {
      setLinkedinConnected(true);
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);

  useEffect(() => {
    if (profile?.linkedin_status === 'active') {
      setLinkedinConnected(true);
    } else {
      setLinkedinConnected(false);
    }
  }, [profile]);

  const handleConnectCalendar = () => {
    const token = localStorage.getItem('hiring_ai_token');
    window.location.href = `/api/auth/google?token=${token}`;
  };

  const handleDisconnectCalendar = async () => {
    if (!confirm('Disconnect Google Calendar? AI will not be able to schedule meetings.')) return;
    setDisconnectingCalendar(true);
    try {
      await api.disconnectGoogleCalendar();
      await refreshUser();
    } catch (e) {
      alert('Failed to disconnect. Please try again.');
    } finally {
      setDisconnectingCalendar(false);
    }
  };

  const handleConnectLinkedin = () => {
    const token = localStorage.getItem('hiring_ai_token');
    window.location.href = `/api/auth/linkedin?token=${token}&_t=${Date.now()}`;
  };

  const handleDisconnectLinkedin = async () => {
    if (!confirm('Disconnect LinkedIn? You can reconnect anytime.')) return;
    setDisconnecting(true);
    try {
      await api.disconnectLinkedin();
      await refreshUser();
    } catch (e) {
      alert('Failed to disconnect. Please try again.');
    } finally {
      setDisconnecting(false);
    }
  };

  if (userLoading && !profile) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent"></div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl p-8">
      <header className="mb-12">
        <h1 className="text-4xl font-black tracking-tight text-slate-900">Settings</h1>
        <p className="mt-2 text-slate-500 font-medium">Manage your account and integrations</p>
      </header>

      <div className="space-y-8">
        {/* Profile Section */}
        <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm transition-all duration-300 hover:shadow-md">
          <div className="border-b border-slate-100 bg-slate-50/50 px-8 py-4">
            <h2 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-slate-400">
              <User className="h-4 w-4" />
              Account Profile
            </h2>
          </div>
          <div className="p-8">
            <div className="flex items-center gap-6">
              <div className="flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-2xl font-bold text-white shadow-lg ring-4 ring-blue-50">
                {profile?.name?.charAt(0).toUpperCase()}
              </div>
              <div className="flex-1">
                <h3 className="text-2xl font-black text-slate-900">{profile?.name}</h3>
                <div className="mt-2 flex flex-wrap gap-4">
                  <span className="flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-600">
                    <Mail className="h-3 w-3" />
                    {profile?.email}
                  </span>
                  <span className="flex items-center gap-1.5 rounded-full bg-blue-100 px-3 py-1 text-xs font-bold text-blue-600">
                    <Shield className="h-3 w-3" />
                    {profile?.role?.toUpperCase()}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Integrations Section - Restricted to Admin */}
        {profile?.role === 'admin' && (
          <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm transition-all duration-300 hover:shadow-md">
            <div className="border-b border-slate-100 bg-slate-50/50 px-8 py-4">
              <h2 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-slate-400">
                <Calendar className="h-4 w-4" />
                Integrations
              </h2>
            </div>
            <div className="p-8">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
                <div className="flex items-start gap-4 text-left">
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-slate-50 ring-1 ring-slate-200">
                    <svg className="h-6 w-6" viewBox="0 0 24 24">
                      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
                      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.66l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 12-4.53z"/>
                    </svg>
                  </div>
                  <div>
                    <h4 className="text-lg font-black text-slate-900">Google Calendar</h4>
                    <p className="mt-1 text-sm font-medium text-slate-500">
                      Automatically sync interviews and check availability in real-time.
                    </p>
                  </div>
                </div>

                {profile?.google_connected ? (
                  <div className="flex flex-col sm:flex-row items-center gap-3 shrink-0">
                    <div className="flex items-center gap-3 rounded-2xl bg-emerald-50 px-6 py-3 ring-1 ring-emerald-200">
                      <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                      <span className="text-sm font-black text-emerald-700">Calendar Connected</span>
                    </div>
                    <button
                      onClick={handleDisconnectCalendar}
                      disabled={disconnectingCalendar}
                      className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-bold text-red-600 hover:bg-red-100 transition-all disabled:opacity-50"
                    >
                      {disconnectingCalendar ? 'Disconnecting...' : 'Disconnect'}
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={handleConnectCalendar}
                    className="group flex items-center justify-center gap-2 rounded-2xl bg-slate-900 px-8 py-4 text-sm font-black text-white transition-all hover:bg-slate-800 hover:shadow-xl active:scale-95"
                  >
                    Connect Calendar
                    <ChevronRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
                  </button>
                )}
              </div>
              
              {!profile?.google_connected && (
                <div className="mt-6 flex items-start gap-2 rounded-2xl bg-amber-50 p-4 ring-1 ring-amber-200">
                  <AlertCircle className="h-4 w-4 shrink-0 text-amber-600" />
                  <p className="text-xs font-bold text-amber-800">
                    Connecting your calendar allows the AI to suggest interview slots and generate Google Meet links automatically.
                  </p>
                </div>
              )}

              <div className="my-8 border-t border-slate-100"></div>

              {/* LinkedIn Integration */}
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
                <div className="flex items-start gap-4 text-left">
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#0A66C2]/10 ring-1 ring-[#0A66C2]/20 text-[#0A66C2]">
                    <Linkedin className="h-6 w-6" />
                  </div>
                  <div>
                    <h4 className="text-lg font-black text-slate-900">LinkedIn Integration</h4>
                    <p className="mt-1 text-sm font-medium text-slate-500">
                      Automatically post approved job descriptions to your company's LinkedIn page.
                    </p>
                  </div>
                </div>

                {linkedinConnected ? (
                  <div className="flex flex-col sm:flex-row items-center gap-3 shrink-0">
                    <div className="flex items-center gap-3 rounded-2xl bg-emerald-50 px-4 py-3 ring-1 ring-emerald-200">
                      {profile?.linkedin_account_picture ? (
                        <img
                          src={profile.linkedin_account_picture}
                          alt="LinkedIn"
                          className="h-7 w-7 rounded-full object-cover ring-2 ring-emerald-300"
                        />
                      ) : (
                        <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0" />
                      )}
                      <div className="text-left">
                        <p className="text-sm font-black text-emerald-700 leading-none">
                          {profile?.linkedin_account_name || 'LinkedIn Connected'} ✅
                        </p>
                        {profile?.linkedin_company_urn ? (
                          <p className="text-xs text-emerald-600 font-medium mt-0.5">🏢 Company Page ready</p>
                        ) : (
                          <p className="text-xs text-amber-600 font-medium mt-0.5">⚠️ No Company Page detected</p>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={handleDisconnectLinkedin}
                      disabled={disconnecting}
                      className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-bold text-red-600 hover:bg-red-100 transition-all disabled:opacity-50"
                    >
                      {disconnecting ? 'Disconnecting...' : 'Disconnect'}
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={handleConnectLinkedin}
                    className="group flex items-center justify-center gap-2 rounded-2xl bg-[#0A66C2] px-8 py-4 text-sm font-black text-white transition-all hover:bg-[#004182] hover:shadow-xl active:scale-95"
                  >
                    Connect LinkedIn
                    <ChevronRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
                  </button>
                )}
              </div>
            </div>
          </section>
        )}
      </div>
    </div>
  );
};

export default Settings;
