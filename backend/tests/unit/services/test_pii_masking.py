from __future__ import annotations

from app.services.pii_masking import (
    REDACTED,
    mask_email,
    mask_parsed_resume,
    mask_phone,
    mask_pii,
)


def test_mask_email_and_phone_fully_redact_values() -> None:
    assert mask_email("jane.doe@example.com") is None
    assert mask_phone("+84 912 345 678") is None
    assert mask_email(None) is None
    assert mask_phone(None) is None


def test_mask_pii_redacts_contact_and_social_fields_recursively() -> None:
    masked = mask_pii(
        {
            "full_name": "Jane Doe",
            "email": "jane.doe@example.com",
            "phone": "+84 912 345 678",
            "address": "12 Main Street",
            "personal_website": "https://jane.dev",
            "links": {
                "linkedin": "https://linkedin.com/in/jane",
                "github": "https://github.com/jane",
            },
            "summary": (
                "Backend engineer reachable at jane.doe@example.com or "
                "+84 912 345 678 or https://linkedin.com/in/jane"
            ),
            "portfolio": "Internal payments platform",
            "skills": ["Python", "FastAPI", "Node.js"],
            "experiences": [
                {
                    "company": "Acme",
                    "description": "Built APIs; contact jane@acme.test",
                    "email": "jane@acme.test",
                }
            ],
        }
    )

    assert masked["full_name"] == "Jane Doe"
    assert masked["email"] is None
    assert masked["phone"] is None
    assert masked["address"] == REDACTED
    assert masked["personal_website"] == REDACTED
    assert masked["links"]["linkedin"] == REDACTED
    assert masked["links"]["github"] == REDACTED
    assert "jane.doe" not in masked["summary"]
    assert "example.com" not in masked["summary"]
    assert "5678" not in masked["summary"]
    assert "linkedin.com" not in masked["summary"]
    assert masked["portfolio"] == "Internal payments platform"
    assert masked["skills"] == ["Python", "FastAPI", "Node.js"]
    assert masked["experiences"][0]["company"] == "Acme"
    assert masked["experiences"][0]["email"] is None
    assert "acme.test" not in masked["experiences"][0]["description"]


def test_mask_parsed_resume_drops_contact_fields_and_preserves_cv() -> None:
    parsed = mask_parsed_resume(
        {
            "full_name": "Jane Doe",
            "title": "Senior Backend Engineer",
            "email": "jane.doe@example.com",
            "phone": "+84 912 345 678",
            "address": "12 Main Street",
            "linkedin": "https://linkedin.com/in/jane",
            "website": "https://jane.dev",
            "summary": "Distributed systems engineer. Email: jane.doe@example.com",
            "skills": ["Python", "FastAPI"],
            "experiences": [
                {
                    "company": "Acme",
                    "position": "Engineer",
                    "start_date": "01/2021",
                    "end_date": "Present",
                    "is_current": True,
                    "description": "Built APIs",
                }
            ],
            "education": [
                {
                    "institution": "Tech University",
                    "degree": "Bachelor of Science",
                    "field_of_study": "Computer Science",
                    "start_year": 2016,
                    "end_year": 2020,
                }
            ],
            "projects": [
                {
                    "name": "Core Billing",
                    "description": "High-throughput billing engine",
                    "skills_used": ["Python", "PostgreSQL"],
                }
            ],
        }
    )

    assert parsed is not None
    assert parsed.full_name == "Jane Doe"
    assert parsed.title == "Senior Backend Engineer"
    assert parsed.email is None
    assert parsed.phone is None
    assert parsed.skills == ["Python", "FastAPI"]
    assert parsed.experiences[0].company == "Acme"
    assert parsed.experiences[0].position == "Engineer"
    assert parsed.education[0].institution == "Tech University"
    assert parsed.projects[0].name == "Core Billing"
    assert not hasattr(parsed, "address")
    assert not hasattr(parsed, "linkedin")
    assert not hasattr(parsed, "website")

    serialized = parsed.model_dump_json()
    assert "jane.doe" not in serialized
    assert "example.com" not in serialized
    assert "5678" not in serialized
    assert "12 Main Street" not in serialized
    assert "linkedin.com" not in serialized
    assert "jane.dev" not in serialized
