"""Learning Teil B: fixed learner id per account, learning groups and invitation links.

Revision ID: bbfd7dc8ca72
Revises: d0e1f2a3b4c5
Create Date: 2026-11-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "bbfd7dc8ca72"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "learning_person" not in tables:
        op.create_table(
            "learning_person",
            sa.Column("user_id", sa.Integer(), primary_key=True, nullable=False, autoincrement=False),
            sa.Column("actor_id", sa.String(length=128), nullable=False, unique=True),
            sa.Column(
                "erstellt_am",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        )

    if "learning_gruppe" not in tables:
        op.create_table(
            "learning_gruppe",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("usergroup_id", sa.Integer(), nullable=False, unique=True),
            sa.Column("course_id", sa.Integer(), nullable=False),
            sa.Column("offen", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("erstellt_von", sa.Integer(), nullable=False),
            sa.Column(
                "erstellt_am",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(["usergroup_id"], ["usergroup.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["course_id"], ["course.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["erstellt_von"], ["user.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_learning_gruppe_course_id", "learning_gruppe", ["course_id"])

    if "learning_link" not in tables:
        op.create_table(
            "learning_link",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("token_sha256", sa.CHAR(length=64), nullable=False, unique=True),
            sa.Column("art", sa.String(length=16), nullable=False),
            sa.Column("org_id", sa.Integer(), nullable=False),
            sa.Column("gruppe_id", sa.Integer(), nullable=True),
            sa.Column("erstellt_von", sa.Integer(), nullable=False),
            sa.Column(
                "erstellt_am",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("laeuft_ab", sa.DateTime(timezone=True), nullable=True),
            sa.Column("zurueckgezogen_am", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "art IN ('admin', 'kursleiter', 'gruppe')", name="ck_learning_link_art"
            ),
            sa.ForeignKeyConstraint(["org_id"], ["organization.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["gruppe_id"], ["learning_gruppe.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["erstellt_von"], ["user.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_learning_link_org_id", "learning_link", ["org_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "learning_link" in tables:
        op.drop_index("ix_learning_link_org_id", table_name="learning_link")
        op.drop_table("learning_link")
    if "learning_gruppe" in tables:
        op.drop_index("ix_learning_gruppe_course_id", table_name="learning_gruppe")
        op.drop_table("learning_gruppe")
    if "learning_person" in tables:
        op.drop_table("learning_person")
