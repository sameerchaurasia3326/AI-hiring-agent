# Authentication & Identity Implementation Guide

This document explains the architecture and implementation details of the login and signup systems in this project. You can use this as a reference for replicating this logic in other B2B SaaS applications.

## 1. Backend: Security Foundation (`src/api/auth.py`)

The backend uses a standard JWT-based authentication system with RBAC (Role-Based Access Control).

### Password Security
- **Hashing**: We never store plain-text passwords. We use `bcrypt` with a salt to hash passwords before saving them to the database.
- **Verification**: `bcrypt.checkpw` is used during login to verify the provided password against the stored hash.

### JWT (JSON Web Tokens)
- **Generation**: When a user logs in, we generate a JWT signed with a `HS256` algorithm and a `SECRET_KEY`.
- **Payload**: The token contains the `user_id` and the user's `role` (e.g., `admin`, `interviewer`).
- **Expiration**: Tokens are set to expire (default 7 days) to minimize risk if a token is intercepted.

### RBAC Dependencies
We use FastAPI's dependency injection system to protect routes:
- `get_current_user`: Extracts the token from the `Authorization: Bearer <token>` header and decodes it.
- `require_admin`: A wrapper that checks if the decoded token's role is `admin`.

---

## 2. Frontend: Authentication Flow

The frontend is built with React and manages the user session via `localStorage`.

### Login/Signup Pages (`frontend/src/pages/Login.tsx`)
- **State Management**: Uses React `useState` for form fields and `loading` states.
- **Persistence**: Upon successful login, the `access_token` and `role` are stored in `localStorage`.
- **Navigation**: The user is redirected to the `/dashboard` (admin) or `/my-tasks` (interviewer) based on their role.

### API Service (`frontend/src/services/api.ts`)
- An Axios interceptor is used to automatically attach the JWT from `localStorage` to every outgoing request:
```javascript
// Example Interceptor Logic
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('hiring_ai_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```

---

## 3. Google OAuth 2.0 Integration

We support passwordless login via Google OAuth.

### Flow Architecture:
1.  **Initiation**: The user clicks "Login with Google". The frontend redirects the browser to the backend endpoint: `window.location.href = '/api/auth/login/google'`.
2.  **Backend Handshake**: The backend (`google_auth_utils.py`) constructs the Google Auth URL and redirects the user to Google's consent screen.
3.  **Callback**: After consent, Google redirects back to our backend, which exchanges the code for a Google token, fetches user info, and creates/logs in the user in our DB.
4.  **Frontend Callback (`AuthCallback.tsx`)**: The backend eventually redirects the user back to a specific frontend route with the JWT in the URL. The `AuthCallback.tsx` component extracts this token, saves it to `localStorage`, and completes the login.

---

## 4. Best Practices Summary
- **Zero Local Tokens in State**: Only store tokens in `localStorage` or HttpOnly cookies to survive page refreshes.
- **Fail Fast**: The backend should validate the JWT at the edge (FastAPI dependencies) before any business logic executes.
- **Multi-Tenant Isolation**: Always include the `organization_id` in the JWT payload and use it to filter every database query.
