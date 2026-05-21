import json

import anthropic
import structlog

logger = structlog.get_logger()

CLASSIFY_EMAIL_PROMPT = """\
You are an email triage assistant. Analyze this email and determine:
1. Whether it requires action (is "actionable") or is just informational/spam/newsletter
2. If actionable, what the task is (concise title)
3. How urgent it is (normal or urgent)
4. Whether this task is doable by an AI assistant

Respond with JSON only:
{
  "actionable": true/false,
  "task_title": "string or null",
  "urgent": true/false,
  "doability": "Human-only" | "Semi-Claude" | "Fully-Claude",
  "reasoning": "one sentence explaining doability classification"
}

Doability definitions:
- "Human-only": Requires physical presence, personal relationships, authority, signing documents, or access the AI doesn't have
- "Semi-Claude": AI can draft/research/prepare, but human must review, approve, or take final action
- "Fully-Claude": AI can complete this entirely (draft replies, summarize, research, write code, schedule)

Email:
From: {sender}
Subject: {subject}
Body: {body}
"""

EXTRACT_ACTIONS_PROMPT = """\
You are a meeting notes analyst. Extract all action items from this meeting transcript.

For each action item, provide:
1. A concise task title
2. Who it's assigned to (if mentioned, otherwise "unspecified")
3. Doability classification

Respond with JSON only:
{
  "action_items": [
    {
      "title": "string",
      "assignee": "string",
      "doability": "Human-only" | "Semi-Claude" | "Fully-Claude",
      "reasoning": "one sentence explaining doability"
    }
  ]
}

Doability definitions:
- "Human-only": Requires physical presence, personal relationships, authority, or access the AI doesn't have
- "Semi-Claude": AI can draft/research/prepare, but human must review or take final action
- "Fully-Claude": AI can complete this entirely (draft replies, summarize, research, write code)

Meeting transcript:
{transcript}
"""


class ClaudeClient:
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)

    def classify_email(self, sender: str, subject: str, body: str) -> dict:
        prompt = CLASSIFY_EMAIL_PROMPT.format(sender=sender, subject=subject, body=body[:3000])

        message = self.client.messages.create(
            model="claude-sonnet-4-6-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        text = message.content[0].text
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]

        result = json.loads(text)
        logger.info("email_classified", subject=subject, actionable=result["actionable"])
        return result

    def extract_action_items(self, transcript: str) -> list[dict]:
        prompt = EXTRACT_ACTIONS_PROMPT.format(transcript=transcript[:8000])

        message = self.client.messages.create(
            model="claude-sonnet-4-6-20250514",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )

        text = message.content[0].text
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]

        result = json.loads(text)
        items = result.get("action_items", [])
        logger.info("actions_extracted", count=len(items))
        return items

    def validate_connection(self) -> bool:
        try:
            self.client.messages.create(
                model="claude-sonnet-4-6-20250514",
                max_tokens=10,
                messages=[{"role": "user", "content": "Say 'ok'"}],
            )
            return True
        except Exception as e:
            logger.error("claude_validation_failed", error=str(e))
            return False
