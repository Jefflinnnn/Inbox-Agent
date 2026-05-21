# Notion Integration Setup

## 1. Create Internal Integration

1. Go to [Notion Integrations](https://www.notion.so/profile/integrations)
2. Click **"+ New integration"**
3. Fill in:
   - **Name**: `Inbox Agent`
   - **Associated workspace**: Select your workspace
   - **Type**: Internal
4. Click **"Submit"**
5. Copy the **"Internal Integration Secret"** → this is your `NOTION_API_KEY`

## 2. Configure Capabilities

Under the integration settings, ensure these are enabled:
- **Read content** ✓
- **Update content** ✓
- **Insert content** ✓

## 3. Share Databases with Integration

For each database (Kanban board + Meeting Notes):
1. Open the database as a full page
2. Click **"..."** (three dots menu) in the top-right
3. Click **"Connections"**
4. Click **"Connect to"** → select **"Inbox Agent"**

## 4. Find Database IDs

1. Open your Kanban board as a full page in the browser
2. The URL looks like: `https://www.notion.so/myworkspace/abc123def456789...?v=...`
3. The **32-character hex string** before `?v=` is your database ID
4. Copy it → this is your `NOTION_KANBAN_DB_ID`
5. Repeat for your Meeting Notes database → `NOTION_MEETINGS_DB_ID`

## 5. Kanban Board Schema

The agent expects your board to have a **Status** property (it already does if it's a Board view).

Your existing columns:
- Nice to Haves
- To dos
- In progress
- Getting Anxiety please do this
- To be reviewed
- Completed

The agent will also create these properties on first use (Notion creates select options automatically):
- **Source** (select): `email`, `meeting`, `manual`
- **Doability** (select): `Human-only`, `Semi-Claude`, `Fully-Claude`

## Troubleshooting

- **"Could not find database"**: Make sure you shared the database with the integration (step 3)
- **"Invalid API key"**: Verify the secret starts with `ntn_` or `secret_`
- **Property errors**: The agent creates select options on first use — no manual setup needed
