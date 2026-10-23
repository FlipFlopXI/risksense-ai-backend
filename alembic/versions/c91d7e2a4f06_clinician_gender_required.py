"""Backfill existing clinician gender without inferring identity from names.

Revision ID: c91d7e2a4f06
Revises: ab8e21c4d901
"""
from alembic import op
import sqlalchemy as sa

revision = "c91d7e2a4f06"
down_revision = "ab8e21c4d901"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE clinicians SET gender = 'unspecified' WHERE gender IS NULL")
    op.alter_column("clinicians", "gender", existing_type=sa.String(length=20),
                    nullable=False, server_default="unspecified")


def downgrade():
    op.alter_column("clinicians", "gender", existing_type=sa.String(length=20),
                    nullable=True, server_default=None)
