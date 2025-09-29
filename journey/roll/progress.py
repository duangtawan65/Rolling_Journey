# rpg/progress.py  (ของคุณใช้ roll.* ก็ให้คง roll.*)
from __future__ import annotations
from typing import Optional, Dict, Any
from django.db import transaction
from django.utils import timezone
from roll.ai import resolve_effects

from roll.models import EventLog
from roll.enums import EventType, SessionStatus, ItemCode   # <- ตัด OutcomeType ออก
from roll.rules import (
    ITEM_MP_COST, HEAL_HP_AMOUNT,
    classify_turn, checkpoint_effects, clamp,
    make_roll, Progress, advance,
)

# ---------- utils ----------

def _log(player, session, etype: EventType, *, attrs: Optional[Dict[str, Any]] = None):
    EventLog.objects.create(
        ts=timezone.now(),
        player=player,
        session=session,
        type=etype,
        stage_index=session.stage_index,
        turn=session.turn,
        hp=player.hp,
        mp=player.mp,
        potions=(player.pot_heal + player.pot_boost),
        pot_heal_ct=player.pot_heal,
        pot_boost_ct=player.pot_boost,
        attrs=(attrs or {}),
    )

# ---------- core ----------

@transaction.atomic
def resolve_turn(
    *,
    session,
    player,
    action_text: str,
    use_mp: int = 0,
    use_heal: bool = False,
    use_boost: bool = False,
    rng: Optional[object] = None,
) -> Dict[str, Any]:

    kind = classify_turn(session.turn)

    if session.turn == 1:
        _log(player, session, EventType.STAGE_ENTER, attrs={"stage_index": session.stage_index})

    _log(player, session, EventType.TURN_START, attrs={"kind": kind, "action_text": action_text})

    if kind == "CHECKPOINT":
        heal_full, mp_pct, grant_pots = checkpoint_effects()
        if heal_full:
            player.hp = player.HP_MAX
        if mp_pct > 0:
            player.mp = clamp(player.mp + int(player.MP_MAX * (mp_pct / 100.0)), 0, player.MP_MAX)
        if grant_pots > 0:
            player.pot_heal += grant_pots
        player.save(update_fields=["hp", "mp", "pot_heal", "updated_at"])
        _log(player, session, EventType.CHECKPOINT, attrs={
            "heal_full": heal_full, "mp_pct": mp_pct, "grant_potions": grant_pots
        })

    boost_applied = False
    if kind == "FORCED_MP":
        _log(player, session, EventType.MANA_EVENT_OFFERED, attrs={"requested_mp": int(use_mp)})

    if use_heal and player.pot_heal > 0 and player.mp >= ITEM_MP_COST:
        player.mp -= ITEM_MP_COST
        player.pot_heal -= 1
        player.hp = clamp(player.hp + HEAL_HP_AMOUNT, 0, player.HP_MAX)
        player.save(update_fields=["hp", "mp", "pot_heal", "updated_at"])
        _log(player, session, EventType.ITEM_USED, attrs={
            "item": ItemCode.HEAL, "mp_cost": ITEM_MP_COST, "heal_amount": HEAL_HP_AMOUNT
        })
    else:
        if use_heal and (player.pot_heal <= 0 or player.mp < ITEM_MP_COST):
            use_heal = False

    if use_boost and player.pot_boost > 0 and player.mp >= ITEM_MP_COST:
        player.mp -= ITEM_MP_COST
        player.pot_boost -= 1
        boost_applied = True
        player.save(update_fields=["mp", "pot_boost", "updated_at"])
        _log(player, session, EventType.ITEM_USED, attrs={
            "item": ItemCode.BOOST, "mp_cost": ITEM_MP_COST, "boost_bonus": 5
        })
    else:
        if use_boost and (player.pot_boost <= 0 or player.mp < ITEM_MP_COST):
            use_boost = False

    roll = make_roll(
        turn=session.turn,
        mp_spent=int(use_mp),
        boost=bool(boost_applied),
        available_mp=player.mp,
        rng=rng,
    )

    ai = resolve_effects(
        session=session,
        player=player,
        roll=roll,
        action_text=action_text,
        kind=kind,
    )

    # apply เอฟเฟกต์จาก AI
    player.hp = clamp(player.hp + ai.hp_delta, 0, player.HP_MAX)
    player.mp = clamp(player.mp + ai.mp_delta, 0, player.MP_MAX)
    player.pot_heal  += ai.grant_heal
    player.pot_boost += ai.grant_boost
    player.save(update_fields=["hp", "mp", "pot_heal", "pot_boost", "updated_at"])

    # หัก MP ที่ใช้บัฟทอย
    if roll.mp_spent > 0:
        player.mp = clamp(player.mp - roll.mp_spent, 0, player.MP_MAX)
        player.save(update_fields=["mp", "updated_at"])

    if kind == "FORCED_MP":
        if roll.mp_spent > 0:
            _log(player, session, EventType.MANA_EVENT_ACCEPTED, attrs={"mp_spent": roll.mp_spent})
        else:
            _log(player, session, EventType.MANA_EVENT_DECLINED, attrs={"requested_mp": int(use_mp)})

    # << เพิ่มรวมผลจาก AI เข้า attrs เพื่อเก็บ narration/เดลต้าไว้ใน log >>
    _log(player, session, EventType.ACTION_RESULT, attrs={
        "action_text": action_text,
        "dice_roll": roll.dice_roll,
        "mp_spent_roll": roll.mp_spent,
        "mp_bonus": roll.mp_bonus,
        "boost_applied": roll.boost_applied,
        "boost_bonus": roll.boost_bonus,
        "total_roll": roll.total_roll,
        "outcome": roll.tier,
        **ai.to_attrs(),  # <--- สำคัญ
    })

    if player.hp <= 0:
        session.status = SessionStatus.DEAD
        session.ended_at = timezone.now()
        session.save(update_fields=["status", "ended_at", "updated_at"])
        _log(player, session, EventType.DEATH, attrs={"reason": "hp<=0"})
        _log(player, session, EventType.SESSION_END, attrs={"status": SessionStatus.DEAD})
        _log(player, session, EventType.TURN_END)
        return {
            "kind": kind,
            "roll": roll,
            "narration": ai.narration,    # <--- ส่งกลับให้ UI ใช้
            "dead": True,
            "cleared_stage": False,
            "cleared_game": False,
        }

    adv = advance(Progress(session.stage_index, session.turn))
    cleared_stage = adv.cleared_stage
    cleared_game = adv.cleared_game

    if cleared_stage:
        _log(player, session, EventType.STAGE_CLEAR, attrs={"stage_index": session.stage_index})

    if cleared_game:
        session.status = SessionStatus.CLEARED
        session.ended_at = timezone.now()
        session.save(update_fields=["status", "ended_at", "updated_at"])
        _log(player, session, EventType.CLEAR_GAME)
        _log(player, session, EventType.SESSION_END, attrs={"status": SessionStatus.CLEARED})
        _log(player, session, EventType.TURN_END)
        return {
            "kind": kind,
            "roll": roll,
            "narration": ai.narration,    # <--- ส่งกลับให้ UI ใช้
            "dead": False,
            "cleared_stage": True,
            "cleared_game": True,
        }

    session.stage_index = adv.progress.stage_index
    session.turn = adv.progress.turn
    session.save(update_fields=["stage_index", "turn", "updated_at"])

    if cleared_stage and session.turn == 1:
        _log(player, session, EventType.STAGE_ENTER, attrs={"stage_index": session.stage_index})

    _log(player, session, EventType.TURN_END)

    return {
        "kind": kind,
        "roll": roll,
        "narration": ai.narration,        # <--- ส่งกลับให้ UI ใช้
        "dead": False,
        "cleared_stage": cleared_stage,
        "cleared_game": False,
    }
