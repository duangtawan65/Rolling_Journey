from __future__ import annotations
import os, json, re
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from roll.rules import clamp
from dotenv import load_dotenv
try:
    from groq import Groq
except Exception:
    Groq = None

load_dotenv()     

# ===================== ค่าคงที่สำหรับพรอมต์ GM =====================

SCENE_TITLES = [
    None,  # index 0 เว้นไว้
    "ถนนทางเข้าหมู่บ้าน",
    "ตลาดร้างกลางหมู่บ้าน",
    "บ้านผู้ใหญ่บ้าน",
    "วัดป่าท้ายหมู่บ้าน",
    "สุสานหลังวัด",
    "ท่าน้ำประกอบพิธี",
    "เมืองโบราณใต้บาดาล",
    "ถ้ำลับใต้เมืองโบราณ",
    "อุโมงค์หนี",
    "ปากทางออกหุบเขา",
]

DEFAULT_MISSIONS = {
    1: "หาทางเข้าสู่หมู่บ้านอย่างปลอดภัย",
    2: "สืบหาที่มาของเสียงร่ำไห้",
    3: "ค้นบันทึก/สิ่งของของผู้ใหญ่บ้านที่เกี่ยวข้อง",
    4: "ขอเบาะแสจากสิ่งศักดิ์สิทธิ์/รูปเคารพ",
    5: "ทำความเข้าใจกับวิญญาณและทางปลดปล่อย",
    6: "เตรียมพิธี/รวบรวมเครื่องประกอบ",
    7: "หาทางผ่านด่านผนึกของเมืองโบราณ",
    8: "ไขปริศนาในถ้ำเพื่อนำทางออก",
    9: "หลบหลีกอันตรายและหาทางไปทางออก",
    10:"หลุดพ้นจากหุบเขาและปิดฉากเหตุการณ์",
}

GM_SYSTEM_PROMPT = """คุณเป็น AI Game Master สำหรับเกมสยองขวัญแนวไทยเรื่อง "เสียงร่ำไห้แห่งเวียงหล่ม"

บทบาทและหน้าที่ของคุณ:
1. บรรยายสถานการณ์สยองขวัญที่น่าขนลุก สร้างบรรยากาศหลอน
2. ใช้ผลการทอยลูกเต๋าในการตัดสินเหตุการณ์
3. ให้ทางเลือกที่สมจริงและท้าทาย 3 ตัวเลือก
4. เก็บบริบทของเรื่องราวและการตัดสินใจที่ผ่านมา
5. ไม่พูดนอกเรื่อง ไม่ทำลายบรรยากาศ

การแปลผลลูกเต๋า:
- fail (1-5): ล้มเหลว เกิดเหตุร้าย อันตรายมาก HP ลด
- neutral (6-10): ผ่านไปได้แต่มีอันตราย ไม่ได้ไม่เสีย
- success (11-15): สำเร็จเล็กน้อย ได้เบาะแส
- great (16-20): สำเร็จยอดเยี่ยม ได้รางวัล/ไอเท็ม

สิ่งสำคัญ:
- บรรยายแบบสยองขวัญไทย มีเงามืด วิญญาณ ความหลอน
- สร้างความตึงเครียด ให้ผู้เล่นรู้สึกไม่ปลอดภัย
- ทางเลือกต้องมีความเสี่ยงและผลที่แตกต่างกัน
- ห้ามให้ของมากเกินไป ต้องมีความยากและท้าทาย
"""

# ===================== Data model =====================

@dataclass
class AIResult:
    narration: str
    hp_delta: int = 0
    mp_delta: int = 0
    grant_heal: int = 0
    grant_boost: int = 0
    status: List[str] = None
    extra: Dict[str, Any] = None

    def to_attrs(self) -> Dict[str, Any]:
        d = asdict(self)
        if d.get("status") is None: d["status"] = []
        if d.get("extra")  is None: d["extra"]  = {}
        return d

# ===================== Groq helpers =====================

def _default_groq_client() -> Optional["Groq"]:
    api_key = os.getenv("api_key")
    if Groq is None or not api_key:
        return None
    try:
        return Groq(api_key=api_key)
    except Exception:
        return None

def _build_user_prompt(payload: Dict[str, Any]) -> str:
    """สร้าง prompt แบบละเอียดสำหรับ GM"""
    scene_idx = payload.get("scene_index", 1)
    scene_title = payload.get("scene_title", "")
    mission = payload.get("mission", "")
    progress = payload.get("progress", 1)
    action = payload.get("action_text", "")
    
    player = payload.get("player", {})
    roll = payload.get("roll", {})
    
    hp = player.get("hp", 100)
    hp_max = player.get("HP_MAX", 100)
    mp = player.get("mp", 10)
    pot_heal = player.get("pot_heal", 0)
    pot_boost = player.get("pot_boost", 0)
    
    dice_roll = roll.get("dice_roll", 10)
    tier = roll.get("tier", "neutral")
    
    # สร้าง context สำหรับ AI
    prompt = f"""ตอนนี้เป็นฉากที่ {scene_idx}/10 ของเกม

**สถานที่ปัจจุบัน:** {scene_title}
**ภารกิจ:** {mission}
**ความคืบหน้า:** {progress}/10

**สถานะผู้เล่น:**
- HP: {hp}/{hp_max}
- MP: {mp}
- Heal Potion: {pot_heal}
- Boost Charm: {pot_boost}

**การกระทำของผู้เล่น:** "{action}"

**ผลการทอยลูกเต๋า:**
- ค่าที่ทอยได้: {dice_roll}/20
- ผลลัพธ์: {tier}

คุณต้องตอบเป็น JSON เท่านั้น โดยมีรูปแบบดังนี้:
{{
  "narration": "บรรยายสถานการณ์แบบ:\n**[สถานที่]:** ...\n**[สถานการณ์]:** (3-5 ประโยค ขึ้นอยู่กับผลลูกเต๋า)\n**[สถานะตัวละคร]:**\n**สุขภาพ:** ...\n**สติ:** ...\n**ไอเท็ม:** ...\n**ความคืบหน้าภารกิจ:** [{progress}/10]\n**[ภารกิจปัจจุบัน]:** ...\n**[ทางเลือก]:**\n* A. ...\n* B. ...\n* C. ...",
  "hp_delta": 0,
  "mp_delta": 0,
  "grant_heal": 0,
  "grant_boost": 0,
  "status": [],
  "extra": {{}}
}}

**หลักการสร้าง narration:**
1. บรรยายตามผลลูกเต๋าที่ได้
2. ถ้า fail ต้องมีอันตราย HP ลดลง (-5 ถึง -15)
3. ถ้า great ให้รางวัล เช่น grant_boost: 1
4. สร้างบรรยากาศสยองขวัญ มีเงามืด เสียงประหลาด
5. ให้ทางเลือก 3 ข้อที่เหมาะกับสถานการณ์

**สุขภาพ:** {_health_label(hp, hp_max)}
**สติ:** {_sanity_label(tier)}

ตอบเป็น JSON เท่านั้น ห้ามมีข้อความอื่น"""
    
    return prompt

def _health_label(hp: int, hp_max: int) -> str:
    r = hp / max(1, hp_max)
    if r >= 2/3: return "ปกติ"
    if r >= 1/3: return "บาดเจ็บเล็กน้อย"
    return "บาดเจ็บสาหัส"

def _sanity_label(tier: str) -> str:
    if tier in ("great","success"): return "มั่นคง"
    if tier == "neutral": return "หวาดระแวง"
    return "ใกล้เสียสติ"

def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """แยก JSON จากข้อความ"""
    if not text:
        return None
    
    # ลบ markdown code blocks
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    
    # หา JSON object
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    
    try:
        return json.loads(m.group(0))
    except Exception:
        return None

def call_llm_narrator(payload: Dict[str, Any],
                      *,
                      groq_client: Optional["Groq"]=None,
                      model: Optional[str]=None,
                      temperature: float=0.7,
                      timeout_s: int=30) -> Optional[Dict[str, Any]]:
    """เรียก AI เพื่อสร้าง narration"""
    client = groq_client or _default_groq_client()
    if client is None:
        print("❌ Groq client is None - check API key in .env file")
        return None

    # ลองใช้โมเดลอื่นถ้าไม่ระบุ
    model_name = model or "openai/gpt-oss-20b"  # เปลี่ยนจาก openai/gpt-oss-20b
    
    messages = [
        {"role": "system", "content": GM_SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(payload)}
    ]

    try:
        print(f"📡 Calling Groq API with model: {model_name}")
        
        resp = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=1000,
            timeout=timeout_s,
        )
        
        if not resp or not resp.choices:
            print("❌ No response from API")
            return None
            
        content = resp.choices[0].message.content
        print(f"📝 AI Response length: {len(content)} chars")
        print(f"📄 First 200 chars: {content[:200]}")
        
        result = _extract_json(content)
        if result:
            print("✅ JSON extracted successfully")
        else:
            print("❌ Failed to extract JSON from response")
            print(f"Full response: {content}")
        
        return result
        
    except Exception as e:
        print(f"❌ AI Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None

# ===================== Baseline (no-LLM fallback) =====================

def _choices_for_scene(scene_idx: int) -> List[str]:
    mapping = {
        1: ["ตรวจป้ายและขอบถนน", "ลัดเข้าพงหญ้าทางขวา", "เดินตามถนนเข้าไปในหมอก"],
        2: ["ค้นร้านค้าเก่า", "ฟังเสียงลม/เสียงร้อง", "ตามรอยเท้าไปตรอกแคบ"],
        3: ["สำรวจตู้เอกสาร", "เคาะเรียกและรอคำตอบ", "แง้มประตูห้องด้านหลัง"],
        4: ["จุดธูปขอทาง", "วนรอบอุโบสถ", "ส่องรูปเคารพหาเบาะแส"],
        5: ["อ่านป้ายหลุมศพ", "วางของเซ่น", "มองหาดินที่เพิ่งถูกรบกวน"],
        6: ["ตรวจแท่นพิธี", "ชำเลืองใต้น้ำ", "ฟังเสียงกระซิบริมน้ำ"],
        7: ["อ่านอักขระบนผนัง", "วัดระดับน้ำวน", "ลองวางเครื่องประกอบพิธี"],
        8: ["คลำหาทางลับ", "ส่องเพดานหิน", "ฟังเสียงหยดน้ำจับจังหวะ"],
        9: ["ตามอากาศเย็น", "ฟังเสียงลมหวน", "หลบซ่อนเมื่อได้ยินฝีเท้า"],
        10:["มุ่งหน้าออกจากหุบเขา", "มองย้อนหาเงาตามติด", "ทำพิธีปิดฉากเหตุการณ์"],
    }
    return mapping.get(scene_idx, ["สำรวจรอบตัว", "เงี่ยหูฟัง", "ก้าวต่อไปอย่างระวัง"])

def _render_narration_template(
    *, scene_title: str, situation: str, health: str, sanity: str,
    items_text: str, progress: int, mission: str, choices: List[str]
) -> str:
    a, b, c = (choices + ["...", "...", "..."])[:3]
    return (
f"**[สถานที่]:** {scene_title}\n"
f"**[สถานการณ์]:** {situation}\n"
f"**[สถานะตัวละคร]:**\n"
f"**ความคืบหน้าภารกิจ:** [{progress}/10]\n"
f"**[ภารกิจปัจจุบัน]:** {mission}\n"
f"**[ทางเลือก]:**\n"
f"* A. {a}\n"
f"* B. {b}\n"
f"* C. {c}"
    )

def baseline_from_tier(
    *, tier: str, action_text: str, scene_idx: int, player, progress: int
) -> AIResult:
    """Fallback เมื่อ AI ไม่ทำงาน"""
    scene = SCENE_TITLES[scene_idx] or f"ฉากที่ {scene_idx}"
    mission = DEFAULT_MISSIONS.get(scene_idx, "เดินหน้าไขปริศนา")
    health = _health_label(player.hp, player.HP_MAX)
    sanity = _sanity_label(tier)
    items_text = f"Heal Potion ×{player.pot_heal}, Boost Charm ×{player.pot_boost}"
    choices = _choices_for_scene(scene_idx)

    if tier == "fail":
        situation = (
            f"คุณพยายาม '{action_text}' แต่จังหวะผิดพลาด เงามืดเคลื่อนตัวมาข้างหลัง. "
            "ลมเย็นเฉียบพัดสวนกับกลิ่นดินชื้นจนสันหลังชาวาบ. "
            "บางสิ่งกำลังเฝ้ามอง—และมันรู้ว่าคุณอยู่ที่นี่."
        )
        hp_delta = -8
        grant_boost = 0
    elif tier == "neutral":
        situation = (
            f"คุณ '{action_text}' อย่างระมัดระวัง ทุกอย่างดูเงียบงันเกินจริง. "
            "สายหมอกบดบังรายละเอียดเล็กๆ และเสียงหยดน้ำคอยกวนใจ. "
            "ไม่มีอะไรเกิดขึ้นชัดเจน แต่ความรู้สึกไม่แน่ใจเริ่มก่อตัว."
        )
        hp_delta = 0
        grant_boost = 0
    elif tier == "success":
        situation = (
            f"คุณลงมือ '{action_text}' ได้อย่างเฉียบคม เงามืดถอยห่างไปชั่วครู่. "
            "เบาะแสเล็กๆ โผล่มาใต้แสงฟ้าแลบ ทำให้คุณมีกำลังใจขึ้น. "
            "เส้นทางถัดไปชัดเจนขึ้น แม้ยังแฝงอันตราย."
        )
        hp_delta = 0
        grant_boost = 0
    else:  # great
        situation = (
            f"การ '{action_text}' ของคุณแม่นยำจนน่าประหลาด เงามืดแตกซ่าน. "
            "สัญญาณดีปรากฏตรงหน้า—บันไดทางลับ/สัญลักษณ์นำทางเผยตัวออกมา. "
            "คุณสูดลมหายใจลึก ความมั่นใจไหลคืนสติ."
        )
        hp_delta = 0
        grant_boost = 1

    narration = _render_narration_template(
        scene_title=scene,
        situation=situation,
        health=health,
        sanity=sanity,
        items_text=items_text,
        progress=max(0, min(10, int(progress))),
        mission=mission,
        choices=choices,
    )
    
    return AIResult(
        narration=narration,
        hp_delta=hp_delta,
        mp_delta=0,
        grant_heal=0,
        grant_boost=grant_boost,
        status=[],
        extra={"scene_title": scene, "mission": mission},
    )

# ===================== Entry point =====================

def resolve_effects(
    *,
    session,
    player,
    roll,
    action_text: str,
    kind: str,
    groq_client: Optional["Groq"]=None,
    model: Optional[str]=None,
) -> AIResult:
    """ใช้ AI จริงๆ ในการสร้าง narration"""
    scene_idx = max(1, min(10, int(session.stage_index)))
    scene_title = SCENE_TITLES[scene_idx] or f"ฉากที่ {scene_idx}"
    mission = DEFAULT_MISSIONS.get(scene_idx, "เดินหน้าไขปริศนา")
    progress = max(1, min(10, int(session.turn)))

    payload = {
        "scene_index": scene_idx,
        "scene_title": scene_title,
        "mission": mission,
        "progress": progress,
        "kind": kind,
        "player": {
            "hp": player.hp, 
            "mp": player.mp,
            "pot_heal": player.pot_heal, 
            "pot_boost": player.pot_boost,
            "HP_MAX": player.HP_MAX, 
            "MP_MAX": player.MP_MAX,
        },
        "roll": {
            "dice_roll": roll.dice_roll,
            "total": roll.total_roll,
            "tier": roll.tier,
            "mp_spent": roll.mp_spent,
            "boost_applied": roll.boost_applied,
        },
        "action_text": action_text,
    }

    # ลอง call AI ก่อน
    print(f"🎲 Calling AI for scene {scene_idx}...")
    data = call_llm_narrator(payload, groq_client=groq_client, model=model)
    
    if data and isinstance(data, dict) and "narration" in data:
        print("✅ AI response received!")
        ai = AIResult(
            narration=str(data.get("narration") or ""),
            hp_delta=int(data.get("hp_delta") or 0),
            mp_delta=int(data.get("mp_delta") or 0),
            grant_heal=int(data.get("grant_heal") or 0),
            grant_boost=int(data.get("grant_boost") or 0),
            status=list(data.get("status") or []),
            extra=dict({"scene_title": scene_title, "mission": mission, **(data.get("extra") or {})}),
        )
        return _validated(ai, player)

    # Fallback ถ้า AI ไม่ทำงาน
    print("⚠️ AI failed, using baseline...")
    return _validated(baseline_from_tier(
        tier=roll.tier, 
        action_text=action_text,
        scene_idx=scene_idx, 
        player=player, 
        progress=progress
    ), player)

def _validated(ai: AIResult, player) -> AIResult:
    """ตรวจสอบและจำกัดค่า"""
    ai.hp_delta = max(-50, min(50, int(ai.hp_delta)))
    ai.mp_delta = max(-10, min(10, int(ai.mp_delta)))
    
    if player.mp + ai.mp_delta < 0:
        ai.mp_delta = -player.mp
    
    ai.grant_heal  = max(0, min(2, int(ai.grant_heal)))
    ai.grant_boost = max(0, min(2, int(ai.grant_boost)))
    
    if ai.status is None:
        ai.status = []
    if ai.extra is None:
        ai.extra = {}
    
    return ai