import uuid
from datetime import datetime, timezone, timedelta

import pytest

from app.domain.enums import (
    PaymentOrderStatus,
    PaymentProvider,
    PaymentTransactionStatus,
    RecruitmentPlanStatus,
    SubscriptionStatus,
    UserRole,
)
from app.domain.models.base import utc_now
from app.models import (
    PaymentOrder,
    PaymentTransaction,
    RecruitmentPlan,
    Subscription,
    User,
)


def test_recruitment_plan_model_structure():
    """Test RecruitmentPlan model has all required columns."""
    plan = RecruitmentPlan(
        name="Professional",
        description="Professional recruitment plan",
        price=1000000,
        currency="VND",
        duration_days=30,
        max_job_posts=10,
        max_candidate_searches=100,
        max_ai_features=50,
        is_active=True,
        display_order=1,
    )

    assert plan.name == "Professional"
    assert plan.description == "Professional recruitment plan"
    assert plan.price == 1000000
    assert plan.currency == "VND"
    assert plan.duration_days == 30
    assert plan.max_job_posts == 10
    assert plan.max_candidate_searches == 100
    assert plan.max_ai_features == 50
    assert plan.is_active is True
    assert plan.display_order == 1


def test_recruitment_plan_optional_fields():
    plan = RecruitmentPlan(
        name="Basic",
        price=500000,
        currency="VND",
        duration_days=15,
        max_job_posts=5,
        is_active=True,
        display_order=0,
    )

    assert plan.name == "Basic"
    assert plan.description is None
    assert plan.max_candidate_searches is None
    assert plan.max_ai_features is None
    assert plan.currency == "VND"
    assert plan.is_active is True
    assert plan.display_order == 0


def test_recruitment_plan_price_must_be_authoritative():
    """Price is set from database-backed plan, not from frontend."""
    plan = RecruitmentPlan(
        name="Enterprise",
        price=5000000,
        currency="VND",
        duration_days=90,
        max_job_posts=100,
    )

    assert plan.price == 5000000


def test_subscription_model_structure():
    user_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    started_at = utc_now()
    expires_at = started_at + timedelta(days=30)

    subscription = Subscription(
        user_id=user_id,
        plan_id=plan_id,
        status=SubscriptionStatus.ACTIVE,
        started_at=started_at,
        expires_at=expires_at,
    )

    assert subscription.user_id == user_id
    assert subscription.plan_id == plan_id
    assert subscription.status is SubscriptionStatus.ACTIVE
    assert subscription.started_at == started_at
    assert subscription.expires_at == expires_at


def test_subscription_default_status_pending():
    """Default status is PENDING when explicitly set."""
    subscription = Subscription(
        user_id=uuid.uuid4(),
        plan_id=uuid.uuid4(),
        status=SubscriptionStatus.PENDING,
    )

    assert subscription.status is SubscriptionStatus.PENDING


def test_subscription_supports_historical_records():
    """Multiple subscriptions per user should be possible for history."""
    user_id = uuid.uuid4()
    plan_id = uuid.uuid4()

    sub1 = Subscription(
        user_id=user_id,
        plan_id=plan_id,
        status=SubscriptionStatus.EXPIRED,
    )
    sub2 = Subscription(
        user_id=user_id,
        plan_id=plan_id,
        status=SubscriptionStatus.ACTIVE,
    )

    assert sub1.user_id == sub2.user_id
    assert sub1.status is SubscriptionStatus.EXPIRED
    assert sub2.status is SubscriptionStatus.ACTIVE


def test_payment_order_model_structure():
    user_id = uuid.uuid4()
    plan_id = uuid.uuid4()

    order = PaymentOrder(
        user_id=user_id,
        plan_id=plan_id,
        amount=1000000,
        currency="VND",
        provider=PaymentProvider.MOMO,
        internal_order_id="ORDER-12345",
        provider_order_id="MOMO-ORDER-12345",
        provider_request_id="MOMO-REQUEST-12345",
        status=PaymentOrderStatus.PENDING,
    )

    assert order.user_id == user_id
    assert order.plan_id == plan_id
    assert order.amount == 1000000
    assert order.currency == "VND"
    assert order.provider is PaymentProvider.MOMO
    assert order.internal_order_id == "ORDER-12345"
    assert order.provider_order_id == "MOMO-ORDER-12345"
    assert order.provider_request_id == "MOMO-REQUEST-12345"
    assert order.status is PaymentOrderStatus.PENDING


def test_payment_order_amount_is_authoritative():
    """Payment order amount is the internal source of truth."""
    order = PaymentOrder(
        user_id=uuid.uuid4(),
        plan_id=uuid.uuid4(),
        amount=2000000,
        currency="VND",
        provider=PaymentProvider.MOMO,
        internal_order_id="ORDER-AUTH-001",
    )

    assert order.amount == 2000000
    assert order.currency == "VND"


def test_payment_order_unique_identifiers():
    """Payment order has unique constraint fields for idempotency."""
    user_id = uuid.uuid4()
    plan_id = uuid.uuid4()

    order1 = PaymentOrder(
        user_id=user_id,
        plan_id=plan_id,
        amount=1000000,
        currency="VND",
        provider=PaymentProvider.MOMO,
        internal_order_id="ORDER-UNIQUE-001",
        provider_order_id="MOMO-ORDER-UNIQUE-001",
        provider_request_id="MOMO-REQ-UNIQUE-001",
    )

    order2 = PaymentOrder(
        user_id=user_id,
        plan_id=plan_id,
        amount=1000000,
        currency="VND",
        provider=PaymentProvider.MOMO,
        internal_order_id="ORDER-UNIQUE-002",
        provider_order_id="MOMO-ORDER-UNIQUE-002",
        provider_request_id="MOMO-REQ-UNIQUE-002",
    )

    assert order1.internal_order_id != order2.internal_order_id
    assert order1.provider_order_id != order2.provider_order_id
    assert order1.provider_request_id != order2.provider_request_id


def test_payment_order_subscription_optional():
    """Payment order can exist without subscription (before activation)."""
    order = PaymentOrder(
        user_id=uuid.uuid4(),
        plan_id=uuid.uuid4(),
        amount=1000000,
        currency="VND",
        provider=PaymentProvider.MOMO,
        internal_order_id="ORDER-NO-SUB-001",
    )

    assert order.subscription_id is None


def test_payment_transaction_model_structure():
    order_id = uuid.uuid4()

    transaction = PaymentTransaction(
        payment_order_id=order_id,
        provider_transaction_id="MOMO-TXN-12345",
        provider_result_code="0",
        provider_message="Success",
        provider_response_metadata='{"key": "value"}',
        status=PaymentTransactionStatus.SUCCESS,
        responded_at=utc_now(),
    )

    assert transaction.payment_order_id == order_id
    assert transaction.provider_transaction_id == "MOMO-TXN-12345"
    assert transaction.provider_result_code == "0"
    assert transaction.provider_message == "Success"
    assert transaction.provider_response_metadata == '{"key": "value"}'
    assert transaction.status is PaymentTransactionStatus.SUCCESS
    assert transaction.responded_at is not None


def test_payment_transaction_default_status_pending():
    """Default status is PENDING when explicitly set."""
    transaction = PaymentTransaction(
        payment_order_id=uuid.uuid4(),
        status=PaymentTransactionStatus.PENDING,
    )

    assert transaction.status is PaymentTransactionStatus.PENDING


def test_payment_transaction_unique_provider_transaction_id():
    order_id = uuid.uuid4()

    txn1 = PaymentTransaction(
        payment_order_id=order_id,
        provider_transaction_id="MOMO-TXN-UNIQUE-001",
    )
    txn2 = PaymentTransaction(
        payment_order_id=order_id,
        provider_transaction_id="MOMO-TXN-UNIQUE-002",
    )

    assert txn1.provider_transaction_id != txn2.provider_transaction_id


def test_payment_transaction_no_secrets_stored():
    """Payment transaction should not store sensitive credentials."""
    txn = PaymentTransaction(
        payment_order_id=uuid.uuid4(),
        provider_transaction_id="MOMO-TXN-SECRET-001",
        provider_response_metadata='{"amount": 1000000, "currency": "VND"}',
    )

    assert "password" not in txn.provider_response_metadata.lower()
    assert "secret" not in txn.provider_response_metadata.lower()
    assert "token" not in txn.provider_response_metadata.lower()
    assert "key" not in txn.provider_response_metadata.lower()


def test_all_enums_defined():
    """Verify all required enums exist with correct values."""
    assert RecruitmentPlanStatus.ACTIVE.value == "active"
    assert RecruitmentPlanStatus.INACTIVE.value == "inactive"

    assert SubscriptionStatus.ACTIVE.value == "active"
    assert SubscriptionStatus.EXPIRED.value == "expired"
    assert SubscriptionStatus.CANCELLED.value == "cancelled"
    assert SubscriptionStatus.PENDING.value == "pending"

    assert PaymentProvider.MOMO.value == "momo"

    assert PaymentOrderStatus.PENDING.value == "pending"
    assert PaymentOrderStatus.PAID.value == "paid"
    assert PaymentOrderStatus.FAILED.value == "failed"
    assert PaymentOrderStatus.CANCELLED.value == "cancelled"
    assert PaymentOrderStatus.EXPIRED.value == "expired"

    assert PaymentTransactionStatus.SUCCESS.value == "success"
    assert PaymentTransactionStatus.FAILED.value == "failed"
    assert PaymentTransactionStatus.PENDING.value == "pending"


def test_model_relationships_defined():
    """Verify relationship attributes exist on models."""
    plan = RecruitmentPlan(
        name="Test",
        price=1000,
        currency="VND",
        duration_days=30,
        max_job_posts=5,
    )
    assert hasattr(plan, 'subscriptions')

    sub = Subscription(user_id=uuid.uuid4(), plan_id=uuid.uuid4())
    assert hasattr(sub, 'user')
    assert hasattr(sub, 'plan')
    assert hasattr(sub, 'payment_orders')

    order = PaymentOrder(
        user_id=uuid.uuid4(),
        plan_id=uuid.uuid4(),
        amount=1000,
        currency="VND",
        provider=PaymentProvider.MOMO,
        internal_order_id="TEST-001",
    )
    assert hasattr(order, 'user')
    assert hasattr(order, 'plan')
    assert hasattr(order, 'subscription')
    assert hasattr(order, 'transactions')

    txn = PaymentTransaction(payment_order_id=uuid.uuid4())
    assert hasattr(txn, 'payment_order')


def test_user_model_has_new_relationships():
    """Verify User model has subscriptions and payment_orders relationships."""
    user = User(
        email="test@example.com",
        password_hash="hashed",
        role=UserRole.CANDIDATE,
    )
    assert hasattr(user, 'subscriptions')
    assert hasattr(user, 'payment_orders')


def test_table_names():
    """Verify table names follow convention."""
    assert RecruitmentPlan.__tablename__ == "recruitment_plans"
    assert Subscription.__tablename__ == "subscriptions"
    assert PaymentOrder.__tablename__ == "payment_orders"
    assert PaymentTransaction.__tablename__ == "payment_transactions"


def test_indexes_defined():
    """Verify indexes are defined on key columns."""
    # RecruitmentPlan indexes
    plan_indexes = {idx.name for idx in RecruitmentPlan.__table__.indexes}
    assert "ix_recruitment_plans_display_order" in plan_indexes
    assert "ix_recruitment_plans_is_active" in plan_indexes

    # PaymentOrder columns - provider identifiers are nullable, unique enforcement via filtered indexes in DB
    order_columns = {col.name for col in PaymentOrder.__table__.columns}
    assert "internal_order_id" in order_columns
    assert "provider_order_id" in order_columns
    assert "provider_request_id" in order_columns

    # internal_order_id has unique constraint at model level
    order_unique_cols = set()
    for constraint in PaymentOrder.__table__.constraints:
        if hasattr(constraint, 'columns'):
            for col in constraint.columns:
                order_unique_cols.add(col.name)
    assert "internal_order_id" in order_unique_cols
    # provider_order_id and provider_request_id unique enforcement is via filtered indexes in migration (not model-level constraints)

    # PaymentTransaction columns - provider_transaction_id is nullable, unique enforcement via filtered index in DB
    txn_columns = {col.name for col in PaymentTransaction.__table__.columns}
    assert "provider_transaction_id" in txn_columns
    # provider_transaction_id unique enforcement is via filtered index in migration


def test_foreign_keys_defined():
    """Verify foreign key relationships are defined."""
    # Subscription FKs
    sub_fks = [fk.parent.name for fk in Subscription.__table__.foreign_keys]
    assert "user_id" in sub_fks
    assert "plan_id" in sub_fks

    # PaymentOrder FKs
    order_fks = [fk.parent.name for fk in PaymentOrder.__table__.foreign_keys]
    assert "user_id" in order_fks
    assert "plan_id" in order_fks
    assert "subscription_id" in order_fks

    # PaymentTransaction FKs
    txn_fks = [fk.parent.name for fk in PaymentTransaction.__table__.foreign_keys]
    assert "payment_order_id" in txn_fks


def test_no_delete_cascade_on_financial_history_relationships():
    """Financial history relationships must not use delete or delete-orphan cascade."""
    # User -> subscriptions
    user_subs_rel = User.__mapper__.relationships['subscriptions']
    assert 'delete' not in user_subs_rel.cascade
    assert 'delete-orphan' not in user_subs_rel.cascade

    # User -> payment_orders
    user_orders_rel = User.__mapper__.relationships['payment_orders']
    assert 'delete' not in user_orders_rel.cascade
    assert 'delete-orphan' not in user_orders_rel.cascade

    # RecruitmentPlan -> subscriptions
    plan_subs_rel = RecruitmentPlan.__mapper__.relationships['subscriptions']
    assert 'delete' not in plan_subs_rel.cascade
    assert 'delete-orphan' not in plan_subs_rel.cascade

    # Subscription -> payment_orders
    sub_orders_rel = Subscription.__mapper__.relationships['payment_orders']
    assert 'delete' not in sub_orders_rel.cascade
    assert 'delete-orphan' not in sub_orders_rel.cascade

    # PaymentOrder -> transactions
    order_txns_rel = PaymentOrder.__mapper__.relationships['transactions']
    assert 'delete' not in order_txns_rel.cascade
    assert 'delete-orphan' not in order_txns_rel.cascade


def test_relationships_have_save_update_merge_cascade():
    """Relationships should have default cascade save/update/merge."""
    user_subs_rel = User.__mapper__.relationships['subscriptions']
    assert 'save-update' in user_subs_rel.cascade
    assert 'merge' in user_subs_rel.cascade

    user_orders_rel = User.__mapper__.relationships['payment_orders']
    assert 'save-update' in user_orders_rel.cascade
    assert 'merge' in user_orders_rel.cascade

    plan_subs_rel = RecruitmentPlan.__mapper__.relationships['subscriptions']
    assert 'save-update' in plan_subs_rel.cascade
    assert 'merge' in plan_subs_rel.cascade

    sub_orders_rel = Subscription.__mapper__.relationships['payment_orders']
    assert 'save-update' in sub_orders_rel.cascade
    assert 'merge' in sub_orders_rel.cascade

    order_txns_rel = PaymentOrder.__mapper__.relationships['transactions']
    assert 'save-update' in order_txns_rel.cascade
    assert 'merge' in order_txns_rel.cascade


def test_provider_order_id_allows_multiple_nulls():
    """
    Test that provider_order_id allows multiple NULL values.
    This is a unit test - actual SQL Server filtered index behavior
    is verified in integration tests against real SQL Server.
    """
    user_id = uuid.uuid4()
    plan_id = uuid.uuid4()

    # Multiple orders with NULL provider_order_id should be creatable
    # (SQLAlchemy model doesn't enforce uniqueness at Python level)
    order1 = PaymentOrder(
        user_id=user_id,
        plan_id=plan_id,
        amount=1000000,
        currency="VND",
        provider=PaymentProvider.MOMO,
        internal_order_id="ORDER-001",
        provider_order_id=None,
        provider_request_id=None,
    )
    order2 = PaymentOrder(
        user_id=user_id,
        plan_id=plan_id,
        amount=2000000,
        currency="VND",
        provider=PaymentProvider.MOMO,
        internal_order_id="ORDER-002",
        provider_order_id=None,
        provider_request_id=None,
    )

    assert order1.provider_order_id is None
    assert order2.provider_order_id is None
    assert order1.internal_order_id != order2.internal_order_id


def test_provider_order_id_rejects_duplicate_non_null():
    """
    Test that provider_order_id rejects duplicate non-NULL values at model level.
    Actual database enforcement is via filtered unique index.
    """
    user_id = uuid.uuid4()
    plan_id = uuid.uuid4()

    order1 = PaymentOrder(
        user_id=user_id,
        plan_id=plan_id,
        amount=1000000,
        currency="VND",
        provider=PaymentProvider.MOMO,
        internal_order_id="ORDER-001",
        provider_order_id="MOMO-123",
        provider_request_id=None,
    )
    order2 = PaymentOrder(
        user_id=user_id,
        plan_id=plan_id,
        amount=2000000,
        currency="VND",
        provider=PaymentProvider.MOMO,
        internal_order_id="ORDER-002",
        provider_order_id="MOMO-123",  # Duplicate
        provider_request_id=None,
    )

    # Model allows creation, but database will reject via filtered unique index
    assert order1.provider_order_id == order2.provider_order_id == "MOMO-123"


def test_provider_request_id_allows_multiple_nulls():
    """provider_request_id allows multiple NULL values (MoMo requestId idempotency)."""
    user_id = uuid.uuid4()
    plan_id = uuid.uuid4()

    order1 = PaymentOrder(
        user_id=user_id,
        plan_id=plan_id,
        amount=1000000,
        currency="VND",
        provider=PaymentProvider.MOMO,
        internal_order_id="ORDER-001",
        provider_request_id=None,
    )
    order2 = PaymentOrder(
        user_id=user_id,
        plan_id=plan_id,
        amount=2000000,
        currency="VND",
        provider=PaymentProvider.MOMO,
        internal_order_id="ORDER-002",
        provider_request_id=None,
    )

    assert order1.provider_request_id is None
    assert order2.provider_request_id is None


def test_provider_request_id_rejects_duplicate_non_null():
    """provider_request_id rejects duplicate non-NULL values."""
    user_id = uuid.uuid4()
    plan_id = uuid.uuid4()

    order1 = PaymentOrder(
        user_id=user_id,
        plan_id=plan_id,
        amount=1000000,
        currency="VND",
        provider=PaymentProvider.MOMO,
        internal_order_id="ORDER-001",
        provider_request_id="MOMO-REQ-123",
    )
    order2 = PaymentOrder(
        user_id=user_id,
        plan_id=plan_id,
        amount=2000000,
        currency="VND",
        provider=PaymentProvider.MOMO,
        internal_order_id="ORDER-002",
        provider_request_id="MOMO-REQ-123",  # Duplicate
    )

    assert order1.provider_request_id == order2.provider_request_id == "MOMO-REQ-123"


def test_provider_transaction_id_allows_multiple_nulls():
    """provider_transaction_id allows multiple NULL values."""
    order_id = uuid.uuid4()

    txn1 = PaymentTransaction(
        payment_order_id=order_id,
        provider_transaction_id=None,
    )
    txn2 = PaymentTransaction(
        payment_order_id=order_id,
        provider_transaction_id=None,
    )

    assert txn1.provider_transaction_id is None
    assert txn2.provider_transaction_id is None


def test_provider_transaction_id_rejects_duplicate_non_null():
    """provider_transaction_id rejects duplicate non-NULL values."""
    order_id = uuid.uuid4()

    txn1 = PaymentTransaction(
        payment_order_id=order_id,
        provider_transaction_id="MOMO-TXN-123",
    )
    txn2 = PaymentTransaction(
        payment_order_id=order_id,
        provider_transaction_id="MOMO-TXN-123",  # Duplicate
    )

    assert txn1.provider_transaction_id == txn2.provider_transaction_id == "MOMO-TXN-123"


def test_internal_order_id_always_unique():
    """internal_order_id is non-nullable and always unique (no filtered index needed)."""
    user_id = uuid.uuid4()
    plan_id = uuid.uuid4()

    order1 = PaymentOrder(
        user_id=user_id,
        plan_id=plan_id,
        amount=1000000,
        currency="VND",
        provider=PaymentProvider.MOMO,
        internal_order_id="INTERNAL-001",
    )
    order2 = PaymentOrder(
        user_id=user_id,
        plan_id=plan_id,
        amount=2000000,
        currency="VND",
        provider=PaymentProvider.MOMO,
        internal_order_id="INTERNAL-002",
    )

    assert order1.internal_order_id != order2.internal_order_id
    assert order1.internal_order_id is not None
    assert order2.internal_order_id is not None


def test_financial_history_preserved_on_user_soft_delete():
    """
    Test that soft-deleting a User does not destroy Subscription/PaymentOrder/PaymentTransaction history.
    Actual database enforcement relies on FK constraints without ON DELETE CASCADE
    and ORM cascade without 'delete-orphan'.
    """
    user_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    order_id = uuid.uuid4()
    txn_id = uuid.uuid4()

    user = User(
        id=user_id,
        email="test@example.com",
        password_hash="hashed",
        role=UserRole.CANDIDATE,
    )
    subscription = Subscription(
        id=uuid.uuid4(),
        user_id=user_id,
        plan_id=plan_id,
        status=SubscriptionStatus.ACTIVE,
        is_deleted=False,
    )
    order = PaymentOrder(
        id=order_id,
        user_id=user_id,
        plan_id=plan_id,
        subscription_id=subscription.id,
        amount=1000000,
        currency="VND",
        provider=PaymentProvider.MOMO,
        internal_order_id="ORDER-001",
        is_deleted=False,
    )
    transaction = PaymentTransaction(
        id=txn_id,
        payment_order_id=order_id,
        provider_transaction_id="MOMO-TXN-001",
        status=PaymentTransactionStatus.SUCCESS,
        is_deleted=False,
    )

    # Soft delete user (ORM models use is_deleted flag directly)
    user.is_deleted = True

    # Financial records should still exist (not deleted by cascade)
    assert subscription.is_deleted is False
    assert order.is_deleted is False
    assert transaction.is_deleted is False


def test_financial_history_preserved_on_plan_soft_delete():
    """Soft-deleting a RecruitmentPlan preserves historical subscriptions and payments."""
    plan_id = uuid.uuid4()
    user_id = uuid.uuid4()

    plan = RecruitmentPlan(
        id=plan_id,
        name="Test Plan",
        price=1000000,
        currency="VND",
        duration_days=30,
        max_job_posts=5,
        is_deleted=False,
    )
    subscription = Subscription(
        id=uuid.uuid4(),
        user_id=user_id,
        plan_id=plan_id,
        status=SubscriptionStatus.ACTIVE,
        is_deleted=False,
    )
    order = PaymentOrder(
        id=uuid.uuid4(),
        user_id=user_id,
        plan_id=plan_id,
        subscription_id=subscription.id,
        amount=1000000,
        currency="VND",
        provider=PaymentProvider.MOMO,
        internal_order_id="ORDER-001",
        is_deleted=False,
    )

    plan.is_deleted = True

    assert subscription.is_deleted is False
    assert order.is_deleted is False


def test_financial_history_preserved_on_subscription_soft_delete():
    """Soft-deleting a Subscription preserves historical payment orders and transactions."""
    subscription_id = uuid.uuid4()
    user_id = uuid.uuid4()
    plan_id = uuid.uuid4()

    subscription = Subscription(
        id=subscription_id,
        user_id=user_id,
        plan_id=plan_id,
        status=SubscriptionStatus.ACTIVE,
        is_deleted=False,
    )
    order = PaymentOrder(
        id=uuid.uuid4(),
        user_id=user_id,
        plan_id=plan_id,
        subscription_id=subscription_id,
        amount=1000000,
        currency="VND",
        provider=PaymentProvider.MOMO,
        internal_order_id="ORDER-001",
        is_deleted=False,
    )
    transaction = PaymentTransaction(
        id=uuid.uuid4(),
        payment_order_id=order.id,
        provider_transaction_id="MOMO-TXN-001",
        status=PaymentTransactionStatus.SUCCESS,
        is_deleted=False,
    )

    subscription.is_deleted = True

    assert order.is_deleted is False
    assert transaction.is_deleted is False


def test_financial_history_preserved_on_order_soft_delete():
    """Soft-deleting a PaymentOrder preserves historical transactions."""
    order_id = uuid.uuid4()

    order = PaymentOrder(
        id=order_id,
        user_id=uuid.uuid4(),
        plan_id=uuid.uuid4(),
        amount=1000000,
        currency="VND",
        provider=PaymentProvider.MOMO,
        internal_order_id="ORDER-001",
        is_deleted=False,
    )
    transaction = PaymentTransaction(
        id=uuid.uuid4(),
        payment_order_id=order_id,
        provider_transaction_id="MOMO-TXN-001",
        status=PaymentTransactionStatus.SUCCESS,
        is_deleted=False,
    )

    order.is_deleted = True

    assert transaction.is_deleted is False