import structlog

from inbox_agent.integrations.claude import ClaudeClient
from inbox_agent.integrations.notion import NotionClient
from inbox_agent.integrations.outlook import OutlookClient
from inbox_agent.state import StateDB

logger = structlog.get_logger()


class EmailProcessor:
    def __init__(
        self,
        outlook: OutlookClient,
        notion: NotionClient,
        claude: ClaudeClient,
        state: StateDB,
        max_emails: int = 50,
    ):
        self.outlook = outlook
        self.notion = notion
        self.claude = claude
        self.state = state
        self.max_emails = max_emails

    def process(self) -> tuple[int, int]:
        """Process unread emails. Returns (emails_processed, tasks_created)."""
        emails = self.outlook.get_unread_emails(limit=self.max_emails)
        logger.info("emails_fetched", count=len(emails))

        processed = 0
        tasks_created = 0

        for email in emails:
            email_hash = StateDB.hash_email(email.sender, email.subject, email.received_at[:10])

            if self.state.is_email_processed(email_hash):
                self.outlook.mark_as_read(email.id)
                continue

            try:
                classification = self.claude.classify_email(
                    sender=email.sender,
                    subject=email.subject,
                    body=email.body_preview or email.body[:2000],
                )

                if classification.get("actionable"):
                    status = (
                        "Getting Anxiety please do this"
                        if classification.get("urgent")
                        else "To dos"
                    )
                    page_id = self.notion.create_task(
                        title=classification.get("task_title", email.subject),
                        status=status,
                        source="email",
                        doability=classification.get("doability", "Human-only"),
                        agent_notes=f"From: {email.sender}\n{classification.get('reasoning', '')}",
                    )
                    self.state.record_email(email_hash, page_id)
                    self.state.record_task(page_id, status, classification.get("doability", "Human-only"))
                    tasks_created += 1
                else:
                    self.state.record_email(email_hash)

                self.outlook.mark_as_read(email.id)
                processed += 1

            except Exception as e:
                logger.error("email_processing_failed", email_id=email.id, error=str(e))
                self.state.record_email(email_hash)

        return processed, tasks_created
