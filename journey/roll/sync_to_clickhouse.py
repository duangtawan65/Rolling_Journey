import os
import sys
from pathlib import Path
import django
import clickhouse_connect
from roll.models import EventLog

HERE = Path(__file__).resolve()
OUTER = HERE.parents[1]   # .../journey
ROOT = OUTER.parent       # .../Rolling_Journey

for p in (str(OUTER), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "journey.journey.settings")
django.setup()

def sync_event_logs(batch_size: int = 1000):
    client = clickhouse_connect.get_client(
        host="localhost", port=8123, username="default", password="1234"
    )

    qs = EventLog.objects.all().values(
        "ts", "player_id", "session_id", "type", "stage_index", "turn",
        "hp", "mp", "potions", "pot_heal_ct", "pot_boost_ct", "attrs"
    )

    buf, total = [], 0

    def flush():
        nonlocal buf, total
        if not buf:
            return
        client.insert(
            "event_log",
            buf,
            column_names=[
                "ts", "player_id", "session_id", "type", "stage_index", "turn",
                "hp", "mp", "potions", "pot_heal_ct", "pot_boost_ct", "attrs"
            ],
        )
        total += len(buf)
        buf = []

    for row in qs.iterator(chunk_size=batch_size):
        buf.append([
            row["ts"],
            int(row["player_id"]),
            str(row["session_id"]),
            row["type"],
            int(row["stage_index"]),
            int(row["turn"]),
            int(row["hp"]),
            int(row["mp"]),
            int(row["potions"]),
            int(row["pot_heal_ct"]),
            int(row["pot_boost_ct"]),
            row["attrs"] or {}
        ])
        if len(buf) >= batch_size:
            flush()

    flush()
    print("No event logs to sync." if total == 0 else f"✅ Inserted {total} rows into ClickHouse.")

if __name__ == "__main__":
    sync_event_logs()
