"""re-add oauth identity fields to users

Restores the columns dropped by f72a31ae33a8 so Google sign-in can link
accounts again. Railway's database already had those columns dropped, so
this is a new revision on top of the current head rather than a revert.

Revision ID: b7c2d9e41f03
Revises: f72a31ae33a8
Create Date: 2026-11-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c2d9e41f03'
down_revision: Union[str, Sequence[str], None] = 'f72a31ae33a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('oauth_provider', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('oauth_subject', sa.String(length=255), nullable=True))
        batch_op.create_unique_constraint('uq_users_oauth_identity', ['oauth_provider', 'oauth_subject'])


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('uq_users_oauth_identity', type_='unique')
        batch_op.drop_column('oauth_subject')
        batch_op.drop_column('oauth_provider')
