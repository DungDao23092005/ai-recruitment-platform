# AI Recruitment Platform

## Live Demo
**Application:** http://tuyendungai.me/

## Overview
The AI Recruitment Platform is a modern, intelligence-driven recruitment ecosystem designed to streamline the hiring process. It connects Candidates, Recruiters, and Administrators using a suite of AI-powered tools. The platform goes beyond traditional keyword search by employing advanced AI models for Semantic Search, Resume Parsing, Job Matching (Recommendation), Explainable AI, and an intelligent RAG-based Chatbot.

## Problem Statement
Traditional recruitment platforms suffer from rigid keyword-based filtering, leading to mismatched expectations and prolonged hiring cycles. Candidates struggle to find jobs that truly fit their skills and experience, while recruiters spend countless hours manually parsing resumes and screening candidates. 

## Objectives
- Provide **Candidates** with a seamless way to parse resumes, find highly relevant jobs via Semantic Search, and interact with an AI Chatbot for career assistance.
- Empower **Recruiters** with AI-driven candidate matching, automated resume screening, and automatic interview question generation.
- Ensure **Administrators** can moderate the system, manage users, and maintain data integrity.

## Key Features

### Candidate
- **Profile & Resume Management:** Upload and automatically parse CV/Resumes into structured profiles (Skills, Experience, Education, Projects).
- **Job Discovery:** Search for jobs using Natural Language (Semantic Search) instead of strict keywords.
- **Application Tracking:** Apply for jobs and track the application status through the application management interface.
- **AI Chatbot (RAG):** Ask recruitment-related questions, get job recommendations based on personal profiles, and clarify job descriptions via an intelligent conversational interface.

### Recruiter
- **Recruiter Dashboard:** Manage companies, post jobs, and monitor application metrics.
- **AI Candidate Matching:** Automatically score and rank candidates based on Cosine Similarity and Rule-based Engines (Skills, Experience, Projects).
- **Explainable AI:** View LLM-generated explanations detailing candidate fit and identifying skill gaps based on the matching evidence.
- **Interview Generation:** Automatically generate structured interview questions tailored to specific job requirements.

### Admin
- **User & Company Moderation:** Manage user roles, approve companies, and oversee system operations.
- **System Monitoring:** Monitor overall platform activity and data.

## AI Features

### Resume Parsing & Job Parsing
Uses LLMs (Gemini) to extract unstructured data from PDF/Docx resumes and free-text job descriptions, transforming them into a unified structured format (Skills, Experience, Projects).

### Embedding & Vector Search
Utilizes `sentence-transformers` to create dense vector representations of Resumes and Job Descriptions. Stores these vectors in **Qdrant** for semantic retrieval and Cosine Similarity search.

### AI Matching & Recommendation
A hybrid matching engine evaluates Candidate and Job compatibility using:
- **Semantic Score:** Vector distance between Candidate Profile and Job Description.
- **Rule-based Engine (40/30/15/10/5):** Weights dynamically applied to Semantic Score (40%), Skill Coverage (30%), Experience Match (15%), Education Match (10%), and Project Evidence (5%). Project Evidence validates that a candidate has actually applied a skill in a real-world scenario.

### Explainable AI
The matching engine calls the Gemini LLM to generate a natural language explanation (`match_reasons`, `skill_gap`) summarizing why the candidate fits the role, providing transparency to Recruiters.

### Context Resolution (ContextResolver)
Acts as a security and data hydration layer between the Vector Database (Qdrant) and the Application. It ensures users only retrieve semantic results (Jobs/Applications) they are authorized to view (e.g., Candidates only see PUBLISHED jobs; Recruiters only see Applications for their own company).

### RAG Chatbot
An intelligent conversational agent featuring an LLM-based **Intent Classifier** that routes queries into 4 paths:
- `RECOMMENDATION`: Recommends jobs tailored to the Candidate's CV by triggering the AI Matching Service.
- `KNOWLEDGE`: Answers questions about platform policies using a predefined Knowledge Base.
- `SEMANTIC`: Searches for jobs/candidates using Qdrant vector search based on natural language queries.
- `EXHAUSTIVE`: Performs exact-match database queries for specific constraints (e.g., "Find jobs in Hanoi").

## System Architecture

The platform follows a Client-Server architecture with a layered AI service architecture. 
- **Frontend:** React SPA built with Vite, styled with Tailwind CSS.
- **Backend:** FastAPI application utilizing Dependency Injection and layered architecture (Routers → Services → Repositories → ORM).
- **Database:** Microsoft SQL Server for transactional data (ACID compliance) and Qdrant for vector storage.

## Technology Stack

| Layer | Technology | Version | Purpose |
| --- | --- | --- | --- |
| **Frontend** | React | 18.3.1 | SPA UI |
| **Routing** | React Router | 6.28.0 | Client-side routing |
| **Build Tool** | Vite | 5.4.11 | Frontend build tool |
| **Styling** | Tailwind CSS | 3.4.17 | Utility-first CSS framework |
| **Icons** | Lucide React | 0.474.0 | UI Icons |
| **Backend** | FastAPI | 0.115.0 | Async API framework |
| **Server** | Uvicorn | 0.30.0 | ASGI web server |
| **Language** | Python / TypeScript | 3.11 (CI), 3.12 (Docker) / 5.6.3 | Core programming languages |
| **Database** | Microsoft SQL Server | 2022 | Transactional application data |
| **ORM** | SQLAlchemy | 2.0.30 | Database object-relational mapping |
| **Migrations** | Alembic | 1.13.0 | Database schema migrations |
| **Vector DB** | Qdrant | 1.8.0 (Client) | Semantic search and embedding storage |
| **AI / LLM** | Google Gemini (genai) | 0.1.1 | Generation, Parsing, and Explainable AI |
| **Embeddings** | sentence-transformers | 2.6.0 | Text-to-vector embedding generation |
| **Container** | Docker, Docker Compose | Latest | Local development and deployment |

## Project Structure

```text
.
├── backend/
│   ├── alembic/              # Database migrations
│   ├── app/
│   │   ├── api/v1/endpoints/ # API Route controllers
│   │   ├── core/             # Configuration & Security
│   │   ├── models/           # SQLAlchemy ORM Models
│   │   ├── schemas/          # Pydantic validation schemas
│   │   ├── services/         # Business logic and AI pipelines
│   │   └── main.py           # FastAPI application entry point
│   ├── tests/                # Pytest suites
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/       # Reusable UI components
│   │   ├── features/         # Feature-based modules (Auth, Jobs, Chat)
│   │   ├── hooks/            # Custom React hooks
│   │   └── App.tsx           # Main React component
│   └── package.json
├── docs/
│   ├── diagrams/             # Technical diagrams (PlantUML, PNG, SVG)
│   └── AI_Recruitment_Platform_Final_Report.docx
└── docker-compose.yml        # Multi-container orchestration
```

## Database Architecture

The transactional database uses Microsoft SQL Server. Key entities include:
| Entity | Purpose | Key Relationships |
| --- | --- | --- |
| `User` | Core authentication and authorization | Base table for all roles |
| `Candidate` / `Recruiter` / `Company` | Role-specific profile data | 1:1 with User, 1:N with Applications/Jobs |
| `Job` | Job descriptions, requirements, and metadata | 1:N with Applications, N:M with Skills |
| `Resume` | Parsed structured profile data | 1:1 with Candidate, N:M with Skills |
| `Application` | Tracks candidate job applications and status | N:1 with Job and Candidate |
| `Interview` | Generated interview questions and schedules | 1:1 with Application |

## API Overview

The API is documented via Swagger UI (available at `/docs` when running locally).
| Method | Endpoint | Description | Auth |
| --- | --- | --- | --- |
| `POST` | `/api/v1/auth/login` | Authenticate user and return JWT | None |
| `POST` | `/api/v1/auth/register` | Register a new user | None |
| `GET`  | `/api/v1/jobs` | Search jobs (Keyword filtering, Pagination) | Public |
| `POST` | `/api/v1/applications` | Apply for a job | Candidate |
| `GET`  | `/api/v1/ai/search/jobs` | Semantic search for jobs using Qdrant | Public/Auth |
| `POST` | `/api/v1/ai/chat` | Interact with the AI RAG Chatbot (Semantic/Exhaustive/Recommendation) | Candidate |
| `POST` | `/api/v1/ai/match` | Score and explain Candidate-Job fit | Recruiter |

## Authentication & Authorization
- **JWT (JSON Web Tokens):** Used for stateless authentication.
- **Password Hashing:** Uses `bcrypt` for secure password storage.
- **Role-Based Access Control (RBAC):** API endpoints are protected using dependency injection (e.g., `current_user` decorators) ensuring Candidates cannot access Recruiter endpoints and vice-versa.
- **IDOR Protection:** The `ContextResolver` and service layer ensure users can only modify or access entities they own (e.g., Recruiters can only view applications for their own companies).

## Development Setup

### Prerequisites
- Docker and Docker Compose
- Node.js 20+ (for local frontend dev)
- Python 3.11+ (for local backend dev)

### Clone Repository
```bash
git clone https://github.com/DungDao23092005/ai-recruitment-platform.git
cd ai-recruitment-platform
```

### Environment Configuration
Create a `.env` file in the root directory:
```bash
cp .env.example .env
```
Ensure you populate required variables such as `GEMINI_API_KEY` and `DATABASE_PASSWORD`.

| Variable | Required | Purpose |
| --- | --- | --- |
| `DATABASE_HOST` | Yes | MSSQL server hostname |
| `DATABASE_PASSWORD` | Yes | MSSQL server password |
| `GEMINI_API_KEY` | Yes | Gemini LLM access |
| `QDRANT_HOST` | Yes | Qdrant vector database hostname |
| `SECRET_KEY` | Yes | Secret used to sign JWTs |

### Running with Docker (Recommended)
Docker Compose provides the local environment for the backend, frontend, SQL Server, Qdrant, as well as included infrastructure services like Redis and Mailpit:
```bash
docker compose up --build
```
- Frontend: `http://localhost:3000`
- Backend API Docs: `http://localhost:8000/docs`
- Mailpit: `http://localhost:8025`

## Testing
The backend test suite uses `pytest` and `pytest-asyncio` for unit and integration testing.
To run tests locally (ensure the database and Qdrant are running):
```bash
cd backend
pip install -r requirements.txt
pytest
```
*Note: AI evaluation is implemented and testable, but a formal golden dataset-based accuracy benchmark is not currently provided due to the dynamic nature of LLM generation.*

## Deployment
**Live Application:** http://tuyendungai.me/

## Diagram Library
Technical diagrams illustrating Use Cases, ERD, AI Matching Pipelines, RAG Architectures, and UI placeholders are fully documented in the `docs/diagrams/` folder. All technical diagrams provide PlantUML source code alongside SVG and PNG exports.

## Project Documentation
- **Final Report:** `docs/AI_Recruitment_Platform_Final_Report.docx`
- **Diagrams:** `docs/diagrams/`

## Known Limitations
- **Golden Dataset:** No standardized dataset exists yet to rigorously benchmark AI accuracy.
- **LLM Latency:** Responses from the Gemini API can introduce slight latency during CV parsing and Match Explanation generation.
- **UI Placeholders:** Some specific UI screens are currently documented as placeholders within the diagram library.

## Troubleshooting
- **Database Connection Issues:** If the backend fails to connect to MSSQL on startup, ensure the Docker healthcheck for `mssql` passes before the backend boots up. You may need to restart the backend container.
- **Qdrant Vector DB:** If semantic search fails, verify that `QDRANT_HOST` is correctly mapped and the service is healthy.

## Security Notes
- **Never commit `.env` files or API keys.**
- The JWT Secret Key must be rotated in production.
- Production deployments should place the SQL Server and Qdrant instances behind a secure private subnet.
