from uuid import uuid4
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Q
from .enums import SessionStatus, EventType, TemplateKind

# ---------- Stage ----------
class Stage(models.Model):
    index = models.PositiveIntegerField(
        unique=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)]  # คุมให้ 1..10
    )
    name  = models.CharField(max_length=100)
    zone  = models.CharField(max_length=50, blank=True)  # house/forest/hospital
    bg_intro_url  = models.CharField(max_length=255, blank=True)
    bg_battle_url = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["index"]

    def __str__(self):
        return f"Stage {self.index}: {self.name}"

# ---------- Checkpoint ----------
class Checkpoint(models.Model):
    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name="checkpoints")
    turn  = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )  # เทิร์นในด่าน (ตามกติกาใช้ 1 และ 5)

    heal_hp_full   = models.BooleanField(default=True)
    restore_mp_pct = models.PositiveIntegerField(default=50)  # คืน MP % ของ max
    grant_potions  = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["stage", "turn"], name="uniq_checkpoint_stage_turn"),
            # บังคับให้ turn เป็น 1 หรือ 5 ตามกติกาปัจจุบัน
            models.CheckConstraint(
                check=Q(turn__in=[1, 5]),
                name="checkpoint_turn_in_1_or_5",
            ),
        ]
        ordering = ["stage__index", "turn"]

    def __str__(self):
        return f"Checkpoint S{self.stage.index}@T{self.turn}"

# ---------- Player ----------
class Player(models.Model):
    user = models.ForeignKey(
        getattr(settings, "AUTH_USER_MODEL", "auth.User"),
        on_delete=models.SET_NULL, null=True, blank=True
    )
    anon_id  = models.CharField(max_length=64, unique=True, blank=False)

    hp = models.IntegerField(default=30)
    mp = models.IntegerField(default=10)

    pot_heal   = models.IntegerField(default=1)
    pot_boost  = models.IntegerField(default=0)

    last_checkpoint = models.ForeignKey(
        Checkpoint, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="players"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ค่าคงที่ (ไม่ใช่คอลัมน์ DB)
    HP_MAX = 30
    MP_MAX = 10

    @property
    def potions_total(self) -> int:
        return max(0, int(self.pot_heal)) + max(0, int(self.pot_boost))

    def __str__(self):
        # แก้บั๊ก: เดิมอ้าง self.potions ซึ่งไม่มี
        return f"Player<{self.id}> hp={self.hp} mp={self.mp} potions={self.potions_total}"

# ---------- Session (การเล่น 1 รอบ) ----------
class Session(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="sessions")

    stage_index = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        db_index=True
    )   # ด่านปัจจุบัน 1..10
    turn = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        db_index=True
    )   # เทิร์น 1..10

    status = models.CharField(
        max_length=10,
        choices=SessionStatus.choices,
        default=SessionStatus.ACTIVE,
        db_index=True
    )
    started_at  = models.DateTimeField(default=timezone.now)
    ended_at    = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["player", "status"]),
            models.Index(fields=["player", "stage_index", "turn"]),
        ]

    def __str__(self):
        return f"Session<{self.id}> P{self.player_id} S{self.stage_index}T{self.turn} {self.status}"

# ---------- EventTemplate (optional config) ----------
class EventTemplate(models.Model):
    event_id   = models.CharField(max_length=64, unique=True)
    title      = models.CharField(max_length=120)
    zone       = models.CharField(max_length=50, blank=True)
    kind       = models.CharField(max_length=12, choices=TemplateKind.choices,
                                  default=TemplateKind.NORMAL)

    mp_cost     = models.PositiveIntegerField(default=0)
    requires_mp = models.BooleanField(default=False)
    mp_bonus    = models.IntegerField(default=0)             # เช่น +5
    fallback    = models.CharField(max_length=8, default="none")  # none|harder|alt

    template_text = models.TextField(blank=True)

    def __str__(self):
        return f"{self.event_id} [{self.kind}]"

# ---------- EventLog (telemetry / dashboard) ----------
class EventLog(models.Model):
    ts       = models.DateTimeField(default=timezone.now, db_index=True)
    player   = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="logs")
    session  = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="logs")
    type     = models.CharField(max_length=32, choices=EventType.choices, db_index=True)

    stage_index = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    turn        = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(10)]
    )

    # snapshot state
    hp  = models.IntegerField()
    mp  = models.IntegerField()

    # รวมโพชั่นทั้งหมด (คงของเดิมไว้เพื่อ backward-compat)
    potions = models.IntegerField()

    # เพิ่มแยกเป็นชนิดเพื่อทำแดชบอร์ดละเอียด (ค่า default=0 ปลอดภัย)
    pot_heal_ct  = models.IntegerField(default=0)
    pot_boost_ct = models.IntegerField(default=0)

    # ข้อมูลเสริม
    attrs = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["player", "session", "ts"]),
            models.Index(fields=["type", "ts"]),
            models.Index(fields=["stage_index", "turn"]),
            models.Index(fields=["player", "session", "stage_index", "turn", "ts"]),
        ]
        ordering = ["ts", "id"]

    def __str__(self):
        return f"[{self.ts:%H:%M:%S}] {self.type} S{self.stage_index}T{self.turn} hp={self.hp} mp={self.mp}"
