"""Integration tests for user enrollment, retrieval, and template purging."""

import cv2
import numpy as np
import pytest
from tests.test_palm_processing import create_synthetic_palm_image


def test_user_crud_and_biometric_purge(client):
    """Verifies enrolling a user, querying user profile, and purging biometric data."""
    palm_img = create_synthetic_palm_image()
    _, buffer = cv2.imencode(".jpg", palm_img)

    # 1. Enroll User
    res = client.post(
        "/api/users/enroll",
        data={"user_id": "USR002", "name": "Rahul Sharma", "email": "rahul@example.com"},
        files={"file": ("palm.jpg", buffer.tobytes(), "image/jpeg")}
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ENROLLED"
    assert res.json()["templates_stored"] == 1

    # 2. Get User Profile
    get_res = client.get("/api/users/USR002")
    assert get_res.status_code == 200
    user_data = get_res.json()
    assert user_data["user_id"] == "USR002"
    assert user_data["name"] == "Rahul Sharma"
    assert user_data["templates_count"] == 1

    # 3. Purge Biometric Template
    del_res = client.delete("/api/users/USR002/biometric")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "DELETED"
    assert del_res.json()["templates_deleted"] == 1

    # 4. Verify template count is now 0
    get_res_after = client.get("/api/users/USR002")
    assert get_res_after.json()["templates_count"] == 0


def test_get_nonexistent_user(client):
    """Verifies 404 for unknown user."""
    res = client.get("/api/users/UNKNOWN_999")
    assert res.status_code == 404
