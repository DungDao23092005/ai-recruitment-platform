import pytest
import uuid
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import engine
from app.database.base_class import Base
from app.models import PaymentOrder, PaymentTransaction, RecruitmentPlan, Subscription, User
from app.repositories import PaymentOrderRepository, PaymentTransactionRepository, RecruitmentPlanRepository, SubscriptionRepository
from app.services.payment_service import PaymentService
from app.services.payment_providers.vnpay import VNPAYProvider


@pytest.fixture(scope="function")
async def db_session() -> AsyncSession:
    """Create a fresh database session for each test."""
    async with AsyncSession(engine) as session:
        yield session


@pytest.fixture
def vnpay_provider():
    """Provide a VNPAY provider instance."""
    return VNPAYProvider()


@pytest.fixture
def sample_vnpay_params(vnpay_provider):
    """Generate sample VNPAY parameters with valid signature."""
    params = vnpay_provider.build_payment_params(
        amount=100000,
        order_id="TEST-001",
        order_info="Test order",
        client_ip="127.0.0.1",
    )
    # Add valid signature
    secure_hash = vnpay_provider.generate_secure_hash(params)
    params["vnp_SecureHash"] = secure_hash
    params["vnp_SecureHashType"] = "SHA512"
    return params