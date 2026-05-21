from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import structlog
from notion_client import Client

logger = structlog.get_logger()

KANBAN_STATUSES = [
    "Nice to Haves",
    "To dos",
    "In progress",
    "Getting Anxiety please do this",
    "To be reviewed",
    "Completed",
]

DOABILITY_OPTIONS = ["Human-only", "Semi-Claude", "Fully-Claude"]
SOURCE_OPTIONS = ["email", "meeting", "manual"]


@dataclass
class NotionTask:
    page_id: str
    title: str
    status: str
    source: str | None = None
    doability: str | None = None
    agent_notes: str | None = None


@dataclass
class MeetingPage:
    page_id: str
    title: str
    date: str
    content_blocks: list[str] = field(default_factory=list)


class NotionClient:
    def __init__(self, api_key: str, kanban_db_id: str, meetings_db_id: str):
        self.client = Client(auth=api_key)
        self.kanban_db_id = kanban_db_id
        self.meetings_db_id = meetings_db_id

    def create_task(
        self,
        title: str,
        status: str = "To dos",
        source: str = "manual",
        doability: str = "Human-only",
        agent_notes: str = "",
    ) -> str:
        """Create a task card on the kanban board. Returns the page ID."""
        properties = {
            "Name": {"title": [{"text": {"content": title}}]},
            "Status": {"status": {"name": status}},
        }

        # These are select properties — they'll be created automatically by Notion
        # if they don't exist yet on first use
        properties["Source"] = {"select": {"name": source}}
        properties["Doability"] = {"select": {"name": doability}}

        children = []
        if agent_notes:
            children.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": agent_notes}}],
                    "icon": {"type": "emoji", "emoji": "🤖"},
                },
            })

        response = self.client.pages.create(
            parent={"database_id": self.kanban_db_id},
            properties=properties,
            children=children if children else None,
        )
        logger.info("notion_task_created", title=title, page_id=response["id"])
        return response["id"]

    def get_tasks_by_status(self, status: str) -> list[NotionTask]:
        """Query kanban board for tasks with a given status."""
        response = self.client.databases.query(
            database_id=self.kanban_db_id,
            filter={"property": "Status", "status": {"equals": status}},
        )
        tasks = []
        for page in response.get("results", []):
            title_prop = page["properties"].get("Name", {}).get("title", [])
            title = title_prop[0]["plain_text"] if title_prop else "(untitled)"

            source_prop = page["properties"].get("Source", {}).get("select")
            doability_prop = page["properties"].get("Doability", {}).get("select")

            tasks.append(NotionTask(
                page_id=page["id"],
                title=title,
                status=status,
                source=source_prop["name"] if source_prop else None,
                doability=doability_prop["name"] if doability_prop else None,
            ))
        return tasks

    def archive_page(self, page_id: str):
        """Archive (soft-delete) a page."""
        self.client.pages.update(page_id=page_id, archived=True)
        logger.info("notion_page_archived", page_id=page_id)

    def get_recent_meetings(self, days_back: int = 7) -> list[MeetingPage]:
        """Get meeting pages created in the last N days."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()

        response = self.client.databases.query(
            database_id=self.meetings_db_id,
            filter={
                "property": "Created time",
                "created_time": {"on_or_after": cutoff},
            },
            sorts=[{"property": "Created time", "direction": "descending"}],
        )

        meetings = []
        for page in response.get("results", []):
            title_prop = page["properties"].get("Name", {}).get("title", [])
            if not title_prop:
                title_prop = page["properties"].get("Title", {}).get("title", [])
            title = title_prop[0]["plain_text"] if title_prop else "(untitled meeting)"

            meetings.append(MeetingPage(
                page_id=page["id"],
                title=title,
                date=page["created_time"],
            ))
        return meetings

    def get_page_text_content(self, page_id: str) -> str:
        """Extract all text content from a page's blocks (including transcript)."""
        blocks = self.client.blocks.children.list(block_id=page_id)
        text_parts = []

        for block in blocks.get("results", []):
            block_type = block["type"]
            block_data = block.get(block_type, {})

            rich_text = block_data.get("rich_text", [])
            for segment in rich_text:
                text_parts.append(segment.get("plain_text", ""))

            # Handle child blocks (toggles, etc.)
            if block.get("has_children"):
                child_text = self._get_child_text(block["id"])
                text_parts.append(child_text)

        return "\n".join(text_parts)

    def _get_child_text(self, block_id: str) -> str:
        blocks = self.client.blocks.children.list(block_id=block_id)
        parts = []
        for block in blocks.get("results", []):
            block_type = block["type"]
            block_data = block.get(block_type, {})
            for segment in block_data.get("rich_text", []):
                parts.append(segment.get("plain_text", ""))
        return "\n".join(parts)

    def validate_connection(self) -> bool:
        """Test that the API key and database IDs are valid."""
        try:
            self.client.databases.retrieve(database_id=self.kanban_db_id)
            self.client.databases.retrieve(database_id=self.meetings_db_id)
            return True
        except Exception as e:
            logger.error("notion_validation_failed", error=str(e))
            return False
