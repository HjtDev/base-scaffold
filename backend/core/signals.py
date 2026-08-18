"""Inter-app signal receivers — the mediator pattern's event-driven half.

Empty in a fresh scaffold. A receiver here listens for one installed app's Django signal
and calls another installed app's `services.py` in response, fire-and-forget. See
INTEGRATION-GUIDE.md §4 for the worked example, and note the rule from BASE-DESIGN.md §6:
a receiver that does real work enqueues a Celery task with `transaction.on_commit(...)`
rather than doing the work inline.
"""

# Worked example (INTEGRATION-GUIDE.md §4) — payments_app completing a payment, notifying
# via notifications_app. Neither app imports the other; this module is the only code that
# knows both exist. Left commented out because a fresh scaffold has no apps installed yet —
# uncomment and adapt once payments_app/notifications_app (or your equivalents) are wired in.
#
# from django.db import transaction
# from django.dispatch import receiver
#
# from notifications_app.services import NotificationService
# from payments_app.signals import payment_completed
#
#
# @receiver(payment_completed)
# def notify_on_payment_completed(sender, payment_id, user_id, amount, **kwargs):
#     # on_commit: never notify about a payment whose transaction later rolls back
#     transaction.on_commit(
#         lambda: NotificationService.send(
#             user_id=user_id,
#             template="payment_success",
#             context={"amount": amount},
#         )
#     )
#
# Three rules for every receiver in this file, learned the hard way (INTEGRATION-GUIDE.md §4):
#
#   - Always accept **kwargs. An app adding a kwarg to a signal payload is a minor version
#     bump for that app; a receiver without **kwargs breaks on it.
#   - Never let a receiver raise into the sender. A receiver that throws propagates into the
#     sending app's own services.py call, so a failed notification rolls back a successful
#     payment. Wrap the body in try/except that logs, or — better — do nothing but enqueue a
#     task, so the retry story belongs to Celery.
#   - Slow work goes in a task, not the receiver. Signals are synchronous. Calling an SMS
#     provider inline adds its latency to the request that triggered the signal.
