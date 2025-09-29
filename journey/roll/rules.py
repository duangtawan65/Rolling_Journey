# rpg/rules.py
from __future__ import annotations
from dataclasses import dataclass
import random
from typing import Literal, Tuple, Optional

# -----------------------------
# ค่าคงที่ของเกม (แก้ได้จุดเดียว)
# -----------------------------
STAGES_TOTAL: int   = 10            # ทั้งเกมมี 10 ด่าน
TURNS_PER_STAGE: int = 10           # ด่านละ 10 แชท
CHECKPOINT_TURNS = {1, 5}           # เทิร์นที่เป็นจุดพัก
FORCED_MP_TURNS  = {3, 6, 9}        # เทิร์นที่อนุญาต/เสนอให้ใช้ MP เพื่อบัฟทอย

# ลูกเต๋า & บัฟ
DICE_MIN, DICE_MAX = 1, 20
MP_BONUS_PER_POINT = 5              # ใช้ MP 1 = +5 แต้มทอย
BOOST_ROLL_BONUS   = 5              # ใช้ไอเท็ม BOOST ได้ +5 แต้มทอย (ต่อเทิร์น)

ITEM_MP_COST   = 1                  # ใช้ไอเท็ม เสีย MP 1
HEAL_HP_AMOUNT = 10                 # ใช้ HEAL ได้ +10 HP

# เกณฑ์ผลทอย → Outcome tiers
# 1–5=fail, 6–12=neutral, 13–17=success, 18–20=great (>20 ยังคง "great")
OUTCOME_BOUNDS = {
    "fail":    (1, 5),
    "neutral": (6, 12),
    "success": (13, 17),
    "great":   (18, 20),
}

# ผล checkpoint (ปรับได้ตามกติกาคุณ)
CHECKPOINT_HEAL_HP_FULL: bool = True
CHECKPOINT_RESTORE_MP_PCT: int = 50  # +50% ของ MP MAX (ให้ service ไป clamp เอง)
CHECKPOINT_GRANT_POTIONS: int = 1

# -----------------------------
# ชนิด turn
# -----------------------------
TurnKind = Literal["CHECKPOINT", "FORCED_MP", "NORMAL", "BOSS"]

def is_checkpoint_turn(turn: int) -> bool:
    return turn in CHECKPOINT_TURNS

def is_forced_mp_turn(turn: int) -> bool:
    return turn in FORCED_MP_TURNS

def is_boss_turn(turn: int) -> bool:
    return turn == TURNS_PER_STAGE  # เทิร์นที่ 10 = จบด่าน/บอส

def classify_turn(turn: int) -> TurnKind:
    if is_checkpoint_turn(turn):
        return "CHECKPOINT"
    if is_forced_mp_turn(turn):
        return "FORCED_MP"
    if is_boss_turn(turn):
        return "BOSS"
    return "NORMAL"

# -----------------------------
# ลูกเต๋า & ตัวช่วย outcome
# -----------------------------
@dataclass
class RollResult:
    dice_roll: int      # ผลทอยดิบ 1..20
    mp_spent: int       # ใช้ MP ไปกี่แต้ม "กับการทอย" (ไม่รวม MP ค่าใช้ไอเท็ม)
    boost_applied: bool # ใช้ BOOST ในเทิร์นนี้หรือไม่
    mp_bonus: int       # แต้มบวกจาก MP = mp_spent*MP_BONUS_PER_POINT
    boost_bonus: int    # แต้มบวกจาก BOOST (= BOOST_ROLL_BONUS หรือ 0)
    total_roll: int     # dice_roll + mp_bonus + boost_bonus
    tier: Literal["fail", "neutral", "success", "great"]

def rng_from_seed(seed: Optional[int]) -> random.Random:
    """สร้าง RNG เฉพาะ (ไม่ไปรบกวน global random) สำหรับรีเพลย์/ดีบัก"""
    return random.Random(seed) if seed is not None else random

def roll_d20(rng: Optional[random.Random] = None) -> int:
    r = rng or random
    return r.randint(DICE_MIN, DICE_MAX)

def apply_mp_bonus(dice_roll: int, mp_spent: int, boost: bool = False) -> int:
    """คำนวณแต้มรวมหลังบัฟ MP + BOOST (ฟังก์ชันภายใน; ใช้ make_roll แทนด้านนอก)"""
    mp_spent = max(0, int(mp_spent))
    total = dice_roll + mp_spent * MP_BONUS_PER_POINT
    if boost:
        total += BOOST_ROLL_BONUS
    return total

def tier_from_total(total_roll: int) -> Literal["fail", "neutral", "success", "great"]:
    for name, (lo, hi) in OUTCOME_BOUNDS.items():
        if lo <= total_roll <= hi:
            return name  # type: ignore[return-value]
    if total_roll < OUTCOME_BOUNDS["fail"][0]:
        return "fail"   # type: ignore[return-value]
    return "great"      # type: ignore[return-value]

def sanitize_mp_spend(turn: int, requested_mp: int, available_mp: int) -> int:
    """
    บังคับกติกา: ใช้ MP เพื่อบัฟทอยได้เฉพาะเทิร์นใน FORCED_MP_TURNS เท่านั้น
    และต้องไม่เกิน MP ที่มีอยู่
    """
    if not is_forced_mp_turn(turn):
        return 0
    return max(0, min(int(requested_mp), int(available_mp)))

def make_roll(
    *,
    turn: int,
    mp_spent: int = 0,
    boost: bool = False,
    available_mp: Optional[int] = None,
    rng: Optional[random.Random] = None,
) -> RollResult:
    """
    สุ่ม d20 แล้วรวมบัฟจาก MP และ BOOST
    - จะ sanitize ปริมาณ MP ตามกติกา (เทิร์น 3/6/9 เท่านั้น) ถ้ามี available_mp ให้มา
    - ฝั่ง service/engine ต้องเป็นคน 'หัก MP จริง' และบันทึกการใช้ไอเท็มเอง
    """
    if available_mp is not None:
        mp_spent = sanitize_mp_spend(turn, mp_spent, available_mp)
    d = roll_d20(rng)
    total = apply_mp_bonus(d, mp_spent, boost=boost)
    return RollResult(
        dice_roll=d,
        mp_spent=mp_spent,
        boost_applied=bool(boost),
        mp_bonus=mp_spent * MP_BONUS_PER_POINT,
        boost_bonus=BOOST_ROLL_BONUS if boost else 0,
        total_roll=total,
        tier=tier_from_total(total),
    )

# -----------------------------
# เดินหน้าเทิร์น/ด่าน & เช็คสถานะเคลียร์
# -----------------------------
@dataclass
class Progress:
    stage_index: int    # ด่านปัจจุบัน (1..STAGES_TOTAL)
    turn: int           # เทิร์นปัจจุบัน (1..TURNS_PER_STAGE)

@dataclass
class AdvanceResult:
    progress: Progress
    cleared_stage: bool   # จบด่านเมื่อกี้ไหม
    cleared_game: bool    # เคลียร์เกมแล้วไหม (จบด่านสุดท้าย)

def advance(progress: Progress) -> AdvanceResult:
    """
    เรียกเมื่อ 'จบการประมวลผล' ของเทิร์นปัจจุบันแล้ว เพื่อขยับไปเทิร์น/ด่านถัดไป
    - เมื่อ turn == TURNS_PER_STAGE → จบด่าน, รีเซ็ต turn=1, stage+1
    - เมื่อ stage เกิน STAGES_TOTAL → ถือว่าเคลียร์เกม (คง progress เดิมไว้ให้ service ปิด session)
    """
    stage, turn = progress.stage_index, progress.turn
    cleared_stage = False
    cleared_game = False

    if turn >= TURNS_PER_STAGE:
        cleared_stage = True
        if stage >= STAGES_TOTAL:
            cleared_game = True
            return AdvanceResult(progress=Progress(stage, turn), cleared_stage=True, cleared_game=True)
        stage += 1
        turn = 1
    else:
        turn += 1

    return AdvanceResult(progress=Progress(stage, turn), cleared_stage=cleared_stage, cleared_game=cleared_game)

# -----------------------------
# Checkpoint effects (บอกเป็น tuple ให้ service นำไป apply)
# -----------------------------
def checkpoint_effects() -> Tuple[bool, int, int]:
    """
    คืนค่ากติกา checkpoint:
    - heal_hp_full: bool
    - restore_mp_pct: int (0..100)
    - grant_potions: int
    Service ที่เรียกจะเป็นคน apply ลง Player + clamp ค่าเอง
    """
    return CHECKPOINT_HEAL_HP_FULL, CHECKPOINT_RESTORE_MP_PCT, CHECKPOINT_GRANT_POTIONS

# -----------------------------
# ฟังก์ชันช่วยอื่น ๆ
# -----------------------------
def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))

def bounds_for_tier(tier: Literal["fail", "neutral", "success", "great"]) -> Tuple[int, int]:
    """ดึงช่วงแต้มที่สอดคล้องกับ tier (ใช้ตอนเทสต์/ดีบัก)"""
    return OUTCOME_BOUNDS[tier]
