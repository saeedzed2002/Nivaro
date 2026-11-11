"""Server-side synchronizer token for guest sessions."""

import sqlalchemy as sa
from alembic import op

revision = "0002_guest_csrf"
down_revision = "0001_cart"
branch_labels = None
depends_on = None


def upgrade():
    # Older guest rows receive a token only after possession of their opaque
    # guest cookie is verified; migration never resets owners or cart contents.
    op.add_column("owners", sa.Column("guest_csrf", sa.String(43), nullable=True))
    op.create_check_constraint(
        "owner_guest_csrf",
        "owners",
        "guest_csrf IS NULL OR (guest_digest IS NOT NULL AND char_length(guest_csrf) = 43)",
    )


def downgrade():
    raise RuntimeError("Forward-only migration; preserve guest session protection")
