from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Player, Session, EventLog, Checkpoint, Stage

@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ['id', 'anon_id', 'user', 'hp', 'mp', 'created_at']
    search_fields = ['anon_id', 'user__username']

@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'player', 'stage_index', 'turn', 'status', 'started_at']
    search_fields = ['player__anon_id']

@admin.register(EventLog)
class EventLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'session']
    search_fields = ['session__id']

@admin.register(Checkpoint)
class CheckpointAdmin(admin.ModelAdmin):
    pass

@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    pass