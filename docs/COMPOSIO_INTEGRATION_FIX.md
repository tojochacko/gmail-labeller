# Composio Integration Fix - Summary

## Problem
The original code was trying to use a non-existent `get_toolkit()` method and outdated Composio API patterns that don't exist in the current SDK version.

## Solution
Updated the integration to use the correct Composio 1.0 API (composio 1.0.0-rc2 + composio-openai 0.9.1).

## Changes Made

### 1. Package Installation
- **Added**: `composio-openai==0.9.1` (framework-specific package)
- **Note**: The base `composio>=0.8.0` package alone doesn't include the helper classes needed

### 2. API Changes in `backend/app/services/gmail_toolkit.py`

#### Old API Pattern (v0.x - REMOVED):
```python
from composio import App, ComposioToolSet

toolset = ComposioToolSet(api_key=api_key)
entity = toolset.get_entity(id=entity_id)
connection_request = entity.initiate_connection(app=App.GMAIL)
result = toolset.execute_action(action=Action.GMAIL_FETCH_EMAILS)
```

#### New API Pattern (v1.0 - IMPLEMENTED):
```python
from composio import Composio

client = Composio(api_key=api_key)
connection_request = client.connected_accounts.initiate(
    user_id=user_id,
    auth_config_id=auth_config_id,
    callback_url=redirect_uri
)
result = client.tools.execute(
    slug="GMAIL_FETCH_EMAILS",
    arguments={"max_results": 20},
    connected_account_id=connected_account_id,
    user_id=user_id
)
```

### 3. Key API Differences

| Feature | Old API (v0.x) | New API (v1.0) |
|---------|---------------|----------------|
| Main Class | `ComposioToolSet` | `Composio` |
| User Isolation | `entity_id` | `user_id` + `auth_config_id` |
| OAuth Flow | `entity.initiate_connection(app=App.GMAIL)` | `client.connected_accounts.initiate(user_id, auth_config_id)` |
| Execute Actions | `execute_action(action=Action.GMAIL_FETCH_EMAILS)` | `tools.execute(slug="GMAIL_FETCH_EMAILS")` |
| Connection ID | Managed internally | Use `connected_account_id` or `user_id` |

### 4. Environment Variable Changes

The `COMPOSIO_ACCOUNT_ID` environment variable now represents the **auth_config_id** (not entity_id).

**What is auth_config_id?**
- It's the ID of your OAuth configuration in Composio
- You need to create a Gmail auth config in the Composio dashboard first
- Get it from: Composio Dashboard → Auth Configs → Gmail → Copy ID

## Setup Requirements

### 1. Create Gmail Auth Config in Composio

Before using this integration, you need to:

1. Log into your Composio dashboard: https://app.composio.dev
2. Navigate to **Auth Configs**
3. Create a new **Gmail** auth configuration with your Google OAuth credentials:
   - Client ID: From Google Cloud Console
   - Client Secret: From Google Cloud Console
   - Scopes: `https://www.googleapis.com/auth/gmail.modify`
4. Copy the **auth_config_id** that's generated
5. Set it as `COMPOSIO_ACCOUNT_ID` in your `.env` file

### 2. Update Environment Variables

```bash
# Required
COMPOSIO_API_KEY=your_composio_api_key
COMPOSIO_ACCOUNT_ID=your_gmail_auth_config_id  # This is now the auth_config_id!

# Google OAuth (still needed for callback handling)
GOOGLE_OAUTH_CLIENT_ID=your_google_client_id
GOOGLE_OAUTH_CLIENT_SECRET=your_google_client_secret
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/oauth/callback
```

### 3. Install Dependencies

```bash
uv sync  # Installs all dependencies including composio-openai
```

## How It Works Now

### OAuth Flow

1. **Start OAuth**: User clicks "Connect Gmail"
   - Backend calls `adapter.get_authorization_url(redirect_uri, state)`
   - Composio creates a connection request and returns Google's OAuth URL
   - User is redirected to Google for authorization

2. **OAuth Callback**: Google redirects back to your app
   - Composio automatically handles the token exchange
   - Backend calls `adapter.exchange_code_for_tokens(code, redirect_uri)`
   - Returns placeholder tokens (Composio manages real tokens internally)

3. **Using Gmail**: App needs to fetch emails
   - Backend calls `adapter.list_messages(access_token, refresh_token, max_results, user_id)`
   - Composio uses the `connected_account_id` or `user_id` to find the right connection
   - Executes the Gmail API call and returns results

## Testing the Integration

```bash
# Start the FastAPI backend
cd backend
uvicorn app.main:app --reload

# Test OAuth flow
curl -X POST http://localhost:8000/api/oauth/start \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test-user-123", "email": "test@example.com"}'

# Should return: {"authorization_url": "https://accounts.google.com/...", "state": "..."}
```

## Important Notes

### Token Management
- **Old approach**: You stored access_token and refresh_token in your database
- **New approach**: Composio manages tokens internally; you store the `connected_account_id`
- The `access_token` field now stores the Composio `connected_account_id` instead of the actual Google token

### User Isolation
- Each user in your system should have a unique `user_id` when calling Composio
- Composio tracks which connections belong to which users
- You can pass either `user_id` or `connected_account_id` to identify the connection to use

### Action Slugs
Common Gmail action slugs:
- `GMAIL_FETCH_EMAILS` - List messages
- `GMAIL_SEND_EMAIL` - Send an email
- `GMAIL_ADD_LABEL` - Add label to message
- `GMAIL_CREATE_DRAFT` - Create email draft
- Full list: https://app.composio.dev/tools/gmail

## Troubleshooting

### Error: "API Key not provided"
- Ensure `COMPOSIO_API_KEY` is set in your `.env` file
- The API key should start with `composio_`

### Error: "No connected account found"
- The user hasn't completed OAuth flow yet
- Or the `user_id` / `connected_account_id` doesn't match an existing connection
- Check Composio dashboard → Connected Accounts to verify

### Error: "Auth config not found"
- The `COMPOSIO_ACCOUNT_ID` (auth_config_id) is incorrect
- Create a Gmail auth config in Composio dashboard first

## Migration Checklist

- [x] Install `composio-openai` package
- [x] Update `ComposioGmailAdapter` to use Composio 1.0 API
- [x] Replace `ComposioToolSet` with `Composio`
- [x] Replace `entity_id` with `user_id` + `auth_config_id`
- [x] Update `execute_action` to `tools.execute`
- [x] Update action references from `Action.X` to `"X"` slugs
- [ ] Create Gmail auth config in Composio dashboard
- [ ] Update `COMPOSIO_ACCOUNT_ID` to use auth_config_id
- [ ] Test OAuth flow end-to-end
- [ ] Test Gmail operations (fetch, label, etc.)

## Additional Resources

- [Composio Documentation](https://docs.composio.dev/)
- [Composio Python SDK Reference](https://github.com/ComposioHQ/composio)
- [Gmail Integration Guide](https://app.composio.dev/tools/gmail)
