"""Expand transcript storage into the transcription model."""

from alembic import op
import sqlalchemy as sa

revision = "0002_transcriptions"
down_revision = "0001_transcripts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("transcripts", "transcriptions")
    op.drop_index("ix_transcripts_created_at", table_name="transcriptions")
    op.alter_column("transcriptions", "content", new_column_name="transcript_text", existing_type=sa.Text())
    op.alter_column(
        "transcriptions", "language", new_column_name="detected_language",
        existing_type=sa.String(length=16), type_=sa.String(length=32), nullable=True,
    )
    op.alter_column(
        "transcriptions", "duration_seconds", existing_type=sa.Integer(), type_=sa.Float(), nullable=True
    )
    op.add_column(
        "transcriptions",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
    )
    op.add_column(
        "transcriptions",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column("transcriptions", sa.Column("metadata", sa.JSON(), nullable=True))
    op.create_index("ix_transcriptions_created_at", "transcriptions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_transcriptions_created_at", table_name="transcriptions")
    op.drop_column("transcriptions", "metadata")
    op.drop_column("transcriptions", "updated_at")
    op.drop_column("transcriptions", "status")
    op.alter_column(
        "transcriptions", "duration_seconds", existing_type=sa.Float(), type_=sa.Integer(), nullable=False
    )
    op.execute("UPDATE transcriptions SET detected_language = 'auto' WHERE detected_language IS NULL")
    op.alter_column(
        "transcriptions", "detected_language", new_column_name="language",
        existing_type=sa.String(length=32), type_=sa.String(length=16), nullable=False,
    )
    op.alter_column("transcriptions", "transcript_text", new_column_name="content", existing_type=sa.Text())
    op.rename_table("transcriptions", "transcripts")
    op.create_index("ix_transcripts_created_at", "transcripts", ["created_at"])