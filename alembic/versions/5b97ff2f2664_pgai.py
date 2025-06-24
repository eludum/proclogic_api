"""pgai

Revision ID: 5b97ff2f2664
Revises: 9dc262f2c7ac
Create Date: 2025-06-16 00:24:37.073002

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "5b97ff2f2664"
down_revision: Union[str, None] = "939123525392"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# TODO: make something without cron, just do it in the event startup, also write something for the old ones
def upgrade() -> None:
    # Enable required extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS ai CASCADE;")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector CASCADE;")

    # Add embedding column to publications table
    op.add_column(
        "publications",
        sa.Column(
            "embedding",
            sa.TypeDecorator.load_dialect_impl(sa.dialects.postgresql.ARRAY(sa.Float)),
            nullable=True,
        ),
    )

    # Create a searchable content column that combines all text fields
    op.execute(
        """
        ALTER TABLE publications 
        ADD COLUMN IF NOT EXISTS searchable_content TEXT GENERATED ALWAYS AS (
            COALESCE(
                (SELECT string_agg(d.text, ' ') 
                 FROM descriptions d 
                 JOIN dossiers dos ON dos.reference_number = publications.dossier_reference_number
                 WHERE d.dossier_reference_number = dos.reference_number), ''
            ) || ' ' ||
            COALESCE(
                (SELECT string_agg(on.text, ' ') 
                 FROM organisation_names on 
                 JOIN organisations o ON o.organisation_id = publications.organisation_id
                 WHERE on.organisation_id = o.organisation_id), ''
            ) || ' ' ||
            COALESCE(ai_summary_without_documents, '') || ' ' ||
            COALESCE(ai_summary_with_documents, '') || ' ' ||
            COALESCE(array_to_string(extracted_keywords, ' '), '')
        ) STORED;
    """
    )

    # Create index for better text search performance
    op.create_index(
        "idx_publications_searchable_content",
        "publications",
        [text("to_tsvector('dutch', searchable_content)")],
        postgresql_using="gin",
    )

    # Create the vectorizer
    op.execute(
        """
        SELECT ai.create_vectorizer(
            'publications_vectorizer'::regclass,
            destination => 'publications_embeddings',
            embedding => ai.embedding_openai('text-embedding-3-small', 1536),
            chunking => ai.chunking_recursive_character_text_splitter('searchable_content', 1000, 200),
            scheduling => ai.scheduling_timescaledb(interval => '5 minutes'),
            grant_to => 'postgres'
        );
    """
    )

    # Create the embeddings table with proper structure
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS publications_embeddings (
            id BIGSERIAL PRIMARY KEY,
            publication_workspace_id TEXT REFERENCES publications(publication_workspace_id) ON DELETE CASCADE,
            chunk_seq INT NOT NULL,
            chunk TEXT NOT NULL,
            embedding vector(1536) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(publication_workspace_id, chunk_seq)
        );
    """
    )

    # Create index for vector similarity search
    op.execute(
        """
        CREATE INDEX ON publications_embeddings 
        USING ivfflat (embedding vector_cosine_ops) 
        WITH (lists = 100);
    """
    )

    # Create a view that shows the vectorizer's source data
    op.execute(
        """
        CREATE OR REPLACE VIEW publications_vectorizer AS
        SELECT 
            publication_workspace_id as id,
            publication_workspace_id,
            searchable_content,
            publication_date,
            vault_submission_deadline,
            cpv_main_code_code,
            organisation_id,
            nuts_codes,
            estimated_value
        FROM publications
        WHERE vault_submission_deadline IS NOT NULL;
    """
    )


def downgrade() -> None:
    # Drop the vectorizer first
    op.execute("SELECT ai.drop_vectorizer('publications_vectorizer'::regclass);")

    # Drop views and tables
    op.execute("DROP VIEW IF EXISTS publications_vectorizer;")
    op.execute("DROP TABLE IF EXISTS publications_embeddings;")

    # Drop indexes
    op.drop_index("idx_publications_searchable_content")

    # Drop columns
    op.drop_column("publications", "searchable_content")
    op.drop_column("publications", "embedding")

    # Note: We don't drop extensions as they might be used by other parts
