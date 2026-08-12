from app.repositories.application_repository import ApplicationRepository
from app.repositories.base import BaseRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.interfaces.base_interface import BaseRepositoryInterface
from app.repositories.job_repository import JobRepository
from app.repositories.user_repository import UserRepository

__all__ = [
    "BaseRepository",
    "BaseRepositoryInterface",
    "UserRepository",
    "CompanyRepository",
    "JobRepository",
    "ApplicationRepository",
]
