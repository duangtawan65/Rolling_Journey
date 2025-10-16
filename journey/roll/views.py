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
# roll/views.py
# journey/roll/views.py
from collections import defaultdict
from django.db.models import Count, Avg, Max, Min, F, Q
from django.db.models.functions import TruncDate
from django.shortcuts import render

from .models import Player, Session, EventLog
try:
    # เผื่อโปรเจ็กต์คุณมี enums
    from .enums import SessionStatus
    ACTIVE = getattr(SessionStatus, "ACTIVE", "ACTIVE")
    FINISHED = getattr(SessionStatus, "FINISHED", "FINISHED")
except Exception:
    # กันไว้ถ้าไม่มี enums
    ACTIVE = "ACTIVE"
    FINISHED = "FINISHED"

CHOICES = ["A", "B", "C"]
STAGES = list(range(1, 11))
SANITY_MAP = {
    "stable": "มั่นคง",
    "paranoid": "หวาดระแวง",
    "breakdown": "ใกล้เสียสติ",
}

def native_dashboard(request):
    # ---------- 🧍 ผู้เล่น ----------
    # ถ้ามี log session_start ก็ใช้เป็นตัวนับ entrant; ถ้ายังไม่ยิง log ใช้จำนวน Player กันไว้
    total_entrants = (
        EventLog.objects.filter(type="session_start").values("player_id").distinct().count()
        or Player.objects.count()
    )

    finishers = (
        Session.objects.filter(status=FINISHED)
        .values("player_id").distinct().count()
    )
    completion_rate = round((finishers / total_entrants) * 100, 1) if total_entrants else 0.0

    recent_players = (
        Session.objects
        .values("player_id")
        .annotate(
            last_started=Max("started_at"),
            rounds=Count("id"),
            last_status=Max("status"),
        )
        .order_by("-last_started")[:10]
    )

    # ---------- 🗺️ ความคืบหน้า ----------
    # แจกแจง stage ปัจจุบัน (จะเลือก ACTIVE ตามชื่อหมวดในหน้า)
    current_stage_dist = (
        Session.objects.filter(status=ACTIVE)
        .values("stage_index")
        .annotate(c=Count("id"))
        .order_by("stage_index")
    )
    stage_labels = [f"S{s['stage_index']}" for s in current_stage_dist]
    stage_counts = [s["c"] for s in current_stage_dist]

    # Heatmap ทางเลือก (A/B/C) ต่อฉาก จาก EventLog.type='choice' + attrs.choice
    choice_qs = (
        EventLog.objects
        .filter(type="choice", attrs__has_key="choice")
        .values("stage_index", "attrs__choice")
        .annotate(c=Count("id"))
    )
    heatmap = {s: {ch: 0 for ch in CHOICES} for s in STAGES}
    for row in choice_qs:
        stage = int(row["stage_index"])
        ch = row["attrs__choice"]
        if stage in heatmap and ch in heatmap[stage]:
            heatmap[stage][ch] = row["c"]

    top_choice_by_stage = {
        s: (max(heatmap[s].items(), key=lambda kv: kv[1])[0] if sum(heatmap[s].values()) else "-")
        for s in STAGES
    }

    # ---------- 💀 สถิติความตาย ----------
    deaths = EventLog.objects.filter(type="death")
    death_total = deaths.count()
    death_by_stage = list(
        deaths.values("stage_index").annotate(c=Count("id")).order_by("-c")[:10]
    )
    top_death_stage = death_by_stage[0]["stage_index"] if death_by_stage else None

    death_reasons = list(
        deaths.values("attrs__reason").annotate(c=Count("id")).order_by("-c")[:8]
    )

    # ---------- 🎭 สถานะจิตใจ ----------
    sanity_qs = EventLog.objects.filter(type="sanity", attrs__has_key="sanity")
    sanity_dist = sanity_qs.values("attrs__sanity").annotate(c=Count("id")).order_by("-c")
    sanity_labels = [SANITY_MAP.get(x["attrs__sanity"], x["attrs__sanity"]) for x in sanity_dist]
    sanity_counts = [x["c"] for x in sanity_dist]

    # ---------- 🎒 ไอเท็ม ----------
    holders_any_item = Player.objects.filter(Q(pot_heal__gt=0) | Q(pot_boost__gt=0)).count()
    players_total = max(Player.objects.count(), 1)
    holding_rate = round((holders_any_item / players_total) * 100, 1)

    # ไอเท็มช่วยรอดชีวิต (proxy: จำนวน finishers ที่ผู้เล่นมีโพชั่นอย่างน้อย 1)
    finishers_with_pot = (
        Session.objects.filter(status=FINISHED, player__pot_heal__gt=0)
        | Session.objects.filter(status=FINISHED, player__pot_boost__gt=0)
    ).values("player_id").distinct().count()
    surv_help = {
        "with_potion": finishers_with_pot,
        "without_potion": max(finishers - finishers_with_pot, 0),
    }

    # ---------- ⏱️ เวลาเล่น ----------
    # (แก้แบบไม่ซ้อน Aggregate) ดึง min/max ต่อ (session, stage) แล้วคำนวณเฉลี่ยใน Python
    span_qs = (
        EventLog.objects
        .values("session_id", "stage_index")
        .annotate(tmin=Min("ts"), tmax=Max("ts"))
    )
    stage_seconds = defaultdict(list)
    for r in span_qs:
        tmin, tmax = r["tmin"], r["tmax"]
        if tmin and tmax and tmax > tmin:
            secs = (tmax - tmin).total_seconds()
            stage_seconds[r["stage_index"]].append(secs)

    time_stage_labels, time_stage_avg_sec = [], []
    for s in sorted(stage_seconds.keys()):
        vals = stage_seconds[s]
        avg_sec = sum(vals) / len(vals) if vals else 0
        time_stage_labels.append(f"S{s}")
        time_stage_avg_sec.append(round(avg_sec, 1))

    # เวลาเฉลี่ยก่อนตาย: session_start -> death ที่เร็วสุดของ session
    starts = (
        EventLog.objects.filter(type="session_start")
        .values("session_id").annotate(t0=Min("ts"))
    )
    t0_map = {str(x["session_id"]): x["t0"] for x in starts}
    to_death = []
    for d in deaths.values("session_id").annotate(td=Min("ts")):
        s_id = str(d["session_id"])
        if s_id in t0_map:
            to_death.append((d["td"] - t0_map[s_id]).total_seconds())
    avg_time_to_death = round(sum(to_death) / len(to_death), 1) if to_death else 0.0

    # ---------- รายวัน: entrants vs finishers ----------
    daily_ent = (
        EventLog.objects.filter(type="session_start")
        .annotate(day=TruncDate("ts")).values("day").annotate(c=Count("id")).order_by("day")
    )
    daily_fin = (
        Session.objects.filter(status=FINISHED, ended_at__isnull=False)
        .annotate(day=TruncDate("ended_at")).values("day").annotate(c=Count("id")).order_by("day")
    )
    # รวมวันทั้งหมดเพื่อทำแกน x เดียว
    all_days = sorted({str(x["day"]) for x in daily_ent} | {str(x["day"]) for x in daily_fin})
    ent_map = {str(x["day"]): x["c"] for x in daily_ent}
    fin_map = {str(x["day"]): x["c"] for x in daily_fin}
    daily_labels = all_days
    daily_ent_vals = [ent_map.get(d, 0) for d in all_days]
    daily_fin_vals = [fin_map.get(d, 0) for d in all_days]

    context = {
        # KPI
        "total_entrants": total_entrants,
        "finishers": finishers,
        "completion_rate": completion_rate,
        "avg_time_to_death": avg_time_to_death,

        # ผู้เล่นล่าสุด
        "recent_players": list(recent_players),

        # ความคืบหน้า + heatmap
        "stage_labels": stage_labels,
        "stage_counts": stage_counts,
        "heatmap": heatmap,
        "choices": CHOICES,

        # ความตาย
        "death_total": death_total,
        "top_death_stage": top_death_stage,
        "death_by_stage": death_by_stage,
        "death_reasons": death_reasons,

        # สถานะจิตใจ
        "sanity_labels": sanity_labels,
        "sanity_counts": sanity_counts,

        # ไอเท็ม
        "holding_rate": holding_rate,
        "surv_help": surv_help,

        # เวลาเล่น
        "time_stage_labels": time_stage_labels,
        "time_stage_avg_sec": time_stage_avg_sec,

        # รายวัน
        "daily_labels": daily_labels,
        "daily_ent_vals": daily_ent_vals,
        "daily_fin_vals": daily_fin_vals,
    }
    return render(request, "roll/native_dashboard.html", context)


########################################################################################

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
        
        # --- FIX IS HERE ---
        # 1. Create the new user
        new_user = User.objects.create_user(username=username, password=password)
        
        # 2. Immediately create the associated Player with a unique anon_id
        Player.objects.create(
            user=new_user,
            anon_id=str(uuid4()) # Generate a unique ID
        )
        # -------------------

        return redirect("/login/")
    
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
    Finds or creates a player.
    - For logged-in users, it's linked to their user account.
    - For anonymous users, it uses the 'X-ANON-ID' header or creates a new one.
    """
    if request.user and request.user.is_authenticated:
        # --- THIS IS THE FIX ---
        # When creating a player for a logged-in user for the first time,
        # also create a unique anon_id for them.
        player, _ = Player.objects.get_or_create(
            user=request.user,
            defaults={'anon_id': uuid4().hex}
        )
        return player

    # This part for anonymous users is already correct
    anon_id = request.headers.get("X-ANON-ID")
    if not anon_id:
        anon_id = uuid4().hex
    
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