"""user_memory: preferred_name + user_knowledge user_id

Revision ID: f1a2b3c4d5e6
Revises: c1eaaa780b52
Create Date: 2026-09-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'c1eaaa780b52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('preferred_name', sa.String(length=255), nullable=True))

    with op.batch_alter_table('user_knowledge', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_user_knowledge_user_id', ['user_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_user_knowledge_user_id', 'users',
            ['user_id'], ['id'],
            ondelete='CASCADE',
        )
        # Per-user key uniqueness (NULLs are excluded from unique enforcement in SQLite)
        batch_op.create_index('ix_user_knowledge_user_key', ['user_id', 'key'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('user_knowledge', schema=None) as batch_op:
        batch_op.drop_index('ix_user_knowledge_user_key')
        batch_op.drop_constraint('fk_user_knowledge_user_id', type_='foreignkey')
        batch_op.drop_index('ix_user_knowledge_user_id')
        batch_op.drop_column('user_id')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('preferred_name')
