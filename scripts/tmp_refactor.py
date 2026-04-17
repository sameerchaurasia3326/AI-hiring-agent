import re

with open("src/nodes/resume_scorer.py", "r") as f:
    text = f.read()

# 1. Deterministic temperature
text = text.replace("llm = get_llm(temperature=0.1)", "llm = get_llm(temperature=0.0)")

# 2. Add an inner async function definition and parallel execution block
# We replace the for loop iteration with the async function structure.

target_loop = """        for app in applications:
            if (app["candidate_id"], str(job_id)) in already_scored_this_job"""

new_structure = """        async def _process_single_candidate(app) -> dict:
            try:
                if (app["candidate_id"], str(job_id)) in already_scored_this_job:
                    logger.info("⏩ {} already scored for job {} — skipping.", app["name"], job_id)
                    return None

                resume_path = app.get("resume_path")
                if not resume_path:
                    logger.warning("Missing resume path for candidate {}", app["name"])
                    return None

                if not resume_path.startswith(("http://", "https://")):
                    import os
                    if not os.path.exists(resume_path):
                        logger.error("❌ Local resume file not found: {} for candidate {}", resume_path, app["name"])
                        return None"""

text = text.replace(target_loop, new_structure, 1)

# Now fix the continues to return None
text = text.replace('                    continue', '                    return None')

# Now add asyncio gather block at the end
# The try/except for the main candidate logic ends around line 434:
target_end = """            except asyncio.TimeoutError:
                logger.error("❌ Timeout scoring candidate {} - Skipping", app["name"])
                return None
            except Exception as e:
                logger.exception("❌ Critical failure scoring {}: {}", app["name"], e)
                return None

        # ── Final Status Update ─────────────────────────────────────"""

# We want to change the timeout and exception catch to return a ZERO score object.
new_end_zero_score = """            except asyncio.TimeoutError:
                logger.error("❌ Timeout scoring candidate {} - Generating zero score", app["name"])
                scored_obj = {
                    "candidate_id": app["candidate_id"],
                    "job_id":       str(job_id),
                    "name":         app["name"],
                    "email":        app["email"],
                    "score":        0.0,
                    "reasoning":    "Failed due to processing timeout.",
                    "strengths":    [],
                    "gaps":         []
                }
            except Exception as e:
                logger.exception("❌ Critical failure scoring {}: {}", app["name"], e)
                scored_obj = {
                    "candidate_id": app["candidate_id"],
                    "job_id":       str(job_id),
                    "name":         app["name"],
                    "email":        app["email"],
                    "score":        0.0,
                    "reasoning":    f"Failed due to a critical error.",
                    "strengths":    [],
                    "gaps":         []
                }

            return scored_obj

        # Process all candidates in parallel with bounded concurrency
        import asyncio
        semaphore = asyncio.Semaphore(3) # Ensure stability on slow local LLMs
        
        async def _bounded_process(app):
            async with semaphore:
                return await _process_single_candidate(app)
                
        tasks = [_bounded_process(app) for app in applications]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for r in results:
            if isinstance(r, dict) and r is not None:
                new_scored.append(r)

        # ── Final Status Update ─────────────────────────────────────"""

text = text.replace(target_end, new_end_zero_score, 1)

# we also need to change the DB save from inside the loop to also handle the zero score if exception happens.
# Wait, the try/except was returning scored_obj. Let's make sure the DB is updated.
# Instead of doing that, if they get 0.0, we just return the scored_obj and let a batch DB update run, or do nothing since 0.0 score means they aren't shortlisted anyway (unless we want 'is_scored' flag set).
# The inner loop already has the `log_activity_sync` and `DB Update` block which executes if everything succeeds. If we jump to `except asyncio.TimeoutError`, it skips the DB update in our new code. This is fine because 0.0 dropouts won't be saved, giving them another chance later, OR we can save them.
# The `new_scored.append(scored_obj)` on line 408 is currently there. We need to replace it because in our async func we should just `return scored_obj`.

text = text.replace("                new_scored.append(scored_obj)", "                pass")
text = text.replace("                    await session.commit()", "                    await session.commit()\n                return scored_obj")

with open("src/nodes/resume_scorer.py", "w") as f:
    f.write(text)
