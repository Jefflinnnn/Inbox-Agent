# Microsoft Graph (Outlook) Setup

## 1. Create Azure App Registration

1. Go to [Azure Portal - App registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)
2. Click **"+ New registration"**
3. Fill in:
   - **Name**: `Inbox Agent`
   - **Supported account types**: Choose based on your account:
     - Work/school account → "Accounts in this organizational directory only"
     - Personal Microsoft account → "Personal Microsoft accounts only"
   - **Redirect URI**: Leave blank (we use device-code flow)
4. Click **"Register"**

## 2. Note Your IDs

From the **Overview** page, copy:
- **Application (client) ID** → this is your `MS_CLIENT_ID`
- **Directory (tenant) ID** → this is your `MS_TENANT_ID`

For personal accounts, use `consumers` as the tenant ID.

## 3. Create Client Secret

1. Go to **"Certificates & secrets"** in the left sidebar
2. Click **"+ New client secret"**
3. Description: `inbox-agent`
4. Expiry: 24 months (you'll need to rotate before then)
5. Click **"Add"** → copy the **Value** (not the Secret ID) → this is your `MS_CLIENT_SECRET`

## 4. Configure API Permissions

1. Go to **"API permissions"** in the left sidebar
2. Click **"+ Add a permission"**
3. Select **"Microsoft Graph"**
4. Select **"Delegated permissions"**
5. Add these permissions:
   - `Mail.Read`
   - `Mail.ReadWrite`
   - `offline_access` (for refresh tokens)
6. If you have admin access, click **"Grant admin consent for [org]"**

## 5. Enable Device Code Flow

1. Go to **"Authentication"** in the left sidebar
2. Under **"Advanced settings"**, set **"Allow public client flows"** to **Yes**
3. Click **"Save"**

## Troubleshooting

- **"AADSTS700016"**: Wrong tenant ID. For personal accounts, use `consumers`.
- **"AADSTS65001"**: Permissions not consented. Re-run the device code flow and accept the consent prompt.
- **"AADSTS7000218"**: "Allow public client flows" not enabled. See step 5.
