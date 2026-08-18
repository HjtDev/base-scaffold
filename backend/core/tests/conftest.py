"""Cross-app fixtures for `core/tests/` — BASE-DESIGN.md §5.2.

This is where installed apps' `factories.py` (APP-DESIGN.md §7.3) earns its place:
importing another app's factories from `core/tests/` is sanctioned and expected;
importing them from `core/services/` or any other production code is a bug, enforced
by the `no-factories-in-core` pre-commit hook (docs/CORRECTIONS.md #2).

Empty in a fresh scaffold — no apps are installed yet. The commented example below
shows the pattern: seed whatever objects a cross-app test needs (a cart with items and
a default payment method, say) behind one fixture, using each app's own factories.
"""

# import pytest
# from cart_app.factories import CartFactory, CartItemFactory
# from payments_app.factories import PaymentMethodFactory
#
#
# @pytest.fixture
# def checkout_ready_user(user):
#     cart = CartFactory(user=user)
#     CartItemFactory.create_batch(3, cart=cart)
#     PaymentMethodFactory(user=user, is_default=True)
#     return user
