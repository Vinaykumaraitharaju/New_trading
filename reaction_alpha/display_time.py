from datetime import datetime
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


def indian_time(value: str | datetime | None) -> str | None:
    if not value:
        return None
    stamp = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    # Legacy naive timestamps were written in server-local time, not browser time.
    return stamp.astimezone(IST).strftime("%d %b %Y, %I:%M:%S %p IST")
