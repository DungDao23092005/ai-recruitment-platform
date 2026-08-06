# PROJECT_RULES.md

# AI Recruitment Platform - Project Rules

Version: 1.0

---

# 1. Project Goal

Build a production-quality AI Recruitment Platform as a graduation project.

The project must demonstrate knowledge of:

* Software Engineering
* Clean Architecture
* Backend Development
* Database Design
* Artificial Intelligence
* NLP
* Recommendation Systems
* Docker & DevOps

The project should be understandable, maintainable and extensible.

---

# 2. Tech Stack (Fixed)

## Backend

* Python 3.12
* FastAPI
* SQLAlchemy 2.x
* Alembic
* Pydantic v2

## Database

* Microsoft SQL Server

## Cache

* Redis

## Background Jobs

* Celery

## AI

* spaCy
* Sentence Transformers
* Qdrant
* Gemini API

## Frontend

* React
* TypeScript
* Vite
* TailwindCSS
* Shadcn/UI

## DevOps

* Docker
* Docker Compose
* GitHub Actions
* Nginx

Do NOT replace technologies without explicit approval.

---

# 3. Architecture

Always follow:

Presentation Layer

↓

Application Layer

↓

Domain Layer

↓

Infrastructure Layer

FastAPI structure:

Router

↓

Service

↓

Repository

↓

Database

Rules

* Router contains HTTP logic only.
* Service contains business logic.
* Repository contains data access only.
* Models belong to Domain.
* Schemas belong to Presentation.
* Never mix responsibilities.

---

# 4. Folder Convention

Project Structure

backend/

frontend/

docs/

docker/

scripts/

.github/

Do not create random folders.

---

# 5. Coding Convention

* Use Python type hints.
* Keep functions small.
* One responsibility per class.
* Prefer composition over inheritance.
* Avoid duplicated code.
* Prefer explicit code over magic.

---

# 6. Naming Convention

Classes

PascalCase

Example

UserService

Repositories

UserRepository

Services

RecommendationService

Variables

snake_case

Constants

UPPER_CASE

Database Tables

Plural nouns

Examples

users

companies

jobs

applications

---

# 7. Git Convention

Use Conventional Commits.

Allowed prefixes

feat

fix

docs

refactor

test

perf

build

ci

style

chore

Examples

feat(auth): implement JWT authentication

fix(job): resolve pagination issue

docs(api): update authentication documentation

Never use

update

done

fix bug

123

---

# 8. Branch Strategy

main

Production-ready code

develop

Integration branch

feature/<name>

New features

fix/<name>

Bug fixes

---

# 9. Documentation Rules

Every new module must update documentation if necessary.

Architecture changes

↓

Update architecture.md

Database changes

↓

Update database.md

API changes

↓

Update api.md

---

# 10. Testing Rules

Every completed feature should include:

* Unit Test
* Integration Test (when appropriate)

No feature is considered complete without validation.

---

# 11. Security Rules

Never

* Store plain passwords
* Hardcode secrets
* Disable authentication
* Ignore authorization
* Trust client input

Always

* Validate input
* Use JWT
* Hash passwords
* Use environment variables

---

# 12. Performance Rules

Avoid

* N+1 queries
* Duplicate queries
* Unnecessary loops
* Loading unused data

Always consider scalability.

---

# 13. AI Rules

AI features must be explainable.

Recommendation must provide reasons.

Matching Score must not be a black box.

Use embeddings for semantic similarity.

---

# 14. Commit Rule

One logical task

↓

One commit

Never combine multiple unrelated features.

---

# 15. Definition of Done

A task is complete only if:

* Requirement implemented
* Code reviewed
* Error handling added
* Logging added (where appropriate)
* Tests pass
* Documentation updated
* Commit message follows convention

Only then may the task move to the next Sprint.
