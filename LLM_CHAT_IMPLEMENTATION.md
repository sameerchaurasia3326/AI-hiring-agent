# AI Chat Assistant Implementation

This document explains the architecture and implementation details of the **AI Chat Assistant** featured in the job creation workflow of Hiring.AI.

## 🌟 Overview
The AI Chat Assistant provides real-time, context-aware suggestions for recruiters during the job creation process. It helps with:
- Generating skill requirements.
- Drafting screening questions.
- Providing industry-standard interview questions.
- Optimizing job titles.

## 🏗️ Technical Architecture

The feature follows a classic Client-Server-LLM pattern, enhanced with a robust **Multi-Provider Fallback System**.

### 1. Frontend (React)
- **File**: `frontend/src/pages/CreateJob.tsx`
- **Logic**: As the user types their question in the chat panel, the system captures the **Current Form State** (Job Title, currently selected Skills).
- **Service**: Calls `api.chatWithHRAssistant` which sends a POST request to the backend.

### 2. Backend API (FastAPI)
- **Endpoint**: `POST /api/jobs/ai-chat`
- **File**: `src/api/main.py`
- **Context Injection**: The backend receives the message along with the current form context. This ensures that if you ask "what skills are needed?", the AI knows you are talking about a "Senior Software Engineer" (if that's the title in the form).

### 3. LLM Factory (LangChain)
- **File**: `src/tools/llm_factory.py`
- **The "Brain"**: Instead of calling a single API, we use a custom factory that returns a **Fallback Chain**.
- **Priority Order**:
  1. **OpenAI** (GPT-4o-mini) - Primary, fast and smart.
  2. **Google Gemini** (Gemini 2.0 Flash) - Secondary, high rate limits.
  3. **OpenRouter** - Tertiary, provides access to multiple open-source models.
  4. **Ollama (Local)** - Final fallback. If the internet is down or all APIs fail, it uses a local model (e.g., Llama 3) running on the server.

## 📝 Prompt Engineering
To ensure the AI is helpful and not "wordy," we use a strict system prompt:

> "You are an expert technical recruiter and HR assistant. ... Your answers must be HYPER CONCISE and immediately copy-pasteable. DO NOT give general career advice or long explanations. If they ask for skills, give a simple comma-separated list."

## 🔄 Sequence Diagram (Conceptual)
1. **User**: Types "Suggest 5 skills for a React dev"
2. **Frontend**: Sends `{title: "React Developer", message: "Suggest 5 skills..."}`
3. **Backend**: Combines user message with System Prompt + Job Context.
4. **LLM Factory**: Tries OpenAI -> Success! (or falls back if fails).
5. **AI**: Returns: "React, TypeScript, Redux, Tailwind CSS, Jest"
6. **Frontend**: Displays reply; user can copy-paste into the form.

## 🛠️ Reliability Features
- **Stateless Chat**: Every message sends the current form state, so the AI always has the latest "truth" without needing a complex session database.
- **Error Resilience**: If a model fails mid-request, the fallback mechanism automatically retries with the next provider in milliseconds, usually without the user even noticing.
