"""Add durable revisioned state for the local Learning service API.

Revision ID: d0e1f2a3b4c5
Revises: c7d8e9f0a1b2
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "learning_course_state" not in tables:
        op.create_table(
            "learning_course_state",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("course_id", sa.Integer(), nullable=False, unique=True),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("review_status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("source_metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(["course_id"], ["course.id"], ondelete="CASCADE"),
        )

    if "learning_course_collection_state" not in tables:
        op.create_table(
            "learning_course_collection_state",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("org_id", sa.Integer(), nullable=False, unique=True),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("fingerprint", sa.String(length=4096), nullable=False, server_default=""),
            sa.ForeignKeyConstraint(["org_id"], ["organization.id"], ondelete="CASCADE"),
        )

    if "learning_course_source" not in tables:
        op.create_table(
            "learning_course_source",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("course_id", sa.Integer(), nullable=False),
            sa.Column("media_id", sa.Integer(), nullable=False, unique=True),
            sa.Column("source_uuid", sa.String(length=36), nullable=False, unique=True),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("title", sa.String(length=512), nullable=False, server_default=""),
            sa.Column("source_url", sa.String(length=2048), nullable=False, server_default=""),
            sa.ForeignKeyConstraint(["course_id"], ["course.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        )
        op.create_index(
            "ix_learning_course_source_course_id",
            "learning_course_source",
            ["course_id"],
        )
        op.create_index(
            "ix_learning_course_source_source_uuid",
            "learning_course_source",
            ["source_uuid"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "learning_course_source" in tables:
        op.drop_index("ix_learning_course_source_source_uuid", table_name="learning_course_source")
        op.drop_index("ix_learning_course_source_course_id", table_name="learning_course_source")
        op.drop_table("learning_course_source")
    if "learning_course_collection_state" in tables:
        op.drop_table("learning_course_collection_state")
    if "learning_course_state" in tables:
        op.drop_table("learning_course_state")
