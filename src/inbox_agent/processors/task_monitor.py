import structlog

from inbox_agent.integrations.notion import NotionClient
from inbox_agent.state import StateDB

logger = structlog.get_logger()


class TaskMonitor:
    def __init__(self, notion: NotionClient, state: StateDB):
        self.notion = notion
        self.state = state

    def process_completed(self) -> int:
        """Archive completed tasks. Returns number archived."""
        completed_tasks = self.notion.get_tasks_by_status("Completed")
        logger.info("completed_tasks_found", count=len(completed_tasks))

        archived = 0
        for task in completed_tasks:
            if self.state.is_task_archived(task.page_id):
                continue

            # Only archive tasks that were created by this agent
            if task.source in ("email", "meeting"):
                self.notion.archive_page(task.page_id)
                self.state.mark_task_completed(task.page_id)
                archived += 1
                logger.info("task_archived", title=task.title)

        return archived
