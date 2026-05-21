#!/usr/bin/env python3
"""Interactive setup for Inbox Agent.

Walks through API credential collection, validates connections,
initializes the database, and installs the launchd cron job.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_DIR / ".env"
PLIST_NAME = "com.jefflin.inbox-agent"
PLIST_SRC = PROJECT_DIR / "cron" / f"{PLIST_NAME}.plist"
PLIST_DEST = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_NAME}.plist"


def print_header(text: str):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def print_step(n: int, text: str):
    print(f"\n[Step {n}] {text}")
    print("-" * 40)


def prompt(label: str, secret: bool = False) -> str:
    if secret:
        import getpass
        return getpass.getpass(f"  {label}: ")
    return input(f"  {label}: ").strip()


def find_python() -> str:
    """Find a Python >= 3.11 interpreter."""
    candidates = ["python3.13", "python3.12", "python3.11"]
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path
    # Fall back to python3 and check version
    python3 = shutil.which("python3")
    if python3:
        result = subprocess.run(
            [python3, "-c", "import sys; print(sys.version_info[:2])"],
            capture_output=True, text=True,
        )
        version = eval(result.stdout.strip())
        if version >= (3, 11):
            return python3
    print("  ERROR: Python 3.11+ is required but not found.")
    print("  Install via: brew install python@3.13")
    sys.exit(1)


def setup_venv():
    print_step(1, "Setting up Python virtual environment")
    python = find_python()
    print(f"  Using: {python}")

    venv_path = PROJECT_DIR / ".venv"
    if venv_path.exists():
        print("  Virtual environment already exists, skipping.")
    else:
        subprocess.run([python, "-m", "venv", str(venv_path)], check=True)
        print("  Created .venv")

    pip = venv_path / "bin" / "pip"
    print("  Installing dependencies...")
    result = subprocess.run(
        [str(pip), "install", "-e", str(PROJECT_DIR)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  Install failed:\n{result.stderr}")
        sys.exit(1)
    print("  Dependencies installed.")
    return venv_path


def setup_microsoft_graph() -> dict:
    print_step(2, "Microsoft Graph (Outlook) Configuration")
    print("""
  To access your Outlook inbox, you need an Azure app registration:

  1. Go to https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade
  2. Click "+ New registration"
  3. Name: "Inbox Agent" (or anything you like)
  4. Supported account types: "Accounts in this organizational directory only"
     (or "Personal Microsoft accounts" if using a personal account)
  5. Redirect URI: leave blank (we use device-code flow)
  6. Click "Register"

  After registration:
  7. Copy the "Application (client) ID" and "Directory (tenant) ID" from the Overview page
  8. Go to "Certificates & secrets" → "+ New client secret" → copy the secret value
  9. Go to "API permissions" → "+ Add a permission" → "Microsoft Graph" →
     "Delegated permissions" → add: Mail.Read, Mail.ReadWrite
  10. Click "Grant admin consent" (if you have admin access)
""")
    input("  Press Enter when you've completed the steps above...")

    tenant_id = prompt("Tenant ID (Directory ID)")
    client_id = prompt("Client ID (Application ID)")
    client_secret = prompt("Client Secret", secret=True)

    return {
        "MS_TENANT_ID": tenant_id,
        "MS_CLIENT_ID": client_id,
        "MS_CLIENT_SECRET": client_secret,
    }


def setup_notion() -> dict:
    print_step(3, "Notion Configuration")
    print("""
  To connect to your Notion workspace:

  1. Go to https://www.notion.so/profile/integrations
  2. Click "+ New integration"
  3. Name: "Inbox Agent"
  4. Select your workspace
  5. Click "Submit" → copy the "Internal Integration Secret"

  Then share your databases with the integration:
  6. Open your Kanban board in Notion
  7. Click "..." menu → "Connections" → "Connect to" → select "Inbox Agent"
  8. Do the same for your Meeting Notes database

  To find database IDs:
  9. Open the database as a full page
  10. Copy the URL — the ID is the 32-character hex string before the "?v="
     Example: notion.so/myworkspace/abc123def456...?v=...
              The database ID is: abc123def456...
""")
    input("  Press Enter when you've completed the steps above...")

    api_key = prompt("Notion Integration Secret", secret=True)
    kanban_id = prompt("Kanban Board Database ID")
    meetings_id = prompt("Meeting Notes Database ID")

    return {
        "NOTION_API_KEY": api_key,
        "NOTION_KANBAN_DB_ID": kanban_id.replace("-", ""),
        "NOTION_MEETINGS_DB_ID": meetings_id.replace("-", ""),
    }


def setup_claude() -> dict:
    print_step(4, "Claude API Configuration")
    print("""
  Get your Anthropic API key:
  1. Go to https://console.anthropic.com/settings/keys
  2. Create a new key or copy an existing one
""")
    api_key = prompt("Anthropic API Key", secret=True)
    return {"ANTHROPIC_API_KEY": api_key}


def write_env_file(config: dict):
    print_step(5, "Writing .env configuration file")
    config.setdefault("LOG_LEVEL", "INFO")
    config.setdefault("MAX_EMAILS_PER_RUN", "50")
    config.setdefault("DAYS_BACK_MEETINGS", "7")

    lines = []
    for key, value in config.items():
        lines.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(lines) + "\n")
    print(f"  Written to {ENV_FILE}")


def validate_outlook(config: dict, venv_path: Path):
    print_step(6, "Authenticating with Outlook (device-code flow)")
    # Run the device-code auth via the installed package
    python = venv_path / "bin" / "python"
    script = f"""
import sys
sys.path.insert(0, '{PROJECT_DIR / "src"}')
from inbox_agent.integrations.outlook import OutlookClient
from pathlib import Path

client = OutlookClient(
    tenant_id="{config['MS_TENANT_ID']}",
    client_id="{config['MS_CLIENT_ID']}",
    client_secret="{config['MS_CLIENT_SECRET']}",
    token_path=Path("{PROJECT_DIR / '.tokens.json'}"),
)
success = client.authenticate_device_code()
sys.exit(0 if success else 1)
"""
    result = subprocess.run([str(python), "-c", script])
    if result.returncode != 0:
        print("  ERROR: Outlook authentication failed.")
        print("  You can re-run this setup later to retry.")
    else:
        print("  Outlook authentication successful!")


def validate_notion(config: dict, venv_path: Path) -> bool:
    print("\n  Validating Notion connection...")
    python = venv_path / "bin" / "python"
    script = f"""
import sys
sys.path.insert(0, '{PROJECT_DIR / "src"}')
from inbox_agent.integrations.notion import NotionClient

client = NotionClient(
    api_key="{config['NOTION_API_KEY']}",
    kanban_db_id="{config['NOTION_KANBAN_DB_ID']}",
    meetings_db_id="{config['NOTION_MEETINGS_DB_ID']}",
)
success = client.validate_connection()
sys.exit(0 if success else 1)
"""
    result = subprocess.run([str(python), "-c", script], capture_output=True, text=True)
    if result.returncode == 0:
        print("  Notion connection validated!")
        return True
    else:
        print("  WARNING: Notion validation failed. Check your database IDs and integration sharing.")
        print(f"  Error: {result.stderr}")
        return False


def validate_claude(config: dict, venv_path: Path) -> bool:
    print("\n  Validating Claude API connection...")
    python = venv_path / "bin" / "python"
    script = f"""
import sys
sys.path.insert(0, '{PROJECT_DIR / "src"}')
from inbox_agent.integrations.claude import ClaudeClient

client = ClaudeClient(api_key="{config['ANTHROPIC_API_KEY']}")
success = client.validate_connection()
sys.exit(0 if success else 1)
"""
    result = subprocess.run([str(python), "-c", script], capture_output=True, text=True)
    if result.returncode == 0:
        print("  Claude API connection validated!")
        return True
    else:
        print("  WARNING: Claude API validation failed. Check your API key.")
        return False


def init_database(venv_path: Path):
    print_step(7, "Initializing SQLite database")
    python = venv_path / "bin" / "python"
    script = f"""
import sys
sys.path.insert(0, '{PROJECT_DIR / "src"}')
from inbox_agent.state import StateDB
from pathlib import Path

db = StateDB(Path("{PROJECT_DIR / 'state.db'}"))
db.close()
print("  Database initialized at state.db")
"""
    subprocess.run([str(python), "-c", script], check=True)


def install_launchd():
    print_step(8, "Installing launchd cron job")

    if not PLIST_SRC.exists():
        print(f"  ERROR: Plist template not found at {PLIST_SRC}")
        return

    shutil.copy2(PLIST_SRC, PLIST_DEST)
    print(f"  Installed plist to {PLIST_DEST}")

    # Unload if already loaded, then load
    subprocess.run(["launchctl", "unload", str(PLIST_DEST)], capture_output=True)
    result = subprocess.run(["launchctl", "load", str(PLIST_DEST)], capture_output=True, text=True)
    if result.returncode == 0:
        print("  Launchd job loaded! Agent will run every 15 minutes.")
    else:
        print(f"  WARNING: Failed to load launchd job: {result.stderr}")
        print(f"  You can manually load with: launchctl load {PLIST_DEST}")


def run_first_sync(venv_path: Path):
    print_step(9, "Running first sync cycle")
    python = venv_path / "bin" / "python"
    result = subprocess.run(
        [str(python), "-m", "inbox_agent.main"],
        cwd=str(PROJECT_DIR),
        env={**os.environ, "PYTHONPATH": str(PROJECT_DIR / "src")},
    )
    if result.returncode == 0:
        print("\n  First sync completed successfully!")
    else:
        print("\n  First sync had errors — check the output above.")


def main():
    print_header("Inbox Agent Setup")
    print("This script will walk you through configuring the Inbox Agent.")
    print("You'll need your Notion workspace open in a browser.")

    # Step 1: venv
    venv_path = setup_venv()

    # Step 2: Outlook (optional)
    print_step(2, "Microsoft Graph (Outlook) — Optional")
    print("  Outlook integration requires an Azure app registration.")
    print("  If you don't have access (e.g. SSO-restricted), skip this.")
    print("  You can still add tasks manually or paste emails via the CLI.\n")
    outlook_choice = input("  Set up Outlook now? (y/n): ").strip().lower()

    ms_config = {}
    if outlook_choice == "y":
        ms_config = setup_microsoft_graph()
    else:
        print("  Skipping Outlook. You can set it up later by re-running this script.")
        ms_config = {
            "MS_TENANT_ID": "",
            "MS_CLIENT_ID": "",
            "MS_CLIENT_SECRET": "",
        }

    # Steps 3-4: Notion + Claude
    notion_config = setup_notion()
    claude_config = setup_claude()

    # Step 5: Write .env
    all_config = {**ms_config, **notion_config, **claude_config}
    write_env_file(all_config)

    # Step 6: Validate connections
    if outlook_choice == "y":
        validate_outlook(all_config, venv_path)
    validate_notion(all_config, venv_path)
    validate_claude(all_config, venv_path)

    # Step 7: Init DB
    init_database(venv_path)

    # Step 8: Install cron
    install_launchd()

    # Step 9: First run
    print("\n  Would you like to run the first sync cycle now?")
    choice = input("  (y/n): ").strip().lower()
    if choice == "y":
        run_first_sync(venv_path)

    print_header("Setup Complete!")
    print("  Your Inbox Agent is now configured and will run every 15 minutes.")
    print(f"  Logs: {PROJECT_DIR / 'logs/'}")
    print(f"  Database: {PROJECT_DIR / 'state.db'}")
    print(f"  Config: {ENV_FILE}")
    print()
    print("  Commands:")
    print(f"    Run sync:      {venv_path}/bin/python -m inbox_agent.main")
    print(f"    Add task:      {venv_path}/bin/python -m inbox_agent.cli add")
    print(f"    Process email: {venv_path}/bin/python -m inbox_agent.cli email")
    print(f"    Stop cron:     launchctl unload {PLIST_DEST}")
    print(f"    Start cron:    launchctl load {PLIST_DEST}")
    print()


if __name__ == "__main__":
    main()
