import json


_SESSION_KEY = "supabase_session_v1"
_LEGACY_TASKS_KEY = "todo_tasks_v1"
_LEGACY_MIGRATED_KEY = "todo_tasks_migrated_v1"


async def load_session(preferences):
    saved = await preferences.get(_SESSION_KEY)
    if not saved:
        return None
    try:
        session = json.loads(saved)
    except (TypeError, json.JSONDecodeError):
        return None
    return session if isinstance(session, dict) else None


async def save_session(preferences, session):
    data = {
        "access_token": session.get("access_token"),
        "refresh_token": session.get("refresh_token"),
        "user": session.get("user"),
    }
    await preferences.set(_SESSION_KEY, json.dumps(data))


async def clear_session(preferences):
    await preferences.remove(_SESSION_KEY)


async def legacy_tasks_migrated(preferences):
    return await preferences.get(_LEGACY_MIGRATED_KEY) is True


async def load_legacy_tasks(preferences):
    saved = await preferences.get(_LEGACY_TASKS_KEY)
    if not saved:
        return []
    try:
        records = json.loads(saved)
    except (TypeError, json.JSONDecodeError):
        return []
    return records if isinstance(records, list) else []


async def mark_legacy_tasks_migrated(preferences):
    await preferences.set(_LEGACY_MIGRATED_KEY, True)
    await preferences.remove(_LEGACY_TASKS_KEY)
