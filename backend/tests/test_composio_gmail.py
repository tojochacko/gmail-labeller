"""Test script to explore Composio Gmail actions."""

import os
from composio import Composio


def main():
    api_key = os.getenv("COMPOSIO_API_KEY")
    if not api_key:
        print("❌ COMPOSIO_API_KEY not set")
        return

    client: Composio = Composio(api_key=api_key)

    # Try to get action schema
    try:
        # List all actions
        print("🔍 Fetching Gmail actions...")
        actions = client.actions.list(app_slugs=["GMAIL"])  # type: ignore[attr-defined]

        print(f"\n📋 Found {len(actions.items)} Gmail actions")

        # Find email fetching actions
        fetch_actions = [
            a for a in actions.items if "FETCH" in a.name or "LIST" in a.name or "GET" in a.name
        ]

        print("\n📧 Email fetching actions:")
        for action in fetch_actions:
            print(f"\n  Action: {action.name}")
            if hasattr(action, "description"):
                print(f"  Description: {action.description}")

            # Try to get detailed schema
            try:
                schema = client.actions.get(action_id=action.name)  # type: ignore[attr-defined]
                if hasattr(schema, "parameters"):
                    print(f"  Parameters: {schema.parameters}")
            except Exception as e:
                print(f"  (Could not fetch schema: {e})")

        # List connected accounts
        print("\n\n🔗 Connected Accounts:")
        accounts = client.connected_accounts.list()
        if hasattr(accounts, "items"):
            for acc in accounts.items:
                print(f"  - ID: {acc.id}")
                print(f"    Status: {acc.status}")
                if hasattr(acc, "user_id"):
                    print(f"    User ID: {acc.user_id}")
                if hasattr(acc, "app_id"):
                    print(f"    App ID: {acc.app_id}")
        else:
            print("  No connected accounts found")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
