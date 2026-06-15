import asyncio
import json
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from open_notebook.domain.research import ResearchMission, ResearchNote
from open_notebook.exceptions import InvalidInputError, NotFoundError

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class CreateMissionRequest(BaseModel):
    query: str = Field(..., description="Research question")
    notebook_id: Optional[str] = Field(
        None, description="Notebook ID for source context"
    )
    title: Optional[str] = Field(
        None, description="Mission title (auto-generated if empty)"
    )
    depth: Optional[str] = Field(
        "comprehensive",
        description="Research depth: quick, comprehensive, exhaustive",
    )
    model_override: Optional[str] = Field(None, description="Model ID override")


# ---------------------------------------------------------------------------
# Background task helper
# ---------------------------------------------------------------------------


async def run_research_mission(mission_id: str) -> None:
    """Run the research graph for a mission in the background."""
    try:
        from open_notebook.graphs.research import graph as research_graph

        mission = await ResearchMission.get(mission_id)
        if not mission:
            return

        await research_graph.ainvoke(
            {
                "mission_id": mission_id,
                "query": mission.query,
                "notebook_id": mission.notebook_id,
                "depth": mission.depth or "comprehensive",
                "model_override": mission.model_override,
                "plan": None,
                "notes": [],
                "reflections": None,
                "report": None,
                "summary": None,
                "status": "planning",
                "progress": 0,
                "error": None,
                "execution_log": [],
            }
        )
    except Exception as e:
        logger.error(f"Research mission {mission_id} failed: {e}")
        try:
            mission = await ResearchMission.get(mission_id)
            if mission:
                mission.status = "failed"
                mission.error_message = str(e)
                await mission.save()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# SSE streaming helper
# ---------------------------------------------------------------------------


async def stream_mission_progress(mission_id: str) -> AsyncGenerator[str, None]:
    """Poll a mission periodically and yield SSE events."""
    last_log_count = 0
    while True:
        mission = await ResearchMission.get(mission_id)
        if not mission:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Mission not found'})}\n\n"
            break

        # Send new log entries
        logs = mission.execution_log or []
        if len(logs) > last_log_count:
            for log in logs[last_log_count:]:
                yield f"data: {json.dumps({'type': 'log', 'data': log})}\n\n"
            last_log_count = len(logs)

        # Send progress update
        yield f"data: {json.dumps({'type': 'progress', 'status': mission.status, 'progress': mission.progress})}\n\n"

        if mission.status in ("completed", "failed"):
            if mission.status == "completed":
                yield f"data: {json.dumps({'type': 'complete', 'report': mission.report, 'summary': mission.summary})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'message': mission.error_message})}\n\n"
            break

        await asyncio.sleep(2)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/missions")
async def create_mission(request: CreateMissionRequest):
    """Create a new research mission."""
    try:
        title = request.title if request.title else request.query[:50]
        mission = ResearchMission(
            title=title,
            query=request.query,
            notebook_id=request.notebook_id,
            depth=request.depth,
            model_override=request.model_override,
            status="planning",
        )
        await mission.save()
        return mission
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating research mission: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error creating research mission: {str(e)}"
        )


@router.get("/missions")
async def list_missions(
    notebook_id: Optional[str] = Query(None, description="Filter by notebook ID"),
):
    """List all research missions, optionally filtered by notebook."""
    try:
        if notebook_id:
            from open_notebook.database.repository import ensure_record_id, repo_query

            result = await repo_query(
                "SELECT * FROM research_mission WHERE notebook_id = $notebook_id ORDER BY created DESC",
                {"notebook_id": ensure_record_id(notebook_id)},
            )
            return [ResearchMission(**r) for r in result] if result else []
        else:
            missions = await ResearchMission.get_all(order_by="created DESC")
            return missions or []
    except Exception as e:
        logger.error(f"Error listing research missions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error listing research missions: {str(e)}",
        )


@router.get("/missions/{mission_id}")
async def get_mission(mission_id: str):
    """Get a research mission with its notes."""
    try:
        mission = await ResearchMission.get(mission_id)
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")

        notes = await mission.get_notes()
        return {"mission": mission, "notes": notes}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching mission {mission_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching mission: {str(e)}"
        )


@router.post("/missions/{mission_id}/start")
async def start_mission(mission_id: str):
    """Start a research mission. Runs the research graph asynchronously."""
    try:
        mission = await ResearchMission.get(mission_id)
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")

        mission.status = "planning"
        await mission.save()

        asyncio.create_task(run_research_mission(mission_id))

        return {"status": "planning", "mission_id": mission_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting mission {mission_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error starting mission: {str(e)}"
        )


@router.get("/missions/{mission_id}/stream")
async def stream_mission(mission_id: str):
    """Stream mission progress via Server-Sent Events."""
    try:
        mission = await ResearchMission.get(mission_id)
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")

        return StreamingResponse(
            stream_mission_progress(mission_id),
            media_type="text/event-stream",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming mission {mission_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error streaming mission: {str(e)}"
        )


@router.delete("/missions/{mission_id}")
async def delete_mission(mission_id: str):
    """Delete a research mission and all its notes."""
    try:
        mission = await ResearchMission.get(mission_id)
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")

        await mission.delete()
        return {"message": "Mission deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting mission {mission_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error deleting mission: {str(e)}"
        )


@router.get("/missions/{mission_id}/notes")
async def get_mission_notes(mission_id: str):
    """Get all research notes for a mission."""
    try:
        mission = await ResearchMission.get(mission_id)
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")

        notes = await mission.get_notes()
        return notes
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching notes for mission {mission_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching mission notes: {str(e)}"
        )
