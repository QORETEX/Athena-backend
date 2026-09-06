#!/usr/bin/env python3
"""
Populate the Athena backend with dummy data for testing
Run this with the server running on http://localhost:8000
"""
import asyncio
import sys
from httpx import AsyncClient
from tests.dummy_data import DummyDataGenerator


async def populate_data():
    """Populate the database with dummy data."""
    base_url = "http://localhost:8000"

    try:
        async with AsyncClient(base_url=base_url, timeout=30.0) as client:
            print("=" * 70)
            print("Athena Backend - Dummy Data Population Tool")
            print("=" * 70)
            print(f"Target: {base_url}\n")

            # Check if server is running
            try:
                health_response = await client.get("/health")
                if health_response.status_code != 200:
                    print("❌ Server is not responding properly")
                    return False
                print("✓ Server is running\n")
            except Exception as e:
                print(f"❌ Cannot connect to server at {base_url}")
                print(f"   Error: {e}")
                print("\n💡 Make sure the server is running:")
                print("   python main.py")
                return False

            gen = DummyDataGenerator()

            # Populate Reminders
            print("📝 Creating Reminders...")
            reminders = gen.reminders(10)
            reminder_count = 0
            for reminder in reminders:
                try:
                    response = await client.post("/reminders", json=reminder)
                    if response.status_code == 200:
                        data = response.json()
                        print(f"  ✓ [{data['id']}] {reminder['text']}")
                        reminder_count += 1
                except Exception as e:
                    print(f"  ✗ Failed: {e}")
            print(f"  → Created {reminder_count} reminders\n")

            # Populate Notes
            print("📄 Creating Notes...")
            notes = gen.notes(10)
            notes_count = 0
            for note in notes:
                try:
                    response = await client.post("/notes", json=note)
                    if response.status_code == 200:
                        data = response.json()
                        preview = note['content'][:50] + "..." if len(note['content']) > 50 else note['content']
                        print(f"  ✓ [{data['id']}] {preview}")
                        notes_count += 1
                except Exception as e:
                    print(f"  ✗ Failed: {e}")
            print(f"  → Created {notes_count} notes\n")

            # Populate User Preferences
            print("⚙️  Setting User Preferences...")
            preferences = gen.user_preferences()
            pref_count = 0
            for key, value in preferences.items():
                try:
                    response = await client.put(
                        f"/preferences/{key}",
                        json={"value": value}
                    )
                    if response.status_code in [200, 201]:
                        print(f"  ✓ {key} = {value}")
                        pref_count += 1
                except Exception as e:
                    print(f"  ✗ Failed to set {key}: {e}")
            print(f"  → Set {pref_count} preferences\n")

            # Summary
            print("=" * 70)
            print("Summary:")
            print(f"  • {reminder_count} reminders created")
            print(f"  • {notes_count} notes created")
            print(f"  • {pref_count} preferences set")
            print("=" * 70)
            print("\n✅ Database populated with dummy data!")
            print("\n💡 You can now test the API:")
            print(f"   curl {base_url}/reminders")
            print(f"   curl {base_url}/notes")
            print(f"   curl {base_url}/preferences")

            return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


async def clear_data():
    """Clear all test data from the database."""
    base_url = "http://localhost:8000"

    print("=" * 70)
    print("Clearing all data from Athena backend...")
    print("=" * 70)

    try:
        async with AsyncClient(base_url=base_url, timeout=30.0) as client:
            # Get and delete all reminders
            response = await client.get("/reminders")
            if response.status_code == 200:
                reminders = response.json()
                for reminder in reminders:
                    await client.delete(f"/reminders/{reminder['id']}")
                print(f"✓ Deleted {len(reminders)} reminders")

            # Get and delete all notes
            response = await client.get("/notes")
            if response.status_code == 200:
                notes = response.json()
                for note in notes:
                    await client.delete(f"/notes/{note['id']}")
                print(f"✓ Deleted {len(notes)} notes")

            print("\n✅ Data cleared!")

    except Exception as e:
        print(f"❌ Error: {e}")


async def show_stats():
    """Show current database statistics."""
    base_url = "http://localhost:8000"

    print("=" * 70)
    print("Current Database Statistics")
    print("=" * 70)

    try:
        async with AsyncClient(base_url=base_url, timeout=30.0) as client:
            # Count reminders
            response = await client.get("/reminders")
            if response.status_code == 200:
                reminders = response.json()
                completed = sum(1 for r in reminders if r.get('completed', False))
                print(f"📝 Reminders: {len(reminders)} total, {completed} completed")

            # Count notes
            response = await client.get("/notes")
            if response.status_code == 200:
                notes = response.json()
                print(f"📄 Notes: {len(notes)} total")

            # Health check
            response = await client.get("/health")
            if response.status_code == 200:
                health = response.json()
                print(f"💚 Status: {health.get('status', 'unknown')}")
                print(f"📦 Version: {health.get('version', 'unknown')}")

            print("=" * 70)

    except Exception as e:
        print(f"❌ Error: {e}")


def print_help():
    """Print usage help."""
    print("""
Athena Backend - Dummy Data Population Tool

Usage:
    python populate_dummy_data.py [command]

Commands:
    populate    Populate database with dummy data (default)
    clear       Clear all data from database
    stats       Show current database statistics
    help        Show this help message

Examples:
    python populate_dummy_data.py
    python populate_dummy_data.py populate
    python populate_dummy_data.py clear
    python populate_dummy_data.py stats

Note: The server must be running on http://localhost:8000
      Start it with: python main.py
    """)


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "populate"

    if command == "help":
        print_help()
    elif command == "populate":
        success = asyncio.run(populate_data())
        sys.exit(0 if success else 1)
    elif command == "clear":
        asyncio.run(clear_data())
    elif command == "stats":
        asyncio.run(show_stats())
    else:
        print(f"Unknown command: {command}")
        print("Run 'python populate_dummy_data.py help' for usage")
        sys.exit(1)
