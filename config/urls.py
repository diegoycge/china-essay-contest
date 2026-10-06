from django.urls import include, path

urlpatterns = [
    path("", include("portal.urls")),
]

handler403 = "portal.views.auth.forbidden"
handler404 = "portal.views.auth.not_found"
