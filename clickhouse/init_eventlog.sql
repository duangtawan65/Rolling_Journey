-- สร้างครั้งเดียวตอนขึ้นคอนเทนเนอร์
CREATE TABLE IF NOT EXISTS event_log (
  ts DateTime DEFAULT now(),      -- EventLog.ts
  player_id UInt64,               -- FK -> Player.id (int/serial ใช้ UInt64 ปลอดภัย)
  session_id UUID,                -- Session.id
  type String,                    -- EventType (CharField)
  stage_index UInt8,              -- 1..10 ก็พอด้วย UInt8
  turn UInt8,                     -- 1..10
  hp Int32,
  mp Int32,
  potions Int32,
  pot_heal_ct Int32,
  pot_boost_ct Int32,
  attrs JSON                      -- Django JSONField
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(ts)
ORDER BY (ts, player_id, session_id);
