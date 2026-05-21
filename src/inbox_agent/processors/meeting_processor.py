import structlog

from inbox_agent.integrations.claude import ClaudeClient
from inbox_agent.integrations.notion import NotionClient
from inbox_agent.state import StateDB

logger = structlog.get_logger()


class MeetingProcessor:
    def __init__(
        self,
        notion: NotionClient,
        claude: ClaudeClient,
        state: StateDB,
        days_back: int = 7,
    ):
        self.notion = notion
        self.claude = claude
        self.state = state
        self.days_back = days_back

    def process(self) -> int:
        """Process recent meeting notes. Returns number of tasks created."""
        meetings = self.notion.get_recent_meetings(days_back=self.days_back)
        logger.info("meetings_fetched", count=len(meetings))

        tasks_created = 0

        for meeting in meetings:
            if self.state.is_meeting_processed(meeting.page_id):
                continue

            try:
                transcript = self.notion.get_page_text_content(meeting.page_id)
                if not transcript or len(transcript.strip()) < 50:
                    logger.info("meeting_skipped_empty", page_id=meeting.page_id)
                    self.state.record_meeting(meeting.page_id)
                    continue

                action_items = self.claude.extract_action_items(transcript)

                for item in action_items:
                    page_id = self.notion.create_task(
                        title=item["title"],
                        status="To dos",
                        source="meeting",
                        doability=item.get("doability", "Human-only"),
                        agent_notes=(
                            f"From meeting: {meeting.title}\n"
                            f"Assignee: {item.get('assignee', 'unspecified')}\n"
                            f"{item.get('reasoning', '')}"
                        ),
                    )
                    self.state.record_task(
                        page_id, "To dos", item.get("doability", "Human-only")
                    )
                    tasks_created += 1

                self.state.record_meeting(meeting.page_id)

            except Exception as e:
                logger.error(
                    "meeting_processing_failed", page_id=meeting.page_id, error=str(e)
                )
                self.state.record_meeting(meeting.page_id)

        return tasks_created
