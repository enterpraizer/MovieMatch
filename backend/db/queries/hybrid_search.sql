-- Hybrid Semantic + Full-Text Search using Reciprocal Rank Fusion (RRF)
-- Query typos are handled by the Python side (rapidfuzz vocabulary correction)
-- before this SQL runs; this query assumes $2 is already spell-corrected.
-- $1 FLOAT[] - query vector (384 dimensions from sentence-transformers)
-- $2 TEXT    - query text for full-text search
-- $3 INTEGER - result limit
-- $4 INTEGER - year_from filter (NULL to skip)
-- $5 INTEGER - year_to filter (NULL to skip)
-- $6 FLOAT   - min_rating filter (NULL to skip)
-- $7 INTEGER - offset (0 for first page)
WITH semantic_results AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            ORDER BY embedding <=> $1::vector ASC
        ) AS rank,
        1.0 - (embedding <=> $1::vector) AS semantic_score
    FROM movies
    WHERE
        embedding IS NOT NULL
        AND ($4::int IS NULL OR year >= $4)
        AND ($5::int IS NULL OR year <= $5)
        AND ($6::float IS NULL OR avg_rating >= $6)
    ORDER BY embedding <=> $1::vector ASC
    LIMIT 250
),
text_results AS (
    SELECT
        m.id,
        ROW_NUMBER() OVER (
            ORDER BY ts_rank_cd(m.search_vector, query, 32) DESC
        ) AS rank,
        ts_rank_cd(m.search_vector, query, 32) AS text_score
    FROM movies m,
         plainto_tsquery('english', $2) AS query
    WHERE
        m.search_vector @@ query
        AND ($4::int IS NULL OR m.year >= $4)
        AND ($5::int IS NULL OR m.year <= $5)
        AND ($6::float IS NULL OR m.avg_rating >= $6)
    ORDER BY text_score DESC
    LIMIT 250
),
rrf_scores AS (
    SELECT
        COALESCE(s.id, t.id)                     AS movie_id,
        COALESCE(1.0 / (60.0 + s.rank), 0.0) * 0.6 +
        COALESCE(1.0 / (60.0 + t.rank), 0.0) * 0.4 AS rrf_score,
        COALESCE(s.semantic_score, 0.0)            AS semantic_score,
        COALESCE(t.text_score, 0.0)                AS text_score
    FROM semantic_results s
    FULL OUTER JOIN text_results t ON s.id = t.id
)
SELECT
    m.id,
    m.title,
    m.year,
    m.avg_rating,
    m.rating_count,
    m.poster_path,
    m.description,
    r.rrf_score,
    r.semantic_score,
    r.text_score,
    ARRAY_REMOVE(
        ARRAY_AGG(DISTINCT g.name ORDER BY g.name),
        NULL
    ) AS genres
FROM rrf_scores r
JOIN movies m ON m.id = r.movie_id
LEFT JOIN movie_genres mg ON mg.movie_id = m.id
LEFT JOIN genres g ON g.id = mg.genre_id
GROUP BY
    m.id, m.title, m.year, m.avg_rating, m.rating_count,
    m.poster_path, m.description,
    r.rrf_score, r.semantic_score, r.text_score
-- Tiebreakers so identical rrf_score entries return in the same order each
-- time — otherwise the top-N changes between pages / between runs.
ORDER BY r.rrf_score DESC, r.semantic_score DESC, m.rating_count DESC NULLS LAST, m.id ASC
LIMIT $3 OFFSET $7;
