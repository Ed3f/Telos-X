"""Move Telegram user group membership to a many-to-many table.

Revision ID: 20260821_0001
Revises:
Create Date: 2026-08-21
"""

from typing import Optional, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20260821_0001'
down_revision: Optional[str] = None
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Backfill valid memberships, then remove telegram_user.group_id."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if 'telegram_user_group' not in table_names:
        op.create_table(
            'telegram_user_group',
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('group_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(
                ['user_id'],
                ['telegram_user.id'],
                ondelete='CASCADE',
            ),
            sa.ForeignKeyConstraint(
                ['group_id'],
                ['telegram_group.id'],
                ondelete='CASCADE',
            ),
            sa.PrimaryKeyConstraint('user_id', 'group_id'),
        )
        op.create_index(
            'ix_telegram_user_group_user_id',
            'telegram_user_group',
            ['user_id'],
        )
        op.create_index(
            'ix_telegram_user_group_group_id',
            'telegram_user_group',
            ['group_id'],
        )

    user_columns = {
        column['name']
        for column in sa.inspect(bind).get_columns('telegram_user')
    }
    if 'group_id' not in user_columns:
        return

    # Only rows with a real parent group are migrated, so enabling FK checks
    # after the migration cannot expose invalid association rows.
    op.execute(
        sa.text(
            'INSERT OR IGNORE INTO telegram_user_group (user_id, group_id) '
            'SELECT telegram_user.id, telegram_user.group_id '
            'FROM telegram_user '
            'JOIN telegram_group '
            'ON telegram_group.id = telegram_user.group_id '
            'WHERE telegram_user.group_id IS NOT NULL'
        )
    )

    with op.batch_alter_table('telegram_user', recreate='always') as batch_op:
        batch_op.drop_column('group_id')
        if 'date_profilation' in user_columns:
            batch_op.alter_column(
                'date_profilation',
                existing_type=sa.DateTime(),
                nullable=True,
            )


def downgrade() -> None:
    """Restore one representative group_id per user (necessarily lossy)."""
    bind = op.get_bind()
    user_columns = {
        column['name']
        for column in sa.inspect(bind).get_columns('telegram_user')
    }
    if 'group_id' not in user_columns:
        with op.batch_alter_table('telegram_user', recreate='always') as batch_op:
            batch_op.add_column(sa.Column('group_id', sa.Integer(), nullable=True))
            batch_op.create_index('ix_telegram_user_group_id', ['group_id'])

    op.execute(
        sa.text(
            'UPDATE telegram_user SET group_id = ('
            'SELECT MIN(telegram_user_group.group_id) '
            'FROM telegram_user_group '
            'WHERE telegram_user_group.user_id = telegram_user.id)'
        )
    )
    op.drop_table('telegram_user_group')
