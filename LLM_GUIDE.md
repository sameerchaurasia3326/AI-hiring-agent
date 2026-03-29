# LLM Architecture & Resiliency Guide

This document outlines the design of the AI-driven hiring pipeline, focusing on the fallback mechanisms, error handling, and developer best practices.

## 1. The Multi-Level Fallback Chain

To ensure the hiring pipeline never fails due to API issues or rate limits, we use a **4-level fallback system** in `src/tools/llm_factory.py`.

### 🛡️ Resiliency Order (Default)
1.  **OpenAI** (`gpt-4o`): The primary engine used for high-accuracy tasks like JD drafting.
2.  **Google Gemini** (`gemini-2.0-flash`): The first cloud fallback for speed and high context window.
3.  **OpenRouter** (`anthropic/claude-3-5-sonnet`): The secondary cloud fallback, providing access to top-tier models through a separate gateway.
4.  **Ollama** (`llama3.2`): The **Absolute Last Resort**. If all three cloud providers fail (connectivity, balance, or rate limits), the system falls back to your local hardware.

### 💡 Configuration
The primary model and order can be changed in `src/config/settings.py` or `.env`:
```bash
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
# Set prioritize_local=True in get_llm() to push Ollama to the front
```

---

## 2. Real-Time UI Feedback (The "Drafting" Pattern)

LLMs can take 15-40 seconds to generate a complete Job Description. To prevent users from seeing a "stuck" processing spinner, we implement **State Initialization**.

### The Implementation:
1.  **Request Start**: In `main.py`, the moment a job is created, we set the `jd_draft` column to:
    `🤖 AI is drafting your Job Description... (approx 30s)`
2.  **Node Execution**: The LangGraph node `generate_jd` starts in the background.
3.  **Node Finish**: Once the LLM returns, the node immediately updates the database with the real text and advances the state to `JD_APPROVAL_PENDING`.

---

## 3. Advanced Error Handling & Logging

We use specialized logging to ensure developers can diagnose AI issues instantly from the terminal.

### 📝 Log Signatures:
- `🤖 [LLM] Trying primary: ChatOpenAI`: The first attempt started.
- `🔄 [LLM] Falling back to: ChatGoogleGenerativeAI`: The primary failed; a fallback was triggered automatically.
- `❌ [LLM] ChatOpenAI failed: Rate Limit Exceeded`: The specific cause of failure is always logged.
- `⚡ [generate_jd] Node triggered!`: Confirmation that the LangGraph task has started in the background.

---

## 4. Structured Output Enforcement

For complex data like **Technical Assessments (MCQs)**, we enforce a strict schema using Pydantic. This ensures the frontend never crashes due to malformed AI responses.

### Schema Guardrails:
```python
class MCQ(BaseModel):
    question: str
    options: List[str] # Exactly 4
    correct_index: int # 0-3
```
- **File**: `src/nodes/test_generator.py`
- **Mechanism**: We use `llm.with_structured_output(MCQList)` to force the AI to return valid JSON.

---

## Summary for Developers:
- **Rule 1**: Always use `get_llm()` from `src/tools/llm_factory.py`. Never instantiate provider-specific classes directly.
- **Rule 2**: Check for `⚡ Node triggered` in the logs to verify the pipeline started.
- **Rule 3**: If you add a new AI node, ensure it calls `await session.commit()` internally so the dashboard updates mid-pipeline.
