"""CLI for manually adding tasks and processing pasted emails."""

import argparse
import sys

from inbox_agent.config import load_settings
from inbox_agent.integrations.claude import ClaudeClient
from inbox_agent.integrations.notion import NotionClient
from inbox_agent.state import StateDB


def cmd_add(args):
    """Add a task directly. Claude classifies doability."""
    settings = load_settings()
    claude = ClaudeClient(api_key=settings.anthropic_api_key)
    notion = NotionClient(
        api_key=settings.notion_api_key,
        kanban_db_id=settings.notion_kanban_db_id,
        meetings_db_id=settings.notion_meetings_db_id,
    )
    state = StateDB(settings.db_path)

    if args.task:
        task_text = " ".join(args.task)
    else:
        print("Enter task description (press Enter when done):")
        task_text = input("> ").strip()

    if not task_text:
        print("No task provided.")
        return

    print(f"\nClassifying: \"{task_text}\"...")
    classification = claude.classify_email(
        sender="manual",
        subject=task_text,
        body=task_text,
    )

    doability = classification.get("doability", "Human-only")
    reasoning = classification.get("reasoning", "")

    print(f"  Doability: {doability}")
    print(f"  Reasoning: {reasoning}")

    page_id = notion.create_task(
        title=task_text,
        status="To dos",
        source="manual",
        doability=doability,
        agent_notes=reasoning,
    )
    state.record_task(page_id, "To dos", doability)
    state.close()
    print(f"\n  Created task on Notion board.")


def cmd_email(args):
    """Paste an email for Claude to break down into tasks."""
    settings = load_settings()
    claude = ClaudeClient(api_key=settings.anthropic_api_key)
    notion = NotionClient(
        api_key=settings.notion_api_key,
        kanban_db_id=settings.notion_kanban_db_id,
        meetings_db_id=settings.notion_meetings_db_id,
    )
    state = StateDB(settings.db_path)

    if args.file:
        from pathlib import Path
        content = Path(args.file).read_text()
        # Try to parse sender/subject from headers
        sender, subject, body = _parse_email_text(content)
    else:
        print("Paste the email content below.")
        print("(Enter a blank line when done)\n")
        lines = []
        while True:
            try:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
            except EOFError:
                break
        content = "\n".join(lines)
        sender, subject, body = _parse_email_text(content)

    if not body.strip():
        print("No email content provided.")
        return

    print(f"\n  From: {sender}")
    print(f"  Subject: {subject}")
    print(f"\n  Classifying email...")

    classification = claude.classify_email(sender=sender, subject=subject, body=body)

    if not classification.get("actionable"):
        print("  Result: Not actionable (informational/spam/newsletter)")
        return

    print(f"  Actionable: Yes")
    print(f"  Task: {classification.get('task_title', subject)}")
    print(f"  Urgent: {classification.get('urgent', False)}")
    print(f"  Doability: {classification.get('doability', 'Human-only')}")
    print(f"  Reasoning: {classification.get('reasoning', '')}")

    status = (
        "Getting Anxiety please do this"
        if classification.get("urgent")
        else "To dos"
    )
    page_id = notion.create_task(
        title=classification.get("task_title", subject),
        status=status,
        source="email",
        doability=classification.get("doability", "Human-only"),
        agent_notes=f"From: {sender}\n{classification.get('reasoning', '')}",
    )
    state.record_task(page_id, status, classification.get("doability", "Human-only"))
    state.close()
    print(f"\n  Created task on Notion board.")


def _parse_email_text(text: str) -> tuple[str, str, str]:
    """Best-effort extraction of sender/subject from pasted email text."""
    sender = "unknown"
    subject = "(no subject)"
    body_start = 0

    lines = text.split("\n")
    for i, line in enumerate(lines):
        lower = line.lower()
        if lower.startswith("from:"):
            sender = line[5:].strip()
        elif lower.startswith("subject:"):
            subject = line[8:].strip()
        elif line.strip() == "" and i > 0:
            body_start = i + 1
            break

    body = "\n".join(lines[body_start:]) if body_start else text
    return sender, subject, body


def main():
    parser = argparse.ArgumentParser(description="Inbox Agent CLI")
    subparsers = parser.add_subparsers(dest="command")

    # inbox-agent add "my task description"
    add_parser = subparsers.add_parser("add", help="Add a task manually")
    add_parser.add_argument("task", nargs="*", help="Task description")

    # inbox-agent email --file email.txt
    email_parser = subparsers.add_parser("email", help="Process a pasted/forwarded email")
    email_parser.add_argument("--file", "-f", help="Read email from a file instead of stdin")

    args = parser.parse_args()

    if args.command == "add":
        cmd_add(args)
    elif args.command == "email":
        cmd_email(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
