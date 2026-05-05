"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-15

"""
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.execute(
        """
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            display_name VARCHAR(100),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            CONSTRAINT users_email_unique UNIQUE (email)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE movies (
            id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            imdb_id VARCHAR(20),
            tmdb_id INTEGER,
            title VARCHAR(500) NOT NULL,
            title_original VARCHAR(500),
            year SMALLINT,
            runtime_minutes SMALLINT,
            description TEXT,
            avg_rating NUMERIC(3,2) CHECK (avg_rating >= 1.0 AND avg_rating <= 5.0),
            rating_count INTEGER NOT NULL DEFAULT 0,
            popularity_score NUMERIC(8,4) NOT NULL DEFAULT 0.0,
            poster_path VARCHAR(500),
            search_vector TSVECTOR,
            embedding VECTOR(384),
            embedding_updated_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT movies_imdb_id_unique UNIQUE (imdb_id),
            CONSTRAINT movies_tmdb_id_unique UNIQUE (tmdb_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE genres (
            id SMALLINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            name VARCHAR(50) NOT NULL,
            name_ru VARCHAR(50),
            slug VARCHAR(50) NOT NULL,
            CONSTRAINT genres_name_unique UNIQUE (name),
            CONSTRAINT genres_slug_unique UNIQUE (slug)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE movie_genres (
            movie_id INTEGER NOT NULL,
            genre_id SMALLINT NOT NULL,
            PRIMARY KEY (movie_id, genre_id),
            CONSTRAINT fk_movie_genres_movie FOREIGN KEY (movie_id)
                REFERENCES movies(id) ON DELETE CASCADE,
            CONSTRAINT fk_movie_genres_genre FOREIGN KEY (genre_id)
                REFERENCES genres(id) ON DELETE CASCADE
        )
        """
    )

    op.execute(
        """
        CREATE TABLE ratings (
            id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            user_id UUID NOT NULL,
            movie_id INTEGER NOT NULL,
            score NUMERIC(3,1) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ratings_score_range CHECK (score >= 0.5 AND score <= 5.0),
            CONSTRAINT ratings_score_step CHECK (MOD(score * 2, 1) = 0),
            CONSTRAINT ratings_user_movie_unique UNIQUE (user_id, movie_id),
            CONSTRAINT fk_ratings_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_ratings_movie FOREIGN KEY (movie_id)
                REFERENCES movies(id) ON DELETE CASCADE
        )
        """
    )

    op.execute(
        """
        CREATE TABLE user_embeddings (
            user_id UUID PRIMARY KEY,
            embedding VECTOR(128),
            model_version VARCHAR(50),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT fk_user_embeddings_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    op.execute(
        """
        CREATE TABLE people (
            id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            name VARCHAR(200) NOT NULL,
            tmdb_id INTEGER,
            birth_year SMALLINT,
            profile_path VARCHAR(500),
            CONSTRAINT people_tmdb_id_unique UNIQUE (tmdb_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE movie_credits (
            movie_id INTEGER NOT NULL,
            person_id INTEGER NOT NULL,
            role VARCHAR(20) NOT NULL,
            character_name VARCHAR(200),
            order_index SMALLINT,
            PRIMARY KEY (movie_id, person_id, role),
            CONSTRAINT movie_credits_role_check CHECK (role IN ('director', 'actor', 'writer')),
            CONSTRAINT fk_credits_movie FOREIGN KEY (movie_id)
                REFERENCES movies(id) ON DELETE CASCADE,
            CONSTRAINT fk_credits_person FOREIGN KEY (person_id)
                REFERENCES people(id) ON DELETE CASCADE
        )
        """
    )

    op.execute("CREATE INDEX idx_movies_year ON movies(year)")
    op.execute("CREATE INDEX idx_movies_avg_rating ON movies(avg_rating DESC NULLS LAST)")
    op.execute("CREATE INDEX idx_movies_popularity ON movies(popularity_score DESC)")
    op.execute("CREATE INDEX idx_movies_rating_count ON movies(rating_count DESC)")
    op.execute("CREATE INDEX idx_ratings_user_id ON ratings(user_id)")
    op.execute("CREATE INDEX idx_ratings_movie_id ON ratings(movie_id)")
    op.execute("CREATE INDEX idx_ratings_score ON ratings(score)")
    op.execute("CREATE INDEX idx_movie_credits_movie ON movie_credits(movie_id)")
    op.execute("CREATE INDEX idx_movie_credits_person ON movie_credits(person_id)")
    op.execute("CREATE INDEX idx_movies_search_vector ON movies USING GIN(search_vector)")
    op.execute("CREATE INDEX idx_movies_title_trgm ON movies USING GIN(title gin_trgm_ops)")
    op.execute("CREATE INDEX idx_movies_desc_trgm ON movies USING GIN(description gin_trgm_ops)")
    op.execute(
        """
        CREATE INDEX idx_movies_embedding ON movies
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_user_embeddings_vec ON user_embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_movies_search_vector()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.search_vector := to_tsvector('english',
                COALESCE(NEW.title, '') || ' ' ||
                COALESCE(NEW.title_original, '') || ' ' ||
                COALESCE(NEW.description, ''));
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_movies_search_vector
            BEFORE INSERT OR UPDATE OF title, title_original, description ON movies
            FOR EACH ROW EXECUTE FUNCTION update_movies_search_vector()
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_users_updated_at
            BEFORE UPDATE ON users
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ratings_updated_at
            BEFORE UPDATE ON ratings
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_ratings_updated_at ON ratings")
    op.execute("DROP TRIGGER IF EXISTS trg_users_updated_at ON users")
    op.execute("DROP TRIGGER IF EXISTS trg_movies_search_vector ON movies")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")
    op.execute("DROP FUNCTION IF EXISTS update_movies_search_vector()")

    op.execute("DROP TABLE IF EXISTS movie_credits")
    op.execute("DROP TABLE IF EXISTS people")
    op.execute("DROP TABLE IF EXISTS user_embeddings")
    op.execute("DROP TABLE IF EXISTS ratings")
    op.execute("DROP TABLE IF EXISTS movie_genres")
    op.execute("DROP TABLE IF EXISTS genres")
    op.execute("DROP TABLE IF EXISTS movies")
    op.execute("DROP TABLE IF EXISTS users")
