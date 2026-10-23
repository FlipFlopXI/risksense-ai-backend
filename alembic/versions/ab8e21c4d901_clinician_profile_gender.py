"""Optional clinician profile gender for self-selected profile display."""

from alembic import op
import sqlalchemy as sa

revision = "ab8e21c4d901"
down_revision = "f29a6e7d104b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("clinicians", sa.Column("gender", sa.String(length=20), nullable=True))
    op.create_check_constraint("ck_clinicians_gender", "clinicians",
                               "gender IS NULL OR gender IN ('female', 'male', 'unspecified')")


def downgrade():
    op.drop_constraint("ck_clinicians_gender", "clinicians", type_="check")
    op.drop_column("clinicians", "gender")
