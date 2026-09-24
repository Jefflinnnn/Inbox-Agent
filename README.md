# Inbox Agent

A personal AI assistant that watches your Outlook inbox and Notion meeting
notes, uses Claude to figure out what's actually actionable, and drops tasks
onto a Notion kanban board — tagged with how "doable" each one is and how
urgent it feels.

It runs on a 15-minute cron job (via macOS `launchd`), but Outlook is
optional: without it, you can still feed the agent tasks and forwarded emails
manually through a CLI.

## What it does

Each sync cycle runs three flows:

1. **Email triage** (skipped if Outlook isn't configured) — pulls unread
   emails from Outlook, asks Claude whether each one is actionable, and if so
   creates a Notion task. Urgent items go to a "Getting Anxiety please do
   this" column; everything else goes to "To dos". Already-seen emails are
   tracked in a local SQLite database so nothing gets processed twice.
2. **Meeting note parsing** — scans a Notion "meeting notes" database for
   recent pages, extracts action items from the transcript/notes with
   Claude, and creates a task per action item (with the assignee and
   reasoning noted).
3. **Task monitoring** — looks at tasks marked "Completed" on the kanban
   board that the agent itself created (from email or meeting sources) and
   archives them.

Every task Claude creates is labeled with a **doability** classification
(e.g. agent-doable vs. human-only) and includes Claude's reasoning, so you
can tell at a glance whether something needs your attention or could be
delegated.

## Architecture

```
src/inbox_agent/
├── main.py                     # Sync cycle entry point (the three flows above)
├── cli.py                      # Manual CLI: add a task, or paste/forward an email
├── config.py                   # Settings loaded from .env (pydantic-settings)
├── state.py                    # SQLite-backed dedupe/state tracking
├── integrations/
│   ├── outlook.py              # Microsoft Graph client (device-code auth)
│   ├── notion.py                # Notion API client (kanban + meeting notes)
│   └── claude.py                # Anthropic API client (classification/extraction)
└── processors/
    ├── email_processor.py      # Flow 1: email → task
    ├── meeting_processor.py    # Flow 2: meeting notes → tasks
    └── task_monitor.py         # Flow 3: archive completed agent-created tasks
```

State (which emails/meetings have been processed, which tasks are archived)
is kept in a local SQLite file (`state.db`) so re-runs are idempotent.

## Requirements

- Python 3.11+
- A Notion workspace with:
  - A kanban-style database for tasks (with a status property and columns
    like "To dos", "Getting Anxiety please do this", "Completed")
  - A database for meeting notes
- An [Anthropic API key](https://console.anthropic.com/settings/keys)
- (Optional) An Azure AD app registration with Microsoft Graph `Mail.Read` /
  `Mail.ReadWrite` permissions, if you want Outlook email triage

## Setup

The fastest way to get running is the interactive setup script:

```bash
python3 scripts/setup.py
```

This walks you through:

1. Creating a virtual environment and installing dependencies
2. (Optional) Configuring Microsoft Graph / Outlook via device-code auth
3. Configuring Notion (integration token + database IDs)
4. Configuring your Anthropic API key
5. Writing `.env`
6. Validating each connection
7. Initializing the local SQLite database
8. Installing a `launchd` job that runs the agent every 15 minutes
9. Optionally running a first sync immediately

See [`docs/microsoft_graph_setup.md`](docs/microsoft_graph_setup.md) and
[`docs/notion_setup.md`](docs/notion_setup.md) for detailed walkthroughs of
each integration's setup.

### Manual setup

If you'd rather configure things by hand, copy `.env.example` to `.env` and
fill in the values:

```bash
cp .env.example .env
pip install -e .
python -m inbox_agent.main
```

Leave `MS_TENANT_ID` / `MS_CLIENT_ID` / `MS_CLIENT_SECRET` blank to run
without Outlook — the email flow will simply be skipped.

## Usage

Run a sync cycle manually:

```bash
inbox-agent
# or: python -m inbox_agent.main
```

Add a task by hand (Claude classifies its doability):

```bash
inbox-agent-cli add "Renew the SSL cert for the staging server"
```

Paste or forward an email for Claude to triage and break into tasks:

```bash
inbox-agent-cli email --file forwarded_email.txt
# or run without --file to paste content interactively
```

### Automatic runs (macOS)

The setup script installs a `launchd` agent
(`cron/com.jefflin.inbox-agent.plist`) that runs the sync every 15 minutes.
Logs go to `logs/stdout.log` and `logs/stderr.log`. Manage it with:

```bash
launchctl load ~/Library/LaunchAgents/com.jefflin.inbox-agent.plist
launchctl unload ~/Library/LaunchAgents/com.jefflin.inbox-agent.plist
```

## Configuration reference

All configuration lives in `.env` (see `.env.example`):

| Variable | Required | Description |
|---|---|---|
| `MS_TENANT_ID` | No | Azure AD tenant ID — leave blank to skip Outlook |
| `MS_CLIENT_ID` | No | Azure app registration client ID |
| `MS_CLIENT_SECRET` | No | Azure app registration client secret |
| `NOTION_API_KEY` | Yes | Notion internal integration secret |
| `NOTION_KANBAN_DB_ID` | Yes | Database ID of your kanban board |
| `NOTION_MEETINGS_DB_ID` | Yes | Database ID of your meeting notes |
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `LOG_LEVEL` | No | Log verbosity (default `INFO`) |
| `MAX_EMAILS_PER_RUN` | No | Cap on emails processed per cycle (default `50`) |
| `DAYS_BACK_MEETINGS` | No | How far back to look for meeting notes (default `7`) |

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## Notes

- The agent only archives tasks it created itself (`source` of `email` or
  `meeting`) — manually created tasks on the board are left alone.
- Outlook auth uses device-code flow, so no redirect URI or web server is
  needed.
