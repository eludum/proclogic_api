"""trial

Revision ID: 8547cf81bbd3
Revises: 939123525392
Create Date: 2025-06-26 23:55:35.669931

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8547cf81bbd3'
down_revision: Union[str, None] = '939123525392'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add trial fields to companies table"""
    
    # Add trial-related columns to companies table
    op.add_column('companies', sa.Column('trial_start_date', sa.DateTime(), nullable=True))
    op.add_column('companies', sa.Column('trial_end_date', sa.DateTime(), nullable=True))
    op.add_column('companies', sa.Column('is_trial_active', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('companies', sa.Column('stripe_customer_id', sa.String(255), nullable=True))
    op.add_column('companies', sa.Column('stripe_subscription_id', sa.String(255), nullable=True))
    op.add_column('companies', sa.Column('subscription_status', sa.String(50), nullable=False, server_default='inactive'))
    
    # Add indexes for better query performance
    op.create_index('ix_companies_trial_end_date', 'companies', ['trial_end_date'])
    op.create_index('ix_companies_is_trial_active', 'companies', ['is_trial_active'])
    op.create_index('ix_companies_subscription_status', 'companies', ['subscription_status'])
    op.create_index('ix_companies_stripe_customer_id', 'companies', ['stripe_customer_id'])

def downgrade() -> None:
    """Remove trial fields from companies table"""
    
    # Drop indexes
    op.drop_index('ix_companies_stripe_customer_id', 'companies')
    op.drop_index('ix_companies_subscription_status', 'companies')
    op.drop_index('ix_companies_is_trial_active', 'companies')
    op.drop_index('ix_companies_trial_end_date', 'companies')
    
    # Drop columns
    op.drop_column('companies', 'subscription_status')
    op.drop_column('companies', 'stripe_subscription_id')
    op.drop_column('companies', 'stripe_customer_id')
    op.drop_column('companies', 'is_trial_active')
    op.drop_column('companies', 'trial_end_date')
    op.drop_column('companies', 'trial_start_date')
