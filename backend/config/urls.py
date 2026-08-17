"""A normal, explicit Django URLconf — no discovery loop, no filesystem scan. See
INTEGRATION-GUIDE.md §3. Every installed app package gets two mounts, one public and one
admin, added under the labelled comment blocks below per its own README.
"""

from django.contrib import admin
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", views.healthz),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema")),
    # ---- Public App APIs
    # ---- Custom Admin Dashboard APIs
]
