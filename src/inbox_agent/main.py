import sys
import time

import structlog

from inbox_agent.config import load_settings
from inbox_agent.integrations.claude import ClaudeClient
from inbox_agent.integrations.notion import NotionClient
from inbox_agent.integrations.outlook import OutlookClient
from inbox_agent.processors.email_processor import EmailProcessor
from inbox_agent.processors.meeting_processor import MeetingProcessor
from inbox_agent.processors.task_monitor import TaskMonitor
from inbox_agent.state import StateDB


def configure_logging(level: str):
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(structlog, level.upper(), structlog.INFO)
        ),
    )


def run_sync_cycle():
    """Execute one full sync cycle."""
    settings = load_settings()
    configure_logging(settings.log_level)
    logger = structlog.get_logger()

    logger.info("sync_cycle_start")
    start = time.time()

    state = StateDB(settings.db_path)
    run_id = state.start_sync_run()

    outlook_enabled = bool(settings.ms_tenant_id and settings.ms_client_id)
    outlook = None
    if outlook_enabled:
        outlook = OutlookClient(
            tenant_id=settings.ms_tenant_id,
            client_id=settings.ms_client_id,
            client_secret=settings.ms_client_secret,
            token_path=settings.token_path,
        )

    notion = NotionClient(
        api_key=settings.notion_api_key,
        kanban_db_id=settings.notion_kanban_db_id,
        meetings_db_id=settings.notion_meetings_db_id,
    )
    claude = ClaudeClient(api_key=settings.anthropic_api_key)

    total_emails = 0
    total_tasks = 0
    total_errors = 0

    # Flow 1: Process emails (only if Outlook is configured)
    if outlook:
        try:
            email_proc = EmailProcessor(
                outlook=outlook,
                notion=notion,
                claude=claude,
                state=state,
                max_emails=settings.max_emails_per_run,
            )
            emails_processed, email_tasks = email_proc.process()
            total_emails = emails_processed
            total_tasks += email_tasks
        except Exception as e:
            logger.error("email_flow_failed", error=str(e))
            total_errors += 1
    else:
        logger.info("outlook_skipped", reason="not configured")

    # Flow 2: Process meeting notes
    try:
        meeting_proc = MeetingProcessor(
            notion=notion,
            claude=claude,
            state=state,
            days_back=settings.days_back_meetings,
        )
        meeting_tasks = meeting_proc.process()
        total_tasks += meeting_tasks
    except Exception as e:
        logger.error("meeting_flow_failed", error=str(e))
        total_errors += 1

    # Flow 3: Monitor completed tasks
    try:
        monitor = TaskMonitor(notion=notion, state=state)
        monitor.process_completed()
    except Exception as e:
        logger.error("task_monitor_failed", error=str(e))
        total_errors += 1

    state.finish_sync_run(run_id, total_emails, total_tasks, total_errors)
    state.close()

    elapsed = time.time() - start
    logger.info(
        "sync_cycle_complete",
        emails=total_emails,
        tasks_created=total_tasks,
        errors=total_errors,
        elapsed_seconds=round(elapsed, 1),
    )


def cli():
    """CLI entry point."""
    run_sync_cycle()


if __name__ == "__main__":
    try:
        run_sync_cycle()
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
