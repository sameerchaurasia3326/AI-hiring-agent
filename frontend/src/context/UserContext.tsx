import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';

export interface UserProfile {
  id: string;
  email: string;
  name: string;
  role: string;
  organization_id: string;
  google_connected: boolean;
  linkedin_status?: string | null;
  linkedin_account_name?: string | null;
  linkedin_account_picture?: string | null;
  linkedin_company_urn?: string | null;
}

interface UserContextType {
  user: UserProfile | null;
  loading: boolean;
  error: string | null;
  refreshUser: () => Promise<void>;
  logout: () => void;
}

const UserContext = createContext<UserContextType | undefined>(undefined);

export const UserProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true); // [STRICT] Always wait for verification
  const [error, setError] = useState<string | null>(null);

  const fetchUser = useCallback(async () => {
    const token = localStorage.getItem('hiring_ai_token');
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      const profile = await api.getUserProfile();
      console.log("USER:", profile); // [VERIFY] Confirm correct identity and role in console
      setUser(profile);
      setError(null);
      
      // Sync localStorage with DB source of truth
      localStorage.setItem('hiring_ai_role', profile.role);
      localStorage.setItem('hiring_ai_email', profile.email);
      localStorage.setItem('hiring_ai_name', profile.name);
    } catch (err: any) {
      console.error('Failed to fetch user profile:', err);
      // Auto-logout if truly unauthorized
      if (err.response?.status === 401) {
        localStorage.clear();
        sessionStorage.clear();
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);
 // [FIX] Removed 'user' dependency to break infinite re-fetch loop

  useEffect(() => {
    fetchUser();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // [FIX] Explicitly run only once on mount to prevent any possible loop

  const logout = () => {
    localStorage.clear();
    sessionStorage.clear();
    setUser(null);
    window.location.href = '/login';
  };

  return (
    <UserContext.Provider value={{ user, loading, error, refreshUser: fetchUser, logout }}>
      {children}
    </UserContext.Provider>
  );
};

export const useUser = () => {
  const context = useContext(UserContext);
  if (context === undefined) {
    throw new Error('useUser must be used within a UserProvider');
  }
  return context;
};
