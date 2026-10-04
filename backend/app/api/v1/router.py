from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    admin_plans,
    admin_subscriptions,
    ai,
    applications,
    auth,
    companies,
    health,
    jobs,
    notifications,
    payments,
    plans,
    subscriptions,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health Check"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(
    companies.router, prefix="/companies", tags=["Companies"]
)
api_router.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
api_router.include_router(
    applications.router, prefix="/applications", tags=["Applications"]
)
api_router.include_router(
    notifications.router, prefix="/notifications", tags=["Notifications"]
)
api_router.include_router(ai.router, prefix="/ai", tags=["AI Engine"])
api_router.include_router(payments.router, tags=["VNPAY Payments"])
api_router.include_router(admin.router)
api_router.include_router(plans.router)
api_router.include_router(subscriptions.router)
api_router.include_router(admin_plans.router)
api_router.include_router(admin_subscriptions.router)
