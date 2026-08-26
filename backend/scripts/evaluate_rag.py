#!/usr/bin/env python
"""RAG Evaluation Script with Mock ContextResolver.

This script evaluates the RAG system using a deterministic mock ContextResolver
that provides authorized entities matching the golden dataset IDs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.ai.interfaces.base_provider import BaseReranker, BaseVectorRepository, BaseEmbeddingProvider, RerankCandidate, RerankResult
from app.ai.providers.gemini_provider import GeminiLLMProvider
from app.ai.vector_db.qdrant_client import QdrantVectorRepository
from app.ai.reranking.cross_encoder_reranker import CrossEncoderReranker
from app.core.config import settings
from app.core.exceptions import AIError
from app.domain.enums import UserRole
from app.models import User
from app.schemas.ai_chat import ChatMessage, ChatResponse, ChatSource
from app.schemas.ai_job import ParsedJobSchema
from app.schemas.ai_resume import ParsedResumeSchema, WorkExperienceSchema, EducationSchema, ProjectSchema
from app.schemas.ai_match import MatchResultSchema
from app.services.rag_chat_service import RAGChatService, RAGContext, RAGTelemetry, EmbeddingService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GOLDEN_DATASET_PATH = Path(__file__).parent.parent / "tests" / "evaluation" / "rag_golden_dataset.json"

# Global flag for CrossEncoder skipping
SKIP_CROSS_ENCODER = False


def can_load_cross_encoder() -> bool:
    """Check if CrossEncoder can be safely loaded without crashing.

    On Windows, sentence_transformers CrossEncoder may cause access violation.
    This function attempts to detect if the model can be loaded safely.
    """
    try:
        from sentence_transformers import CrossEncoder
        # Try to create a minimal model to test if it works
        model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        # Try a simple prediction
        result = model.predict([["test", "test"]])
        return len(result) == 1
    except Exception:
        return False

# Tenant ownership for security-aware evaluation
TENANT_A = "tenant_a"
TENANT_B = "tenant_b"

# Deterministic tenant assignments for mock entities
JOB_TENANT_MAP = {
    "11111111-1111-1111-1111-111111111111": TENANT_A,  # Python Developer
    "22222222-2222-2222-2222-222222222222": TENANT_A,  # Frontend Developer
    "33333333-3333-3333-3333-333333333333": TENANT_A,  # Senior Python Developer
    "44444444-4444-4444-4444-444444444444": TENANT_A,  # DevOps Engineer
    "55555555-5555-5555-5555-555555555555": TENANT_A,  # ML Engineer
    "66666666-6666-6666-6666-666666666666": TENANT_B,  # Backend Architect
    "77777777-7777-7777-7777-777777777777": TENANT_B,  # Platform Engineer
    "88888888-8888-8888-8888-888888888888": TENANT_B,  # ML Engineer - TensorFlow
    "99999999-9999-9999-9999-999999999999": TENANT_B,  # Senior Go Developer
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": TENANT_B,  # Frontend Developer
    "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb": TENANT_B,  # DevOps Engineer
    "cccccccc-cccc-cccc-cccc-cccccccccccc": TENANT_B,  # Data Engineer
}

CANDIDATE_TENANT_MAP = {
    "dddddddd-dddd-dddd-dddd-dddddddddddd": TENANT_A,  # Python Developer
    "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee": TENANT_A,  # React Developer
    "ffffffff-ffff-ffff-ffff-ffffffffffff": TENANT_A,  # Senior Python Engineer
    "12121212-1212-1212-1212-121212121212": TENANT_B,  # Java Developer
    "34343434-3434-3434-3434-343434343434": TENANT_B,  # ML Researcher
}

ALL_MOCK_JOB_IDS = set(JOB_TENANT_MAP.keys())
ALL_MOCK_CANDIDATE_IDS = set(CANDIDATE_TENANT_MAP.keys())


def _get_actor_tenant(actor_user: User | UserRole) -> str:
    """Get tenant for actor user."""
    user_role = actor_user if isinstance(actor_user, UserRole) else getattr(actor_user, "role", UserRole.CANDIDATE)
    # For evaluation: CANDIDATE/RECRUITER -> TENANT_A, ADMIN -> both (handled in resolver)
    if user_role == UserRole.ADMIN:
        return "admin"
    return TENANT_A


DETERMINISTIC_JOB_UUIDS = {
    "11111111-1111-1111-1111-111111111111": ParsedJobSchema(
        title="Python Developer",
        summary="We are looking for a Python Developer to join our team. Build backend services with FastAPI and PostgreSQL.",
        required_skills=["Python", "FastAPI", "PostgreSQL"],
        preferred_skills=["Docker", "AWS"],
        responsibilities=["Develop backend services", "Write clean code", "Participate in code reviews"],
        seniority="mid",
        experience_years=3,
        education_level="bachelor",
    ),
    "22222222-2222-2222-2222-222222222222": ParsedJobSchema(
        title="Frontend Developer - React/TypeScript",
        summary="Frontend developer position requiring React and TypeScript expertise. Build responsive user interfaces.",
        required_skills=["React", "TypeScript", "Redux"],
        preferred_skills=["Next.js", "Tailwind CSS"],
        responsibilities=["Build user interfaces", "Optimize performance", "Collaborate with designers"],
        seniority="mid",
        experience_years=3,
        education_level="bachelor",
    ),
    "33333333-3333-3333-3333-333333333333": ParsedJobSchema(
        title="Senior Python Developer",
        summary="Senior Python developer with AWS and Docker experience. Architect scalable backend solutions.",
        required_skills=["Python", "FastAPI", "AWS", "Docker"],
        preferred_skills=["Kubernetes", "Terraform"],
        responsibilities=["Architect solutions", "Mentor junior developers", "Lead technical decisions"],
        seniority="senior",
        experience_years=5,
        education_level="bachelor",
    ),
    "44444444-4444-4444-4444-444444444444": ParsedJobSchema(
        title="DevOps Engineer",
        summary="DevOps engineer with 5 years experience in cloud infrastructure. Manage AWS, Docker, Kubernetes, Terraform.",
        required_skills=["AWS", "Docker", "Kubernetes", "Terraform"],
        preferred_skills=["Python", "Go"],
        responsibilities=["Manage cloud infrastructure", "CI/CD pipelines", "Monitoring and alerting"],
        seniority="senior",
        experience_years=5,
        education_level="bachelor",
    ),
    "55555555-5555-5555-5555-555555555555": ParsedJobSchema(
        title="Machine Learning Engineer",
        summary="ML Engineer position requiring Master's degree in Computer Science. Build and deploy ML models.",
        required_skills=["Python", "TensorFlow", "PyTorch", "Scikit-learn"],
        preferred_skills=["Kubernetes", "MLOps"],
        responsibilities=["Build ML models", "Deploy to production", "Research new techniques"],
        seniority="mid",
        experience_years=3,
        education_level="master",
    ),
    "66666666-6666-6666-6666-666666666666": ParsedJobSchema(
        title="Backend Architect",
        summary="Backend architect specializing in microservices architecture. Design system architecture with Python, Go, gRPC, Kubernetes.",
        required_skills=["Python", "Go", "Microservices", "gRPC", "Kubernetes"],
        preferred_skills=["Service Mesh", "Event-driven architecture"],
        responsibilities=["Design system architecture", "Define technical standards", "Code review"],
        seniority="lead",
        experience_years=8,
        education_level="master",
    ),
    "77777777-7777-7777-7777-777777777777": ParsedJobSchema(
        title="Platform Engineer",
        summary="Platform engineer with Kubernetes and CI/CD experience. Build platform tools, automate deployments.",
        required_skills=["Kubernetes", "CI/CD", "Docker", "AWS", "Terraform"],
        preferred_skills=["Python", "Go", "Prometheus"],
        responsibilities=["Build platform tools", "Automate deployments", "Improve developer experience"],
        seniority="senior",
        experience_years=5,
        education_level="bachelor",
    ),
    "88888888-8888-8888-8888-888888888888": ParsedJobSchema(
        title="ML Engineer - TensorFlow",
        summary="Machine Learning Engineer specializing in TensorFlow. Train and deploy ML models, optimize performance.",
        required_skills=["Python", "TensorFlow", "Keras", "Machine Learning"],
        preferred_skills=["PyTorch", "Kubernetes", "MLOps"],
        responsibilities=["Train and deploy ML models", "Optimize model performance", "Data pipeline"],
        seniority="mid",
        experience_years=3,
        education_level="master",
    ),
    "99999999-9999-9999-9999-999999999999": ParsedJobSchema(
        title="Senior Go Developer",
        summary="Senior Go developer with gRPC and Kubernetes expertise. Build high-performance services.",
        required_skills=["Go", "gRPC", "Kubernetes", "Docker", "Microservices"],
        preferred_skills=["Python", "Service Mesh"],
        responsibilities=["Build high-performance services", "Design APIs", "Mentor team"],
        seniority="senior",
        experience_years=6,
        education_level="bachelor",
    ),
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": ParsedJobSchema(
        title="Frontend Developer - React/Redux/TypeScript",
        summary="Frontend developer with React, Redux, and TypeScript. Develop frontend features, state management.",
        required_skills=["React", "Redux", "TypeScript", "JavaScript"],
        preferred_skills=["Next.js", "GraphQL", "Testing"],
        responsibilities=["Develop frontend features", "State management", "Code quality"],
        seniority="mid",
        experience_years=4,
        education_level="bachelor",
    ),
    "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb": ParsedJobSchema(
        title="DevOps Engineer - AWS/Terraform/Docker",
        summary="DevOps engineer with AWS, Terraform, and Docker. Infrastructure as code, automation, security.",
        required_skills=["AWS", "Terraform", "Docker", "Linux", "CI/CD"],
        preferred_skills=["Kubernetes", "Python", "Monitoring"],
        responsibilities=["Infrastructure as code", "Automation", "Security hardening"],
        seniority="senior",
        experience_years=5,
        education_level="bachelor",
    ),
    "cccccccc-cccc-cccc-cccc-cccccccccccc": ParsedJobSchema(
        title="Data Engineer - Spark/Kafka/Python",
        summary="Data engineer with Spark, Kafka, and Python experience. Build data pipelines, optimize processing.",
        required_skills=["Python", "Spark", "Kafka", "SQL", "Airflow"],
        preferred_skills=["AWS", "DBT", "Data modeling"],
        responsibilities=["Build data pipelines", "Optimize data processing", "Data quality"],
        seniority="mid",
        experience_years=4,
        education_level="bachelor",
    ),
}

DETERMINISTIC_CANDIDATE_UUIDS = {
    "dddddddd-dddd-dddd-dddd-dddddddddddd": ParsedResumeSchema(
        title="Python Developer",
        summary="Experienced Python developer with 3 years experience. Built backend services with FastAPI, PostgreSQL, Docker.",
        skills=["Python", "FastAPI", "PostgreSQL", "Docker"],
        technical_skills=["Python", "FastAPI", "PostgreSQL", "Docker", "Git"],
        job_titles=["Python Developer", "Backend Developer"],
        total_years_experience=3,
        experiences=[
            WorkExperienceSchema(
                position="Python Developer",
                company="TechCorp",
                description="Built backend services with Python and FastAPI. 3 years experience with Docker and PostgreSQL.",
            ),
        ],
        education=[
            EducationSchema(
                degree="Bachelor",
                field_of_study="Computer Science",
                institution="University of Technology",
            ),
        ],
        projects=[
            ProjectSchema(
                name="E-commerce API",
                description="REST API built with FastAPI and PostgreSQL",
            ),
        ],
    ),
    "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee": ParsedResumeSchema(
        title="React Developer",
        summary="Frontend developer specializing in React and TypeScript. Build user interfaces with Redux, Next.js, Tailwind.",
        skills=["React", "TypeScript", "Redux", "Next.js"],
        technical_skills=["React", "TypeScript", "Redux", "Next.js", "Tailwind CSS"],
        job_titles=["Frontend Developer", "React Developer"],
        total_years_experience=4,
        experiences=[
            WorkExperienceSchema(
                position="Frontend Developer",
                company="WebApp Inc",
                description="Built user interfaces with React and TypeScript. 4 years experience with Redux and Next.js.",
            ),
        ],
        education=[
            EducationSchema(
                degree="Bachelor",
                field_of_study="Computer Science",
                institution="Tech University",
            ),
        ],
        projects=[
            ProjectSchema(
                name="Dashboard Application",
                description="Admin dashboard with React, Redux, and TypeScript",
            ),
        ],
    ),
    "ffffffff-ffff-ffff-ffff-ffffffffffff": ParsedResumeSchema(
        title="Senior Python Engineer",
        summary="Senior Python engineer with 7 years experience. Led backend development with Django, FastAPI, PostgreSQL, AWS, Docker, Kubernetes.",
        skills=["Python", "Django", "FastAPI", "PostgreSQL", "AWS", "Docker", "Kubernetes"],
        technical_skills=["Python", "Django", "FastAPI", "PostgreSQL", "AWS", "Docker", "Kubernetes"],
        job_titles=["Senior Python Engineer", "Tech Lead"],
        total_years_experience=7,
        experiences=[
            WorkExperienceSchema(
                position="Senior Python Engineer",
                company="ScaleUp Inc",
                description="Led backend development with Python. 7 years experience with Python, Django, FastAPI, PostgreSQL, AWS, Docker, Kubernetes.",
            ),
        ],
        education=[
            EducationSchema(
                degree="Master",
                field_of_study="Computer Science",
                institution="Stanford University",
            ),
        ],
        projects=[
            ProjectSchema(
                name="Distributed System",
                description="Built distributed system with Python, Kubernetes, and gRPC",
            ),
        ],
    ),
    "12121212-1212-1212-1212-121212121212": ParsedResumeSchema(
        title="Java Developer",
        summary="Java developer with 3 years experience. Built enterprise applications with Java and Spring Boot, PostgreSQL, Docker.",
        skills=["Java", "Spring Boot", "PostgreSQL", "Docker"],
        technical_skills=["Java", "Spring Boot", "PostgreSQL", "Docker", "Maven"],
        job_titles=["Java Developer", "Backend Developer"],
        total_years_experience=3,
        experiences=[
            WorkExperienceSchema(
                position="Java Developer",
                company="JavaCorp",
                description="Built enterprise applications with Java and Spring Boot. 3 years Java experience with PostgreSQL and Docker.",
            ),
        ],
        education=[
            EducationSchema(
                degree="Bachelor",
                field_of_study="Computer Science",
                institution="State University",
            ),
        ],
        projects=[
            ProjectSchema(
                name="Enterprise Application",
                description="Large scale enterprise application with Spring Boot",
            ),
        ],
    ),
    "34343434-3434-3434-3434-343434343434": ParsedResumeSchema(
        title="ML Researcher",
        summary="ML Researcher with Master's in CS from Stanford. Research in machine learning, PyTorch, TensorFlow.",
        skills=["Python", "PyTorch", "TensorFlow", "Research"],
        technical_skills=["Python", "PyTorch", "TensorFlow", "Research", "Mathematics"],
        job_titles=["ML Researcher", "Data Scientist"],
        total_years_experience=2,
        experiences=[
            WorkExperienceSchema(
                position="ML Researcher",
                company="AI Lab",
                description="Research in machine learning. Master's from Stanford. Published research on transformer architectures.",
            ),
        ],
        education=[
            EducationSchema(
                degree="Master",
                field_of_study="Computer Science",
                institution="Stanford University",
            ),
        ],
        projects=[
            ProjectSchema(
                name="Research Paper",
                description="Published research on transformer architectures",
            ),
        ],
    ),
}


class MockContextResolver:
    """Evaluation-only in-memory ContextResolver.

    Provides deterministic jobs/resumes whose IDs correspond exactly to IDs
    declared in the golden dataset. Simulates the authorization boundary
    without removing it. Implements tenant-based authorization.
    """

    def __init__(self, actor_user: User | UserRole):
        self.actor_user = actor_user
        self.user_role = actor_user if isinstance(actor_user, UserRole) else getattr(actor_user, "role", UserRole.CANDIDATE)
        self.actor_tenant = _get_actor_tenant(actor_user)

    def _is_authorized_job(self, job_id: str) -> bool:
        """Check if job is authorized for the actor based on tenant ownership."""
        if self.user_role == UserRole.ADMIN:
            return job_id in ALL_MOCK_JOB_IDS
        elif self.user_role == UserRole.RECRUITER:
            # Recruiter can only access jobs from their tenant
            job_tenant = JOB_TENANT_MAP.get(job_id)
            return job_tenant == self.actor_tenant
        else:
            # CANDIDATE - only published jobs (all our mock jobs are considered published)
            job_tenant = JOB_TENANT_MAP.get(job_id)
            return job_tenant == self.actor_tenant

    def _is_authorized_candidate(self, candidate_id: str) -> bool:
        """Check if candidate is authorized for the actor based on tenant ownership."""
        if self.user_role == UserRole.ADMIN:
            return candidate_id in ALL_MOCK_CANDIDATE_IDS
        elif self.user_role == UserRole.RECRUITER:
            # Recruiter can only access candidates from their tenant
            candidate_tenant = CANDIDATE_TENANT_MAP.get(candidate_id)
            return candidate_tenant == self.actor_tenant
        else:
            # CANDIDATE - cannot access other candidates
            return False

    async def resolve_jobs(self, job_ids: list[uuid.UUID], actor_user: User | UserRole) -> dict[uuid.UUID, ParsedJobSchema]:
        """Resolve jobs with authorization - returns only authorized jobs."""
        result = {}
        for job_id in job_ids:
            job_id_str = str(job_id)
            if job_id_str in DETERMINISTIC_JOB_UUIDS and self._is_authorized_job(job_id_str):
                result[job_id] = DETERMINISTIC_JOB_UUIDS[job_id_str]
        return result

    async def resolve_resumes(self, candidate_ids: list[uuid.UUID], actor_user: User | UserRole, include_primary_only: bool = True) -> dict[uuid.UUID, ParsedResumeSchema]:
        """Resolve resumes with authorization - returns only authorized resumes."""
        result = {}
        for candidate_id in candidate_ids:
            candidate_id_str = str(candidate_id)
            if candidate_id_str in DETERMINISTIC_CANDIDATE_UUIDS and self._is_authorized_candidate(candidate_id_str):
                result[candidate_id] = DETERMINISTIC_CANDIDATE_UUIDS[candidate_id_str]
        return result


class MockVectorRepository(BaseVectorRepository):
    """Mock vector repository that returns deterministic, query-dependent results for evaluation.

    Uses cosine similarity between query embedding and document embedding for scoring.
    This creates realistic Qdrant-vs-semantic ranking disagreements for reranking evaluation.
    """

    def __init__(self, embedding_provider=None):
        self.job_documents = {}
        self.resume_documents = {}
        self.embedding_provider = embedding_provider or MockEmbeddingProvider()
        self._build_documents()

    def _build_documents(self):
        """Build document index with content for query-dependent scoring."""
        for job_id, job in DETERMINISTIC_JOB_UUIDS.items():
            # Combine all searchable text fields
            content_parts = []
            if job.title:
                content_parts.append(job.title)
            if job.summary:
                content_parts.append(job.summary)
            if job.required_skills:
                content_parts.extend(job.required_skills)
            if job.preferred_skills:
                content_parts.extend(job.preferred_skills)
            if job.responsibilities:
                content_parts.extend(job.responsibilities)

            content_text = " ".join(content_parts)
            self.job_documents[job_id] = {
                "id": job_id,
                "title": job.title,
                "skills": job.required_skills + job.preferred_skills,
                "content_text": content_text,
                "payload": {
                    "job_id": job_id,
                    "skills": job.required_skills + job.preferred_skills,
                    "title": job.title,
                    "is_deleted": False,
                }
            }

        for candidate_id, resume in DETERMINISTIC_CANDIDATE_UUIDS.items():
            content_parts = []
            if resume.title:
                content_parts.append(resume.title)
            if resume.summary:
                content_parts.append(resume.summary)
            if resume.skills:
                content_parts.extend(resume.skills)
            if resume.technical_skills:
                content_parts.extend(resume.technical_skills)
            if resume.job_titles:
                content_parts.extend(resume.job_titles)
            if resume.experiences:
                for exp in resume.experiences:
                    if exp.position:
                        content_parts.append(exp.position)
                    if exp.company:
                        content_parts.append(exp.company)
                    if exp.description:
                        content_parts.append(exp.description)
            if resume.projects:
                for proj in resume.projects:
                    if proj.name:
                        content_parts.append(proj.name)
                    if proj.description:
                        content_parts.append(proj.description)

            content_text = " ".join(content_parts)
            self.resume_documents[candidate_id] = {
                "id": candidate_id,
                "title": resume.title,
                "skills": resume.skills + resume.technical_skills,
                "content_text": content_text,
                "payload": {
                    "candidate_id": candidate_id,
                    "skills": resume.skills + resume.technical_skills,
                    "title": resume.title,
                    "is_deleted": False,
                }
            }

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = sum(a * a for a in vec_a) ** 0.5
        norm_b = sum(b * b for b in vec_b) ** 0.5

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    async def upsert_vector(self, collection_name: str, point_id: str | uuid.UUID, vector: list[float], payload: dict[str, Any]) -> None:
        pass

    async def delete_vector(self, collection_name: str, point_id: str | uuid.UUID) -> None:
        pass

    async def retrieve_vector(self, collection_name: str, point_id: str | uuid.UUID) -> dict[str, Any] | None:
        pass

    async def search_similar(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        filters: dict[str, Any] | None = None,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Return query-dependent similarity results using cosine similarity.

        Computes deterministic similarity between query_vector and document embeddings.
        """
        threshold = score_threshold or 0.0

        if collection_name == "jobs":
            documents = self.job_documents
        elif collection_name == "resumes":
            documents = self.resume_documents
        else:
            return []

        # Compute similarity for each document
        scored_results = []
        for doc_id, doc in documents.items():
            # Embed document content
            doc_vector = self.embedding_provider.embed_text(doc["content_text"])
            similarity = self._cosine_similarity(query_vector, doc_vector)
            if similarity >= threshold:
                scored_results.append({
                    "id": doc_id,
                    "score": similarity,
                    "payload": doc["payload"]
                })

        # Sort by score descending
        scored_results.sort(key=lambda x: x["score"], reverse=True)
        return scored_results[:limit]


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """Mock embedding provider using deterministic TF-IDF vectors for evaluation.

    Uses a lightweight TF-IDF vectorizer built from the mock corpus.
    No external dependencies, no model download, fully deterministic.
    """

    def __init__(self):
        self.dimension = 384
        self._vocab: dict[str, int] = {}
        self._idf: dict[int, float] = {}
        self._initialized = False

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenization: lowercase, split on non-alphanumeric."""
        import re
        return [t for t in re.split(r'[\s\-\.\,\+\/\#\(\)\:\;\'\"]+', text.lower()) if len(t) >= 2]

    def _build_vocab_and_idf(self, texts: list[str]) -> None:
        """Build vocabulary and IDF from corpus texts."""
        import math
        doc_count = len(texts)
        term_doc_count: dict[str, int] = {}

        # Count document frequency for each term
        for text in texts:
            tokens = set(self._tokenize(text))
            for token in tokens:
                term_doc_count[token] = term_doc_count.get(token, 0) + 1

        # Build vocabulary (sorted for determinism)
        sorted_terms = sorted(term_doc_count.keys())
        self._vocab = {term: idx for idx, term in enumerate(sorted_terms)}

        # Compute IDF
        self._idf = {
            idx: math.log(doc_count / (1 + count))
            for term, idx in self._vocab.items()
            for count in [term_doc_count[term]]
        }

    def _ensure_initialized(self) -> None:
        """Lazy initialization: build vocab from all mock documents."""
        if self._initialized:
            return

        # Collect all mock document texts
        texts = []
        for job in DETERMINISTIC_JOB_UUIDS.values():
            parts = []
            if job.title:
                parts.append(job.title)
            if job.summary:
                parts.append(job.summary)
            if job.required_skills:
                parts.extend(job.required_skills)
            if job.preferred_skills:
                parts.extend(job.preferred_skills)
            if job.responsibilities:
                parts.extend(job.responsibilities)
            texts.append(" ".join(parts))

        for resume in DETERMINISTIC_CANDIDATE_UUIDS.values():
            parts = []
            if resume.title:
                parts.append(resume.title)
            if resume.summary:
                parts.append(resume.summary)
            if resume.skills:
                parts.extend(resume.skills)
            if resume.technical_skills:
                parts.extend(resume.technical_skills)
            if resume.job_titles:
                parts.extend(resume.job_titles)
            if resume.experiences:
                for exp in resume.experiences:
                    if exp.position:
                        parts.append(exp.position)
                    if exp.company:
                        parts.append(exp.company)
                    if exp.description:
                        parts.append(exp.description)
            if resume.projects:
                for proj in resume.projects:
                    if proj.name:
                        parts.append(proj.name)
                    if proj.description:
                        parts.append(proj.description)
            texts.append(" ".join(parts))

        self._build_vocab_and_idf(texts)
        self._initialized = True

    def _text_to_tfidf(self, text: str) -> list[float]:
        """Convert text to TF-IDF vector."""
        self._ensure_initialized()

        vector = [0.0] * self.dimension
        tokens = self._tokenize(text)

        if not tokens:
            return vector

        # Term frequency
        tf: dict[int, int] = {}
        for token in tokens:
            idx = self._vocab.get(token)
            if idx is not None:
                tf[idx] = tf.get(idx, 0) + 1

        # Normalize TF and apply IDF
        total_terms = len(tokens)
        for idx, count in tf.items():
            tf_normalized = count / total_terms
            idf = self._idf.get(idx, 0.0)
            # Map vocabulary index to vector dimension (modulo for dimension reduction)
            dim_idx = idx % self.dimension
            vector[dim_idx] += tf_normalized * idf

        # L2 normalize
        norm = sum(v * v for v in vector) ** 0.5
        if norm > 0:
            vector = [v / norm for v in vector]

        return vector

    def embed_text(self, text: str) -> list[float]:
        if not text or not text.strip():
            raise ValueError("Text for embedding generation cannot be empty")
        return self._text_to_tfidf(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [self._text_to_tfidf(t) for t in texts]


class EvaluationRAGChatService(RAGChatService):
    """RAGChatService configured for evaluation with mock dependencies."""

    def __init__(self, actor_user: User | UserRole, use_real_reranker: bool = False):
        mock_embedding_provider = MockEmbeddingProvider()
        mock_vector_repo = MockVectorRepository(embedding_provider=mock_embedding_provider)
        mock_context_resolver = MockContextResolver(actor_user)

        if use_real_reranker:
            try:
                mock_reranker = CrossEncoderReranker()
            except Exception as exc:
                raise RuntimeError(f"Failed to initialize CrossEncoderReranker: {exc}") from exc
        else:
            mock_reranker = MockReranker()

        super().__init__(
            vector_repository=mock_vector_repo,
            reranker=mock_reranker,
            context_resolver=mock_context_resolver,
            embedding_service=EmbeddingService(mock_embedding_provider),
        )
        self.actor_user = actor_user
        self._last_telemetry: Optional[RAGTelemetry] = None

    async def chat_with_telemetry(
        self,
        message: str,
        actor_user: User | UserRole,
        history: list[ChatMessage] | None = None,
        context: Any | None = None,
    ) -> tuple[ChatResponse, RAGTelemetry]:
        """Chat and return both response and telemetry."""
        import logging
        original_logger = logging.getLogger("app.services.rag_chat_service")

        captured_telemetry = {}

        def capture_log(record):
            if record.name == "app.services.rag_chat_service" and hasattr(record, 'extra'):
                extra = record.extra
                if isinstance(extra, dict) and 'rewrite_latency_ms' in extra:
                    captured_telemetry['data'] = extra

        handler = logging.Handler()
        handler.handle = capture_log
        original_logger.addHandler(handler)
        original_logger.setLevel(logging.INFO)

        try:
            response = await self.chat(message, actor_user, history, context)

            telemetry = RAGTelemetry()
            if 'data' in captured_telemetry:
                data = captured_telemetry['data']
                telemetry.rewrite_latency_ms = data.get('rewrite_latency_ms', 0.0)
                telemetry.qdrant_latency_ms = data.get('qdrant_latency_ms', 0.0)
                telemetry.reranker_latency_ms = data.get('reranker_latency_ms', 0.0)
                telemetry.retrieved_qdrant_count = data.get('retrieved_qdrant_count', 0)
                telemetry.authorized_sql_count = data.get('authorized_sql_count', 0)
                telemetry.generation_latency_ms = data.get('generation_latency_ms', 0.0)
                telemetry.evaluator_latency_ms = data.get('evaluator_latency_ms', 0.0)
                telemetry.prompt_tokens = data.get('prompt_tokens')
                telemetry.completion_tokens = data.get('completion_tokens')
                telemetry.total_llm_calls = data.get('total_llm_calls', 0)
                telemetry.grounding_retry_count = data.get('grounding_retry_count', 0)
                telemetry.total_latency_ms = data.get('total_latency_ms', 0.0)
                telemetry.error = data.get('error')

            return response, telemetry
        finally:
            original_logger.removeHandler(handler)


class MockReranker(BaseReranker):
    """Mock reranker that returns deterministic reranking (identity function)."""

    async def rerank(self, query: str, candidates: list[RerankCandidate]) -> list[RerankResult]:
        """Return candidates sorted by original score (deterministic)."""
        results = [
            RerankResult(
                entity_id=c.entity_id,
                rerank_score=c.original_relevance_score,
            )
            for c in candidates
        ]
        results.sort(key=lambda r: r.rerank_score, reverse=True)
        return results


@dataclass
class EvaluationCase:
    """Single evaluation case from golden dataset."""
    id: str
    category: str
    subcategory: str
    query: str
    history: list[ChatMessage]
    expected_source_ids: list[str]
    expected_claims: list[str]
    expected_refusal: bool
    expected_faithfulness: bool = True
    rerank_expected: bool = False


@dataclass
class EvaluationResult:
    """Result of evaluating a single case."""
    case_id: str
    category: str
    success: bool
    response: Optional[ChatResponse]
    telemetry: Optional[RAGTelemetry]
    retrieval_metrics: dict[str, float]
    error: Optional[str] = None


@dataclass
class PhaseHComparisonResult:
    """Result of Phase H A/B comparison for a single case."""
    case_id: str
    baseline_metrics: dict[str, float]
    reranked_metrics: dict[str, float]
    baseline_ids: list[str]
    reranked_ids: list[str]
    cross_encoder_executed: bool
    cross_encoder_error: Optional[str] = None
    ordering_changed: bool = False


@dataclass
class EvaluationMetrics:
    """Aggregated evaluation metrics."""
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    blocked_cases: int = 0

    recall_at_5: float = 0.0
    precision_at_5: float = 0.0
    hit_rate_at_5: float = 0.0
    mrr: float = 0.0
    ndcg_at_5: float = 0.0

    refusal_accuracy: float = 0.0
    faithfulness_accuracy: float = 0.0
    citation_validity: float = 0.0

    by_category: dict[str, dict] = field(default_factory=dict)

    retrieval_only_cases: int = 0
    generation_cases: int = 0
    rate_limited_cases: int = 0

    # Phase H comparison results
    phase_h_comparisons: list[PhaseHComparisonResult] = field(default_factory=list)


def load_golden_dataset() -> list[EvaluationCase]:
    """Load and parse the golden dataset."""
    with open(GOLDEN_DATASET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = []
    for case_data in data["cases"]:
        history = [ChatMessage(**msg) for msg in case_data.get("history", [])]
        cases.append(EvaluationCase(
            id=case_data["id"],
            category=case_data["category"],
            subcategory=case_data.get("subcategory", ""),
            query=case_data["query"],
            history=history,
            expected_source_ids=case_data.get("expected_source_ids", []),
            expected_claims=case_data.get("expected_claims", []),
            expected_refusal=case_data.get("expected_refusal", False),
            expected_faithfulness=case_data.get("expected_faithfulness", True),
            rerank_expected=case_data.get("rerank_expected", False),
        ))
    return cases


def calculate_retrieval_metrics(
    expected_ids: list[str],
    actual_ids: list[str],
    k: int = 5
) -> dict[str, float]:
    """Calculate retrieval metrics for a single case."""
    expected_set = set(expected_ids)
    actual_top_k = actual_ids[:k]
    actual_set = set(actual_top_k)

    if not expected_set:
        return {
            "recall": 1.0 if not actual_set else 0.0,
            "precision": 1.0 if not actual_set else 0.0,
            "hit_rate": 1.0 if not actual_set else 0.0,
            "mrr": 1.0 if not actual_set else 0.0,
            "ndcg": 1.0 if not actual_set else 0.0,
        }

    # Recall@k
    recall = len(expected_set & actual_set) / len(expected_set)

    # Precision@k
    precision = len(expected_set & actual_set) / len(actual_set) if actual_set else 0.0

    # Hit Rate@k
    hit_rate = 1.0 if (expected_set & actual_set) else 0.0

    # MRR
    mrr = 0.0
    for i, actual_id in enumerate(actual_top_k):
        if actual_id in expected_set:
            mrr = 1.0 / (i + 1)
            break

    # NDCG@k
    dcg = 0.0
    for i, actual_id in enumerate(actual_top_k):
        if actual_id in expected_set:
            dcg += 1.0 / (i + 1)

    ideal_dcg = sum(1.0 / (i + 1) for i in range(min(len(expected_set), k)))
    ndcg = dcg / ideal_dcg if ideal_dcg > 0 else 0.0

    return {
        "recall": recall,
        "precision": precision,
        "hit_rate": hit_rate,
        "mrr": mrr,
        "ndcg": ndcg,
    }


def evaluate_refusal(response: Optional[ChatResponse], telemetry: Optional[RAGTelemetry], expected_refusal: bool) -> tuple[bool, str]:
    """Evaluate refusal correctness using structured telemetry error state.

    Distinguishes between:
    1. no authorized context (authorization filtering)
    2. insufficient retrieval evidence (retrieval failure)
    3. grounding failure (generation/faithfulness failure)
    4. successful answer
    """
    if telemetry:
        if telemetry.error == "no_authorized_context":
            return expected_refusal == True, "no_authorized_context"
        if telemetry.error == "grounding_failed_after_retry":
            return expected_refusal == True, "grounding_failure"

    if response:
        if not response.sources and response.confidence == 0.0:
            if response.answer == "Không đủ dữ liệu để trả lời.":
                return expected_refusal == True, "insufficient_retrieval_evidence"
            if response.answer == "Không đủ bằng chứng để trả lời câu hỏi này.":
                return expected_refusal == True, "grounding_failure"
            return expected_refusal == True, "insufficient_evidence"

        if response.sources and response.confidence > 0.0:
            return expected_refusal == False, "successful_answer"

    return False, "unknown"


def classify_refusal_type(response: Optional[ChatResponse], telemetry: Optional[RAGTelemetry]) -> str:
    """Classify the refusal type for detailed metrics."""
    if telemetry:
        if telemetry.error == "no_authorized_context":
            return "authorization_filtering"
        if telemetry.error == "grounding_failed_after_retry":
            return "grounding_failure"

    if response:
        if not response.sources and response.confidence == 0.0:
            if response.answer == "Không đủ dữ liệu để trả lời.":
                return "retrieval_failure"
            if response.answer == "Không đủ bằng chứng để trả lời câu hỏi này.":
                return "grounding_failure"
            return "insufficient_evidence"

        if response.sources and response.confidence > 0.0:
            return "successful_answer"

    return "unknown"


async def run_phase_h_comparison(case: EvaluationCase, actor_user: User | UserRole) -> PhaseHComparisonResult:
    """Run Phase H A/B comparison for a single case.

    STEP 1: Retrieve broad candidates using MockVectorRepository.
    STEP 2: Apply the same score_threshold used by production.
    STEP 3: Run authorization through the evaluation MockContextResolver.
    STEP 4: Construct the authorized RAGContext.
    STEP 5 — BASELINE: Do NOT invoke CrossEncoder. Take authorized candidates in original Qdrant ranking order.
    STEP 6 — RERANKED: Invoke the REAL CrossEncoderReranker using authorized SQL-hydrated mock content.
    STEP 7: Return both metrics independently.
    """
    from app.ai.interfaces.base_provider import RerankCandidate, RerankResult
    from app.services.rag_chat_service import DEFAULT_SCORE_THRESHOLD, RETRIEVAL_LIMIT, FINAL_CONTEXT_LIMIT

    # Initialize services with shared embedding provider for consistent query-dependent scoring
    mock_embedding_provider = MockEmbeddingProvider()
    vector_repo = MockVectorRepository(embedding_provider=mock_embedding_provider)
    context_resolver = MockContextResolver(actor_user)

    # STEP 1: Broad retrieval from Qdrant (always available)
    # Generate query embedding from case query
    query_vector = mock_embedding_provider.embed_text(case.query)

    # Retrieve jobs
    retrieved_jobs_raw = await vector_repo.search_similar(
        collection_name="jobs",
        query_vector=query_vector,
        limit=RETRIEVAL_LIMIT,
        score_threshold=DEFAULT_SCORE_THRESHOLD,
    )

    # STEP 2: Apply score threshold (already done by search_similar)

    # STEP 3: Authorization through MockContextResolver
    job_ids = [uuid.UUID(r["payload"]["job_id"]) for r in retrieved_jobs_raw if r.get("payload", {}).get("job_id")]
    jobs_dict = await context_resolver.resolve_jobs(job_ids, actor_user)

    # STEP 4: Build authorized candidates with Qdrant ranking preserved
    # Sort by original Qdrant score descending to preserve Qdrant ranking
    authorized_candidates = []
    for r in retrieved_jobs_raw:
        job_id_str = r["payload"].get("job_id")
        if job_id_str and uuid.UUID(job_id_str) in jobs_dict:
            job = jobs_dict[uuid.UUID(job_id_str)]
            # Build text for reranking
            text_parts = []
            if job.title:
                text_parts.append(f"Title: {job.title}")
            if job.summary:
                text_parts.append(f"Summary: {job.summary}")
            if job.required_skills:
                text_parts.append(f"Required Skills: {', '.join(job.required_skills)}")
            if job.preferred_skills:
                text_parts.append(f"Preferred Skills: {', '.join(job.preferred_skills)}")
            if job.responsibilities:
                text_parts.append(f"Responsibilities: {', '.join(job.responsibilities)}")
            if job.seniority:
                text_parts.append(f"Seniority: {job.seniority}")

            authorized_candidates.append(
                type("RerankCandidate", (), {
                    "entity_id": uuid.UUID(job_id_str),
                    "source_type": "job",
                    "title": job.title or f"Job {job_id_str[:8]}",
                    "text_for_reranking": " | ".join(text_parts) if text_parts else f"Job {job_id_str}",
                    "original_relevance_score": r["score"],
                })()
            )

    # STEP 5 — BASELINE: No CrossEncoder, use Qdrant ranking order
    baseline_top_k = authorized_candidates[:FINAL_CONTEXT_LIMIT]
    baseline_ids = [str(c.entity_id) for c in baseline_top_k]
    baseline_metrics = calculate_retrieval_metrics(case.expected_source_ids, baseline_ids)

    # STEP 6 — RERANKED: Use REAL CrossEncoderReranker (or BLOCKED if skipped/failed)
    cross_encoder_executed = False
    cross_encoder_error = None
    reranked_metrics = None  # None means BLOCKED/SKIPPED, not 0.0
    reranked_ids = None

    global SKIP_CROSS_ENCODER
    if SKIP_CROSS_ENCODER:
        cross_encoder_error = "CrossEncoder evaluation skipped via --skip-cross-encoder flag"
        logger.info(f"CrossEncoder SKIPPED for case {case.id}: {cross_encoder_error}")
    else:
        try:
            reranker = CrossEncoderReranker()
            rerank_results = await reranker.rerank(case.query, authorized_candidates)
            reranked_top_k = rerank_results[:FINAL_CONTEXT_LIMIT]
            reranked_ids = [str(r.entity_id) for r in reranked_top_k]
            reranked_metrics = calculate_retrieval_metrics(case.expected_source_ids, reranked_ids)
            cross_encoder_executed = True
            cross_encoder_error = None
        except Exception as exc:
            cross_encoder_executed = False
            cross_encoder_error = f"CrossEncoder failed: {exc}"
            logger.warning(f"CrossEncoder failed for case {case.id}: {exc}")
            # Do NOT fabricate metrics - leave as None to indicate BLOCKED

    # STEP 7: Check if ordering changed (only if CrossEncoder actually executed)
    ordering_changed = False
    if cross_encoder_executed and reranked_ids is not None:
        ordering_changed = baseline_ids != reranked_ids

    return PhaseHComparisonResult(
        case_id=case.id,
        baseline_metrics=baseline_metrics,
        reranked_metrics=reranked_metrics,
        baseline_ids=baseline_ids,
        reranked_ids=reranked_ids,
        cross_encoder_executed=cross_encoder_executed,
        cross_encoder_error=cross_encoder_error,
        ordering_changed=ordering_changed,
    )


async def run_evaluation() -> EvaluationMetrics:
    """Run the full evaluation suite."""
    logger.info("Loading golden dataset...")
    cases = load_golden_dataset()
    logger.info(f"Loaded {len(cases)} evaluation cases")

    metrics = EvaluationMetrics()
    metrics.total_cases = len(cases)

    refusal_type_counts: dict[str, int] = {}

    for case in cases:
        logger.info(f"Evaluating {case.id} ({case.category})...")

        try:
            actor_role = UserRole.RECRUITER if "candidate" in case.query.lower() or "ứng viên" in case.query.lower() else UserRole.CANDIDATE
            actor_user = MagicMock(spec=User)
            actor_user.role = actor_role
            actor_user.id = uuid.uuid4()

            # Run standard evaluation with mock reranker
            service = EvaluationRAGChatService(actor_user, use_real_reranker=False)

            response, telemetry = await service.chat_with_telemetry(
                message=case.query,
                actor_user=actor_user,
                history=case.history,
            )

            actual_source_ids = [str(s.entity_id) for s in response.sources]
            retrieval_metrics = calculate_retrieval_metrics(case.expected_source_ids, actual_source_ids)

            refusal_correct, refusal_reason = evaluate_refusal(response, telemetry, case.expected_refusal)
            refusal_type = classify_refusal_type(response, telemetry)
            refusal_type_counts[refusal_type] = refusal_type_counts.get(refusal_type, 0) + 1

            if case.category in ("retrieval", "reranking_sensitive"):
                metrics.retrieval_only_cases += 1
            else:
                metrics.generation_cases += 1

            case_passed = True
            if case.expected_source_ids:
                if retrieval_metrics["recall"] < 0.5:
                    case_passed = False

            if not refusal_correct:
                case_passed = False

            if case_passed:
                metrics.passed_cases += 1
            else:
                metrics.failed_cases += 1

            if case.category not in metrics.by_category:
                metrics.by_category[case.category] = {"passed": 0, "total": 0}
            metrics.by_category[case.category]["total"] += 1
            if case_passed:
                metrics.by_category[case.category]["passed"] += 1

            # Run Phase H A/B comparison for reranking_sensitive cases
            if case.category == "reranking_sensitive" or case.rerank_expected:
                logger.info(f"Running Phase H A/B comparison for {case.id}...")
                comparison = await run_phase_h_comparison(case, actor_user)
                metrics.phase_h_comparisons.append(comparison)

                if not comparison.cross_encoder_executed:
                    metrics.blocked_cases += 1
                    logger.error(f"Phase H comparison BLOCKED for {case.id}: {comparison.cross_encoder_error}")

        except Exception as e:
            logger.error(f"Case {case.id} blocked/error: {e}")
            metrics.blocked_cases += 1
            if "rate limit" in str(e).lower() or "quota" in str(e).lower():
                metrics.rate_limited_cases += 1

    logger.info(f"Refusal type distribution: {refusal_type_counts}")

    return metrics


class MagicMock:
    """Simple mock for User object."""
    def __init__(self, spec=None):
        self._spec = spec
        self.role = None
        self.id = None


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="RAG Evaluation Script")
    parser.add_argument(
        "--skip-cross-encoder",
        action="store_true",
        help="Skip CrossEncoder evaluation (useful on Windows where model loading may crash). Default: attempt real CrossEncoder execution."
    )
    args = parser.parse_args()

    global SKIP_CROSS_ENCODER
    SKIP_CROSS_ENCODER = args.skip_cross_encoder

    if SKIP_CROSS_ENCODER:
        print("=" * 60)
        print("RAG EVALUATION - Phase I Correction (CrossEncoder SKIPPED)")
        print("=" * 60)
        print("--skip-cross-encoder flag detected: CrossEncoder evaluation will be skipped.")
        print("Reranked metrics will be marked as BLOCKED/SKIPPED.")
        print("=" * 60)
    else:
        print("=" * 60)
        print("RAG EVALUATION - Phase I Correction")
        print("=" * 60)
        print("Attempting real CrossEncoder evaluation...")
        print("Use --skip-cross-encoder to skip if model loading crashes.")
        print("=" * 60)

    metrics = asyncio.run(run_evaluation())

    print("\n" + "=" * 60)
    print("EVALUATION RESULTS")
    print("=" * 60)
    print(f"Total cases: {metrics.total_cases}")
    print(f"Passed: {metrics.passed_cases}")
    print(f"Failed: {metrics.failed_cases}")
    print(f"Blocked/Error: {metrics.blocked_cases}")
    print(f"Rate limited: {metrics.rate_limited_cases}")
    print(f"Retrieval-only cases: {metrics.retrieval_only_cases}")
    print(f"Generation cases: {metrics.generation_cases}")

    print("\nBy Category:")
    for cat, stats in metrics.by_category.items():
        print(f"  {cat}: {stats['passed']}/{stats['total']} passed")

    # Phase H Comparison Results
    if metrics.phase_h_comparisons:
        print("\n" + "=" * 60)
        print("PHASE H A/B COMPARISON RESULTS")
        print("=" * 60)
        for comp in metrics.phase_h_comparisons:
            print(f"\nCase: {comp.case_id}")
            print(f"  CrossEncoder Executed: {comp.cross_encoder_executed}")
            if comp.cross_encoder_error:
                print(f"  CrossEncoder Status: {comp.cross_encoder_error}")
            print(f"  Ordering Changed: {comp.ordering_changed}")
            print(f"  Baseline IDs: {comp.baseline_ids}")
            print(f"  Reranked IDs: {comp.reranked_ids}")
            print(f"  Baseline Metrics: {comp.baseline_metrics}")
            print(f"  Reranked Metrics: {comp.reranked_metrics}")

            # Calculate improvement
            baseline_recall = comp.baseline_metrics.get("recall", 0.0)
            reranked_recall = comp.reranked_metrics.get("recall", 0.0) if comp.reranked_metrics else None
            if reranked_recall is not None:
                improvement = reranked_recall - baseline_recall
                print(f"  Recall Improvement: {improvement:+.3f}")
            else:
                print(f"  Recall Improvement: N/A (reranked metrics BLOCKED)")

    print("\nNote: This is a structural evaluation script.")
    print("Full metric computation requires Gemini API access.")
    print("=" * 60)

    return metrics


if __name__ == "__main__":
    main()
