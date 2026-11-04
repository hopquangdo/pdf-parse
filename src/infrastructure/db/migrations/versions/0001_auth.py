"""accounts, sessions, refresh tokens

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

from src.infrastructure.db.types import UTCDateTime

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("name", sa.String(120), nullable=False, server_default=""),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("must_change_password", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("failed_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", UTCDateTime, nullable=True),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("last_login_at", UTCDateTime, nullable=True),
        sa.Column("password_changed_at", UTCDateTime, nullable=True),
        sa.CheckConstraint("role in ('admin', 'user')", name="ck_users_role"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("last_refreshed_at", UTCDateTime, nullable=False),
        sa.Column("absolute_expires_at", UTCDateTime, nullable=False),
        sa.Column("revoked_at", UTCDateTime, nullable=True),
        sa.Column("revoked_reason", sa.String(32), nullable=True),
        sa.Column("ip", sa.String(64), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(255), nullable=False, server_default=""),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])

    op.create_table(
        "refresh_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.String(32), sa.ForeignKey("auth_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
        sa.Column("expires_at", UTCDateTime, nullable=False),
        sa.Column("rotated_at", UTCDateTime, nullable=True),
    )
    op.create_index("ix_refresh_tokens_session_id", "refresh_tokens", ["session_id"])


def downgrade() -> None:
    for table in ("refresh_tokens", "auth_sessions", "users"):
        op.drop_table(table)
