from __future__ import annotations
from django.shortcuts import render, redirect
from types import SimpleNamespace

# Create your views here.

import json
from uuid import uuid4
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseNotAllowed
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt,csrf_protect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from .models import Player, Session, Stage, EventLog
from .enums import EventType, SessionStatus
from .progress import resolve_turn
from django.contrib.auth import authenticate, login, logout
from django.views.decorators.http import require_http_methods
from django.utils.http import url_has_allowed_host_and_scheme
from django.conf import settings
from django.contrib.auth.models import User
from roll.ai import resolve_effects
from roll.rules import classify_turn
# ---------- helpers ----------

def _redirect_safe(request, to: str, default: str = "/"):
    """ป้องกัน open redirect vulnerability"""
    if to and url_has_allowed_host_and_scheme(to, allowed_hosts={request.get_host()}):
        return redirect(to)
    return redirect(default)


@csrf_protect
@require_http_methods(["GET", "POST"])
def login_view(request):
    """ฟอร์มล็อกอิน"""
    if request.user.is_authenticated:
        return redirect("/game/")
    
    next_url = request.GET.get("next") or request.POST.get("next") or ""
    
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        
        if not username or not password:
            return render(request, "login.html", {
                "error": "กรุณากรอกชื่อผู้ใช้และรหัสผ่าน",
                "next": next_url
            })
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            return _redirect_safe(
                request, 
                next_url, 
                default="/game/"
            )
        
        return render(request, "login.html", {
            "error": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง",
            "next": next_url
        })
    
    return render(request, "login.html", {"next": next_url})


@csrf_protect
@require_http_methods(["GET", "POST"])
def register_view(request):
    """ฟอร์มสมัครสมาชิก"""
    if request.user.is_authenticated:
        return redirect("/game/")
    
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        password_confirm = request.POST.get("password_confirm", "")
        
        if not username or not password:
            return render(request, "register.html", {
                "error": "กรุณากรอกชื่อผู้ใช้และรหัสผ่าน"
            })
        
        if len(username) < 3:
            return render(request, "register.html", {
                "error": "ชื่อผู้ใช้ต้องมีอย่างน้อย 3 ตัวอักษร"
            })
        
        if len(password) < 6:
            return render(request, "register.html", {
                "error": "รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร"
            })
        
        if password != password_confirm:
            return render(request, "register.html", {
                "error": "รหัสผ่านไม่ตรงกัน"
            })
        
        if User.objects.filter(username=username).exists():
            return render(request, "register.html", {
                "error": "ชื่อผู้ใช้นี้ถูกใช้งานแล้ว"
            })
        
        # สร้าง user ใหม่แล้ว redirect กลับไป login
        User.objects.create_user(username=username, password=password)
        return redirect("/login/")  # ไม่ login อัตโนมัติ ให้กลับไป login เอง
    
    return render(request, "register.html", {})


@require_http_methods(["POST"])
def logout_view(request):
    """ออกจากระบบ"""
    logout(request)
    return redirect("/login/")


def game_view(request):
    """หน้าเกม - ต้อง login ก่อน"""
    if not request.user.is_authenticated:
        return redirect("/login/")
    return render(request, "game.html", {})


def _get_or_create_player(request) -> Player:
    """
    นโยบายอย่างง่าย:
    - ถ้าล็อกอิน: ผูกกับ user
    - ถ้าไม่ล็อกอิน: ใช้ header 'X-ANON-ID' ถ้ามี; ถ้าไม่มีให้สร้าง anon_id ใหม่
    """
    if request.user and request.user.is_authenticated:
        player, _ = Player.objects.get_or_create(user=request.user)
        return player

    anon_id = request.headers.get("X-ANON-ID")
    if not anon_id:
        anon_id = uuid4().hex
        # หมายเหตุ: คุณอาจอยากส่ง anon_id นี้กลับไปที่ client ให้เก็บใช้ในครั้งต่อไป
    player, _ = Player.objects.get_or_create(anon_id=anon_id)
    return player

def _log_session(player: Player, session: Session, etype: EventType, attrs=None):
    """log บางเหตุการณ์ระดับ session (ไม่ไปซ้ำกับ progress ที่ log ระดับ turn)"""
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
        attrs=attrs or {},
    )

def _bad_request(msg: str):
    return HttpResponseBadRequest(json.dumps({"error": msg}), content_type="application/json")


# ---------- endpoints ----------

@csrf_exempt
@require_http_methods(["POST"])
def start_session(request):
    """
    เริ่มรอบเล่นใหม่:
    - ถ้ามี ACTIVE อยู่แล้ว: คืน session เดิม (ป้องกันซ้อน)
    - ไม่ log STAGE_ENTER ที่นี่ ปล่อยให้ progress.resolve_turn จัดตอนเทิร์นแรก
    """
    player = _get_or_create_player(request)

    existing = Session.objects.filter(player=player, status=SessionStatus.ACTIVE).first()
    if existing:
        # มีอยู่แล้ว → คืน state ปัจจุบัน
        return JsonResponse({
            "session_id": str(existing.id),
            "status": existing.status,
            "stage_index": existing.stage_index,
            "turn": existing.turn,
            "player": {"hp": player.hp, "mp": player.mp, "pot_heal": player.pot_heal, "pot_boost": player.pot_boost},
            "note": "resume_active_session",
        }, status=200)

    # ถ้าอยากกันเริ่มที่ stage 1 ต้องมี Stage(1) ใน DB (ไม่จำเป็นต้อง FK)
    if not Stage.objects.filter(index=1).exists():
        # ไม่บังคับ แต่เตือน
        pass

    with transaction.atomic():
        session = Session.objects.create(player=player, stage_index=1, turn=1, status=SessionStatus.ACTIVE)
        _log_session(player, session, EventType.SESSION_START)

    return JsonResponse({
        "session_id": str(session.id),
        "status": session.status,
        "stage_index": session.stage_index,
        "turn": session.turn,
        "player": {"hp": player.hp, "mp": player.mp, "pot_heal": player.pot_heal, "pot_boost": player.pot_boost},
    }, status=201)


@csrf_exempt
@require_http_methods(["GET"])
def get_state(request, session_id):
    """อ่านสถานะล่าสุดของ session"""
    player = _get_or_create_player(request)
    session = get_object_or_404(Session, id=session_id, player=player)

    return JsonResponse({
        "session_id": str(session.id),
        "status": session.status,
        "stage_index": session.stage_index,
        "turn": session.turn,
        "player": {"hp": player.hp, "mp": player.mp, "pot_heal": player.pot_heal, "pot_boost": player.pot_boost},
    })


@csrf_exempt
@require_http_methods(["POST"])
def act(request, session_id):
    """
    เล่น 1 เทิร์น (ยื่น action + ตัวเลือกใช้ของ/ใช้ MP):
    body JSON:
    {
      "action_text": "attack goblin",
      "use_mp": 2,
      "use_heal": false,
      "use_boost": true,
      "seed": 123                # (optional) สำหรับรีเพลย์/เทสต์
    }
    """
    player = _get_or_create_player(request)
    session = get_object_or_404(Session, id=session_id, player=player)

    if session.status != SessionStatus.ACTIVE:
        return _bad_request(f"session is not ACTIVE (status={session.status})")

    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else {}
    except json.JSONDecodeError:
        return _bad_request("invalid JSON body")

    action_text = (payload.get("action_text") or "").strip()
    if not action_text:
        return _bad_request("action_text is required")

    use_mp    = int(payload.get("use_mp") or 0)
    use_heal  = bool(payload.get("use_heal") or False)
    use_boost = bool(payload.get("use_boost") or False)
    seed      = payload.get("seed")  # อนุญาต None หรือ int

    # ป้องกันกดซ้ำในเทิร์นเดียว: ล็อกแถว session
    with transaction.atomic():
        session = Session.objects.select_for_update().get(id=session.id)
        # เรียก service จัดการเทิร์น (เป็นแหล่งเดียวที่แตะกติกา/log รายเทิร์น)
        rng = None
        if isinstance(seed, int):
            import random
            rng = random.Random(seed)

        result = resolve_turn(
            session=session,
            player=player,
            action_text=action_text,
            use_mp=use_mp,
            use_heal=use_heal,
            use_boost=use_boost,
            rng=rng,
        )

    # ส่งผลลัพธ์ให้ client
    roll = result["roll"]
    return JsonResponse({
        "session_id": str(session.id),
        "status": session.status,
        "stage_index": session.stage_index,
        "turn_index": session.turn,       # <--- เดิมใช้ "turn" ทับชื่ออ็อบเจ็กต์
        "player": {
            "hp": player.hp, "mp": player.mp,
            "pot_heal": player.pot_heal, "pot_boost": player.pot_boost,
        },
        "turn": {
            "kind": result["kind"],
            "narration": result["narration"],      # <--- ใส่ข้อความ AI
            "cleared_stage": result["cleared_stage"],
            "cleared_game": result["cleared_game"],
            "dead": result["dead"],
            "roll": {
                "dice_roll": roll.dice_roll,
                "mp_spent": roll.mp_spent,
                "mp_bonus": roll.mp_bonus,
                "boost_applied": roll.boost_applied,
                "boost_bonus": roll.boost_bonus,
                "total_roll": roll.total_roll,
                "tier": roll.tier,
            },
        },
    })


@csrf_exempt
@require_http_methods(["POST"])
def end_session(request, session_id):
    """
    จบ session ด้วยมือ (เช่น ปุ่ม Quit)
    - ตอนนี้ใช้สถานะ ESCAPED เป็นตัวแทนของ "เลิกรอบเล่น"
    """
    player = _get_or_create_player(request)
    session = get_object_or_404(Session, id=session_id, player=player)

    if session.status != SessionStatus.ACTIVE:
        return _bad_request(f"session is not ACTIVE (status={session.status})")

    with transaction.atomic():
        session.status = SessionStatus.ESCAPED
        session.ended_at = timezone.now()
        session.save(update_fields=["status", "ended_at", "updated_at"])
        _log_session(player, session, EventType.SESSION_END, attrs={"status": SessionStatus.ESCAPED})

    return JsonResponse({"ok": True, "session_id": str(session.id), "status": session.status})

@csrf_exempt
@require_http_methods(["GET"])
def intro(request, session_id):
    player = _get_or_create_player(request)
    session = get_object_or_404(Session, id=session_id, player=player)
    kind = classify_turn(session.turn)

    # roll ปลอมสำหรับบรรยาย (ไม่ทอยจริง)
    fake = SimpleNamespace(
        dice_roll=10,
        mp_spent=0,
        total_roll=10,
        tier="neutral",
        boost_applied=False,
        mp_bonus=0,
        boost_bonus=0,
    )

    ai = resolve_effects(
        session=session, player=player, roll=fake,
        action_text="สำรวจรอบตัว", kind=kind
    )

    return JsonResponse({
        "session_id": str(session.id),
        "status": session.status,
        "stage_index": session.stage_index,
        "turn_index": session.turn,
        "turn_intro": {"narration": ai.narration},
        "player": {
            "hp": player.hp, "mp": player.mp,
            "pot_heal": player.pot_heal, "pot_boost": player.pot_boost,
        },
    })