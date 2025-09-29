from django.db import models

class SessionStatus(models.TextChoices):
    ACTIVE  = "ACTIVE",  "Active"
    DEAD    = "DEAD",    "Dead"
    ESCAPED = "ESCAPED", "Escaped"
    CLEARED = "CLEARED", "Cleared"

class EventType(models.TextChoices):
    # Session lifecycle
    SESSION_START  = "session_start",  "Session Start"
    SESSION_END    = "session_end",    "Session End"
    CLEAR_GAME     = "clear_game",     "Clear Game"   # จบเกมแบบเคลียร์

    # Stage flow
    STAGE_ENTER    = "stage_enter",    "Stage Enter"
    STAGE_CLEAR    = "stage_clear",    "Stage Clear"

    # Turn flow
    TURN_START     = "turn_start",     "Turn Start"
    TURN_END       = "turn_end",       "Turn End"
    # (deprecated) ใช้ TURN_START/END แทน
    TURN_TICK      = "turn_tick",      "Turn Tick"

    # Player ↔ Narrator I/O
    MSG_USER       = "msg_user",       "Message (User)"   # ข้อความ/คำสั่งจากผู้เล่น

    # Actions & items
    ACTION_ATTEMPT = "action_attempt", "Action Attempt"
    ACTION_RESULT  = "action_result",  "Action Result"
    ITEM_USED      = "item_used",      "Item Used"

    # Mana event @ stage 3/6/9
    MANA_EVENT_OFFERED  = "mana_event_offered",  "Mana Event Offered"
    MANA_EVENT_ACCEPTED = "mana_event_accepted", "Mana Event Accepted"
    MANA_EVENT_DECLINED = "mana_event_declined", "Mana Event Declined"

    # Escape (ถ้าเกมมีคำสั่งหนี)
    ESCAPE_ATTEMPT = "escape_attempt", "Escape Attempt"
    ESCAPE_RESULT  = "escape_result",  "Escape Result"

    # Outcomes / terminal
    CHECKPOINT     = "checkpoint",     "Checkpoint"
    DEATH          = "death",          "Death"

    # System
    ERROR          = "error",          "Error"

class TemplateKind(models.TextChoices):
    NORMAL   = "NORMAL",    "Normal"
    FORCEDMP = "FORCED_MP", "Forced MP"
    BOSS     = "BOSS",      "Boss"
    TRAP     = "TRAP",      "Trap"
    NARR     = "NARR",      "Narrative"

class OutcomeType(models.TextChoices):
    FAIL    = "fail",    "Fail"
    NEUTRAL = "neutral", "Neutral"
    SUCCESS = "success", "Success"
    GREAT   = "great",   "Great Success"

class ItemCode(models.TextChoices):
    HEAL  = "HEAL",  "Heal Potion"
    BOOST = "BOOST", "Boost Charm (+5)"
