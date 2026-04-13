from __future__ import annotations

import functools
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, ValidationError, field_validator
import uuid
from loguru import logger
from langgraph.errors import GraphInterrupt

from src.state.schema import PipelineStatus

class HiringStateValidator(BaseModel):
    """
    Pydantic mirror of the TypedDict HiringState.
    Used for runtime validation and cleaning of node outputs.
    """
    job_id: Optional[str] = None
    organization_id: Optional[str] = None
    job_title: Optional[str] = None
    jd_draft: Optional[str] = None
    
    # Statuses
    pipeline_status: Optional[str] = None
    current_stage: Optional[str] = None
    action_type: Optional[str] = None
    
    # Lists (should always be lists)
    required_skills: Optional[List[str]] = Field(default_factory=list)
    applications: Optional[List[Dict]] = Field(default_factory=list)
    scored_resumes: Optional[List[Dict]] = Field(default_factory=list)
    shortlist: Optional[List[Dict]] = Field(default_factory=list)
    error_log: Optional[List[str]] = Field(default_factory=list)

    @field_validator("job_id", mode="before")
    @classmethod
    def validate_uuid(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        try:
            # Ensure it's a valid UUID
            if isinstance(v, uuid.UUID):
                return str(v)
            uuid.UUID(str(v))
            return str(v)
        except ValueError:
            logger.warning(f"⚠️ Validation: Invalid job_id format ignored: {v}")
            return None

    @field_validator("pipeline_status", mode="before")
    @classmethod
    def validate_enum(cls, v: Any) -> Optional[str]:
        if v is None: return None
        # Ensure it matches one of our PipelineStatus values
        try:
            return PipelineStatus(v).value
        except ValueError:
            logger.warning(f"⚠️ Validation: Unknown pipeline_status {v}")
            return None

def validate_node(func):
    """
    Decorator for LangGraph nodes to enforce data integrity.
    Catches errors early and ensures consistent data types.
    """
    @functools.wraps(func)
    async def wrapper(state: Dict[str, Any], *args, **kwargs):
        try:
            # Execute node
            result = await func(state, *args, **kwargs)
            
            # If the node returns a dict (state update), validate it
            if isinstance(result, dict):
                try:
                    # Partial validation (since nodes only return changes)
                    HiringStateValidator(**result)
                except ValidationError as e:
                    logger.error(f"❌ State Validation Error in {func.__name__}: {e}")
                    # We could inject 'error_log' here if needed
                    if "error_log" not in result:
                        result["error_log"] = [f"Validation error in {func.__name__}: {str(e)[:100]}"]
            
            return result
        except GraphInterrupt:
            # Phase 15 & Fix: Re-raise LangGraph interrupts so the graph can pause for HR
            raise
        except Exception as e:
            logger.error(f"💥 Node Crash in {func.__name__}: {e}")
            # If a node crashes, we try to preserve the job_id and mark as FAILED instead of a hard crash
            return {
                "pipeline_status": PipelineStatus.FAILED.value,
                "error_log": [f"Runtime error in {func.__name__}: {str(e)}"]
            }
    return wrapper
