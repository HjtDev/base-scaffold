"""Subclasses/overrides of an installed app's views — INTEGRATION-GUIDE.md §5.

Empty in a fresh scaffold. When a project needs modified behavior on top of an app's
view (extra validation, a different response shape), subclass it here and point
`config/urls.py` at the subclass instead of the app's own view — never edit the
installed package directly. Keep the app's `throttle_scope` on the subclass unless
deliberately choosing a different rate, and if you do, register the new scope in
`REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`.

Same idea for admin overrides (a proxy model + a new `ModelAdmin` registered from here)
and template overrides (mirror the app's namespaced path under `backend/templates/`).

If overrides against the same app start to sprawl, that's a signal to stop: either the
app needs a real configuration hook released in its own repo, or this project's needs
have diverged enough to want its own app.
"""
