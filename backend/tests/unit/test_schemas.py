import pytest
from pydantic import ValidationError

from schemas.recommendations import (
    CollaborativeRequest,
    RatingInput,
    RecommendFilters,
    SearchRequest,
)


class TestRatingInput:
    @pytest.mark.parametrize("score", [0.5, 1.0, 2.5, 4.5, 5.0])
    def test_valid_scores(self, score: float) -> None:
        r = RatingInput(movie_id=1, score=score)
        assert r.score == score

    @pytest.mark.parametrize("score", [0.0, 5.5, -1.0])
    def test_invalid_score_range(self, score: float) -> None:
        with pytest.raises(ValidationError):
            RatingInput(movie_id=1, score=score)

    @pytest.mark.parametrize("score", [1.3, 2.7, 3.1])
    def test_invalid_score_step(self, score: float) -> None:
        with pytest.raises(ValidationError, match="0.5 steps"):
            RatingInput(movie_id=1, score=score)

    def test_movie_id_zero(self) -> None:
        with pytest.raises(ValidationError):
            RatingInput(movie_id=0, score=3.0)

    def test_movie_id_negative(self) -> None:
        with pytest.raises(ValidationError):
            RatingInput(movie_id=-1, score=3.0)

    def test_movie_id_valid(self) -> None:
        r = RatingInput(movie_id=1, score=3.0)
        assert r.movie_id == 1


class TestSearchRequest:
    def test_empty_query_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SearchRequest(query="")

    def test_one_char_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SearchRequest(query="a")

    def test_two_chars_ok(self) -> None:
        r = SearchRequest(query="ab")
        assert r.query == "ab"

    def test_max_length_ok(self) -> None:
        r = SearchRequest(query="x" * 500)
        assert len(r.query) == 500

    def test_over_max_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SearchRequest(query="x" * 501)


class TestCollaborativeRequest:
    def _rating(self) -> RatingInput:
        return RatingInput(movie_id=1, score=4.0)

    def test_empty_ratings_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CollaborativeRequest(ratings=[])

    def test_one_rating_ok(self) -> None:
        r = CollaborativeRequest(ratings=[self._rating()])
        assert len(r.ratings) == 1

    def test_max_ratings_ok(self) -> None:
        r = CollaborativeRequest(ratings=[self._rating()] * 500)
        assert len(r.ratings) == 500

    def test_over_max_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CollaborativeRequest(ratings=[self._rating()] * 501)


class TestRecommendFilters:
    def test_default_all_none(self) -> None:
        f = RecommendFilters()
        assert f.year_from is None
        assert f.min_rating is None

    def test_year_from_valid(self) -> None:
        f = RecommendFilters(year_from=1990)
        assert f.year_from == 1990

    def test_min_rating_valid(self) -> None:
        f = RecommendFilters(min_rating=3.5)
        assert f.min_rating == 3.5

    def test_genres_list(self) -> None:
        f = RecommendFilters(genres=["Action", "Drama"])
        assert f.genres == ["Action", "Drama"]
