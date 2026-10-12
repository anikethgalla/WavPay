"""Biometric template matching and similarity scoring service."""

from typing import Optional, Tuple
import numpy as np
from sqlalchemy.orm import Session
from app.config import settings
from app.models import PalmTemplate, User
from app.utils.image_utils import deserialize_features


class PalmMatcher:
    """Matches a probe palm feature vector against enrolled templates in the database."""

    def __init__(self, default_threshold: Optional[float] = None):
        self.default_threshold = default_threshold or settings.MATCH_THRESHOLD

    def match(
        self,
        probe_vector: np.ndarray,
        db: Session,
        threshold: Optional[float] = None
    ) -> Tuple[Optional[User], float, str]:
        """Compares probe feature vector with all enrolled user templates.

        Args:
            probe_vector: 1D float32 normalized feature vector.
            db: SQLAlchemy database session.
            threshold: Optional match threshold override (defaults to config MATCH_THRESHOLD).

        Returns:
            Tuple of (matched_user, highest_confidence, status_str)
        """
        match_thresh = threshold if threshold is not None else self.default_threshold

        templates = db.query(PalmTemplate).all()
        if not templates:
            return None, 0.0, "NO_MATCH"

        best_user_id = None
        best_score = -1.0

        for t in templates:
            try:
                enrolled_vector = deserialize_features(t.template)
                
                # Compute Cosine Similarity (Dot product of L2-normalized vectors)
                sim = float(np.dot(probe_vector, enrolled_vector))
                
                # Clamp score to [0.0, 1.0]
                sim = max(0.0, min(1.0, sim))

                if sim > best_score:
                    best_score = sim
                    best_user_id = t.user_id

            except Exception:
                continue

        if best_user_id and best_score >= match_thresh:
            user = db.query(User).filter(User.user_id == best_user_id, User.active == True).first()
            if user:
                return user, round(best_score, 4), "MATCH_FOUND"

        return None, round(max(0.0, best_score), 4), "NO_MATCH"


# Default singleton instance
palm_matcher = PalmMatcher()
