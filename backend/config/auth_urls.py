from django.urls import path

from config.auth_views import auth_csrf, auth_login, auth_logout, auth_me


urlpatterns = [
    path("csrf/", auth_csrf, name="auth-csrf"),
    path("login/", auth_login, name="auth-login"),
    path("logout/", auth_logout, name="auth-logout"),
    path("me/", auth_me, name="auth-me"),
]
