"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("hashed_password", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_admin", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── user_profiles ─────────────────────────────────────────────────────────
    op.create_table(
        "user_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("phone", sa.Text),
        sa.Column("location", sa.String(255)),
        sa.Column("linkedin_url", sa.Text),
        sa.Column("github_url", sa.Text),
        sa.Column("portfolio_url", sa.Text),
        sa.Column("work_authorization", sa.String(50), nullable=False, server_default="unknown"),
        sa.Column("requires_sponsorship", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("desired_salary_min", sa.Integer),
        sa.Column("desired_salary_max", sa.Integer),
        sa.Column("salary_currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("earliest_start_date", sa.Date),
        sa.Column("willing_to_relocate", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("target_locations", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("education", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("work_history", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("skills", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("certifications", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("custom_qa_defaults", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── ingestion_sources ─────────────────────────────────────────────────────
    op.create_table(
        "ingestion_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_polled_at", sa.DateTime(timezone=True)),
        sa.Column("poll_interval_seconds", sa.Integer, nullable=False, server_default="3600"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── resumes ───────────────────────────────────────────────────────────────
    op.create_table(
        "resumes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_base", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("latex_source", sa.Text, nullable=False),
        sa.Column("compiled_pdf_path", sa.Text),
        sa.Column("parsed_data", postgresql.JSONB),
        sa.Column("template_name", sa.String(50)),
        sa.Column("word_count", sa.Integer),
        sa.Column("page_count", sa.Integer),
        sa.Column("base_resume_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("resumes.id", ondelete="SET NULL")),
        sa.Column("job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("tailoring_diff", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )

    # ── jobs ──────────────────────────────────────────────────────────────────
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_sources.id", ondelete="SET NULL")),
        sa.Column("dedup_hash", sa.String(64), nullable=False),
        sa.Column("raw_url", sa.Text),
        sa.Column("raw_html", sa.Text),
        sa.Column("raw_email_id", sa.String(255)),
        sa.Column("title", sa.String(255)),
        sa.Column("company", sa.String(255)),
        sa.Column("location", sa.String(255)),
        sa.Column("remote_policy", sa.String(20)),
        sa.Column("description", sa.Text),
        sa.Column("required_skills", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("preferred_skills", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("years_experience_min", sa.Integer),
        sa.Column("years_experience_max", sa.Integer),
        sa.Column("sponsorship_hint", sa.String(20)),
        sa.Column("salary_min", sa.Integer),
        sa.Column("salary_max", sa.Integer),
        sa.Column("salary_currency", sa.String(3)),
        sa.Column("deadline", sa.Date),
        sa.Column("application_url", sa.Text),
        sa.Column("application_questions", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("parse_rationale", postgresql.JSONB),
        sa.Column("fit_score", sa.SmallInteger),
        sa.Column("fit_rationale", postgresql.JSONB),
        sa.Column("status", sa.String(30), nullable=False, server_default="new"),
        sa.Column("parse_error", sa.Text),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "dedup_hash", name="uq_jobs_user_dedup"),
    )
    op.create_index("idx_jobs_user_status", "jobs", ["user_id", "status"])
    op.create_index("idx_jobs_user_company", "jobs", ["user_id", "company"])
    op.create_index("idx_jobs_fit_score", "jobs", ["user_id", "fit_score"])

    # ── applications ──────────────────────────────────────────────────────────
    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resume_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("resumes.id", ondelete="SET NULL")),
        sa.Column("cover_letter", sa.Text),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approval_hash", sa.String(64)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("submission_url", sa.Text),
        sa.Column("submission_screenshot_path", sa.Text),
        sa.Column("submission_error", sa.Text),
        sa.Column("outcome", sa.String(30)),
        sa.Column("user_notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "job_id", name="uq_applications_user_job"),
    )
    op.create_index("idx_applications_user_status", "applications", ["user_id", "status"])

    # ── questionnaire_answers ─────────────────────────────────────────────────
    op.create_table(
        "questionnaire_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("question_text", sa.Text, nullable=False),
        sa.Column("question_type", sa.String(30), nullable=False),
        sa.Column("draft_answer", sa.Text, nullable=False),
        sa.Column("final_answer", sa.Text),
        sa.Column("confidence", sa.String(10), nullable=False, server_default="medium"),
        sa.Column("requires_review", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("sources", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("rationale", sa.Text),
        sa.Column("user_edited", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("approved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── company_rules ─────────────────────────────────────────────────────────
    op.create_table(
        "company_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("rule_type", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("cooldown_days", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "company", "rule_type", name="uq_company_rules"),
    )

    # ── audit_logs ────────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor", sa.String(20), nullable=False),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("resource_type", sa.String(30)),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column("payload_hash", sa.String(64)),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("ip_address", postgresql.INET),
        sa.Column("user_agent", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_audit_user_action", "audit_logs", ["user_id", "action", "created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("company_rules")
    op.drop_table("questionnaire_answers")
    op.drop_table("applications")
    op.drop_table("jobs")
    op.drop_table("resumes")
    op.drop_table("ingestion_sources")
    op.drop_table("user_profiles")
    op.drop_table("users")
