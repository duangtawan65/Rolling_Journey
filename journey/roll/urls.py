from django.urls import path,include
from roll import views

urlpatterns = [
    path("api/session/start", views.start_session, name="start_session"),
    path("api/session/<uuid:session_id>/state", views.get_state, name="get_state"),
    path("api/session/<uuid:session_id>/act", views.act, name="act"),
    path("api/session/<uuid:session_id>/end", views.end_session, name="end_session"),

    path('', views.login_view, name='home'),  # หน้าแรกคือ login
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('game/', views.game_view, name='game'),
    path("api/session/<uuid:session_id>/intro", views.intro, name="intro"),
]

