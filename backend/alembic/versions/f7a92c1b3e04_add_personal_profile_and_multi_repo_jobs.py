"""add_personal_profile_and_multi_repo_jobs

Revision ID: f7a92c1b3e04
Revises: a98385580fc5
Create Date: 2026-07-07 04:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f7a92c1b3e04'
down_revision: Union[str, Sequence[str], None] = '7374756ed0ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add personal profile fields to users and create multi_repo_jobs table."""

    # --- Add personal profile fields to users ---
    op.add_column('users', sa.Column(
        'full_name', sa.String(255), nullable=True,
        comment='Full display name for resume header.'
    ))
    op.add_column('users', sa.Column(
        'phone', sa.String(50), nullable=True,
        comment='Phone number for resume contact line.'
    ))
    op.add_column('users', sa.Column(
        'location', sa.String(255), nullable=True,
        comment="City/Country for resume header, e.g. 'Delhi, India'."
    ))
    op.add_column('users', sa.Column(
        'college', sa.String(500), nullable=True,
        comment='University or college name for education section.'
    ))
    op.add_column('users', sa.Column(
        'degree', sa.String(255), nullable=True,
        comment="Degree and major, e.g. 'BS in Data Science & Applications'."
    ))
    op.add_column('users', sa.Column(
        'cgpa', sa.String(50), nullable=True,
        comment="CGPA string, e.g. '7.6 / 10'."
    ))
    op.add_column('users', sa.Column(
        'graduation_year', sa.String(10), nullable=True,
        comment="Expected or actual graduation year, e.g. '2027'."
    ))
    op.add_column('users', sa.Column(
        'linkedin_url', sa.String(2048), nullable=True,
        comment='Full LinkedIn profile URL.'
    ))
    op.add_column('users', sa.Column(
        'portfolio_url', sa.String(2048), nullable=True,
        comment='Personal portfolio or website URL.'
    ))
    op.add_column('users', sa.Column(
        'profile_complete', sa.Boolean(), nullable=False,
        server_default='false',
        comment='True when name+email+target_role are all filled.'
    ))

    # --- Create multi_repo_jobs table ---
    op.create_table(
        'multi_repo_jobs',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text('gen_random_uuid()'),
            comment='Primary key for the combined resume generation job.'
        ),
        sa.Column(
            'user_id', postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
            index=True,
            comment='Owner of this job.'
        ),
        sa.Column(
            'repo_ids', postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment='List of up to 3 repository UUIDs.'
        ),
        sa.Column(
            'job_status', sa.String(50), nullable=False,
            server_default='queued',
            comment='Current pipeline status.'
        ),
        sa.Column(
            'output_pdf_key', sa.String(2048), nullable=True,
            comment='MinIO object key for the generated combined resume PDF.'
        ),
        sa.Column(
            'output_tex_key', sa.String(2048), nullable=True,
            comment='MinIO object key for the generated .tex source.'
        ),
        sa.Column(
            'personal_context', postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='Snapshot of user personal profile at time of generation.'
        ),
        sa.Column(
            'missing_fields', postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='Fields that were missing and prompted clarification.'
        ),
        sa.Column(
            'error_message', sa.String(), nullable=True,
            comment='LaTeX compiler error or pipeline failure message.'
        ),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
            comment='Job creation timestamp.'
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
            comment='Last status update timestamp.'
        ),
    )


def downgrade() -> None:
    """Remove personal profile fields from users and drop multi_repo_jobs."""

    op.drop_table('multi_repo_jobs')

    op.drop_column('users', 'profile_complete')
    op.drop_column('users', 'portfolio_url')
    op.drop_column('users', 'linkedin_url')
    op.drop_column('users', 'graduation_year')
    op.drop_column('users', 'cgpa')
    op.drop_column('users', 'degree')
    op.drop_column('users', 'college')
    op.drop_column('users', 'location')
    op.drop_column('users', 'phone')
    op.drop_column('users', 'full_name')
