"""Add original audio archive metadata."""

from alembic import op
import sqlalchemy as sa

revision = "0003_transcription_audio"
down_revision = "0002_transcriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transcriptions", sa.Column("audio_storage_key", sa.String(length=255), nullable=True))
    op.add_column("transcriptions", sa.Column("audio_media_type", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("transcriptions", "audio_media_type")
    op.drop_column("transcriptions", "audio_storage_key")