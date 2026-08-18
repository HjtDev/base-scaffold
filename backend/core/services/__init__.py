"""Cross-app service orchestrators — the mediator pattern's request/response half.

Empty in a fresh scaffold. A function here composes multiple installed apps' own
`services.py` interfaces for a workflow that needs a direct, synchronous result (e.g.
checkout), rather than the fire-and-forget style of `core/signals.py`. See
INTEGRATION-GUIDE.md §4 for the worked example. No app in the chain knows about any
other app in the chain — only this module does.
"""

# Worked example (INTEGRATION-GUIDE.md §4) — a checkout flow composing cart_app,
# inventory_app, and payments_app's own services.py interfaces. Left commented out
# because a fresh scaffold has no apps installed yet — uncomment and adapt once your
# equivalents are wired in. A project-level view or Celery task calls this function,
# not any single app directly.
#
# from django.db import transaction
#
# from cart_app.services import CartService
# from inventory_app.services import InventoryService
# from payments_app.services import PaymentService
#
#
# @transaction.atomic
# def complete_checkout(user_id: int):
#     cart = CartService.get_active_cart(user_id)
#     InventoryService.reserve(cart.items)
#     payment = PaymentService.charge(user_id, cart.total)
#     return payment
#
# The @transaction.atomic above is doing real work, and so is what it can't do: it
# guarantees the *database* effects roll back together, but it cannot roll back a charge
# already made at an external provider (e.g. Stripe). Any orchestrator that mixes DB
# writes with external side effects needs an explicit compensation path — a try/except
# that refunds, or an idempotency key so a retry is safe. Note that in the orchestrator's
# own docstring so the next reader doesn't assume more safety than exists.
