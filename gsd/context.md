Project: Hiring.AI

Type: AI-powered hiring automation system

Stack:
- FastAPI backend
- LangGraph pipeline
- PostgreSQL database
- React frontend
- Ollama (local LLM)

Goal:
Automate hiring:
- JD generation
- Resume scoring
- Shortlisting
- Interview scheduling

Current Issues:
- Resume parsing crashes (LLM JSON issues)
- Scoring inconsistency
- Pipeline crashes (escalate stage)
- Email system failing
- Timeout issues

Requirement:
- System must be fault-tolerant
- Must not crash on bad LLM output
- Must work reliably with local models