"""Inter-app signal receivers — the mediator pattern's event-driven half.

Empty in a fresh scaffold. A receiver here listens for one installed app's Django signal
and calls another installed app's `services.py` in response, fire-and-forget. See
INTEGRATION-GUIDE.md §4 for the worked example, and note the rule from BASE-DESIGN.md §6:
a receiver that does real work enqueues a Celery task with `transaction.on_commit(...)`
rather than doing the work inline.
"""
