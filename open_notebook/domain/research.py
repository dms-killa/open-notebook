from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional, Union

from loguru import logger
from pydantic import Field, field_validator
from surrealdb import RecordID

from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.base import ObjectModel
from open_notebook.exceptions import DatabaseOperationError, InvalidInputError


class ResearchMission(ObjectModel):
    table_name: ClassVar[str] = "research_mission"
    nullable_fields: ClassVar[set[str]] = {
        "summary",
        "status",
        "report",
        "plan",
        "execution_log",
        "notebook_id",
    }

    title: str
    query: str
    notebook_id: Optional[Union[str, RecordID]] = None
    status: Optional[str] = "planning"
    depth: Optional[str] = "comprehensive"
    plan: Optional[Dict[str, Any]] = None
    report: Optional[str] = None
    summary: Optional[str] = None
    execution_log: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    model_override: Optional[str] = None
    progress: Optional[int] = 0
    error_message: Optional[str] = None

    @field_validator("notebook_id", mode="before")
    @classmethod
    def parse_notebook_id(cls, value):
        """Parse notebook_id field to ensure RecordID format"""
        if isinstance(value, str) and value:
            return ensure_record_id(value)
        return value

    @field_validator("title")
    @classmethod
    def title_must_not_be_empty(cls, v):
        if not v.strip():
            raise InvalidInputError("Mission title cannot be empty")
        return v

    @field_validator("query")
    @classmethod
    def query_must_not_be_empty(cls, v):
        if not v.strip():
            raise InvalidInputError("Mission query cannot be empty")
        return v

    async def get_notes(self) -> List["ResearchNote"]:
        """Get all research notes for this mission."""
        try:
            result = await repo_query(
                "SELECT * FROM research_note WHERE mission_id = $mission_id ORDER BY created ASC",
                {"mission_id": ensure_record_id(self.id)},
            )
            return [ResearchNote(**note) for note in result] if result else []
        except Exception as e:
            logger.error(
                f"Error fetching notes for mission {self.id}: {str(e)}"
            )
            logger.exception(e)
            raise DatabaseOperationError(e)

    async def add_note(
        self,
        phase: str,
        content: str,
        source_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ResearchNote":
        """Add a research note to this mission."""
        note = ResearchNote(
            mission_id=ensure_record_id(self.id),
            phase=phase,
            content=content,
            source_type=source_type,
            metadata=metadata,
        )
        await note.save()
        return note

    async def add_log_entry(
        self,
        phase: str,
        agent: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append an entry to the execution log and save."""
        if self.execution_log is None:
            self.execution_log = []
        entry: Dict[str, Any] = {
            "phase": phase,
            "agent": agent,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        }
        if details:
            entry["details"] = details
        self.execution_log.append(entry)
        await self.save()

    async def delete(self) -> bool:
        """Delete mission and cascade delete all associated notes."""
        if self.id is None:
            raise InvalidInputError("Cannot delete mission without an ID")
        try:
            # Delete all associated research notes
            notes = await self.get_notes()
            for note in notes:
                await note.delete()
            logger.info(
                f"Deleted {len(notes)} research notes for mission {self.id}"
            )

            # Delete the mission record itself
            return await super().delete()
        except Exception as e:
            logger.error(f"Error deleting mission {self.id}: {str(e)}")
            logger.exception(e)
            raise DatabaseOperationError(
                f"Failed to delete research mission: {str(e)}"
            )


class ResearchNote(ObjectModel):
    table_name: ClassVar[str] = "research_note"
    nullable_fields: ClassVar[set[str]] = {"metadata", "source_url"}

    mission_id: Union[str, RecordID]
    phase: str
    content: str
    source_type: Optional[str] = None
    source_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("mission_id", mode="before")
    @classmethod
    def parse_mission_id(cls, value):
        """Parse mission_id field to ensure RecordID format"""
        if isinstance(value, str) and value:
            return ensure_record_id(value)
        return value

    @field_validator("content")
    @classmethod
    def content_must_not_be_empty(cls, v):
        if not v.strip():
            raise InvalidInputError("Research note content cannot be empty")
        return v
