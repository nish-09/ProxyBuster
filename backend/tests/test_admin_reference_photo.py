from tests.conftest import auth_headers, make_class_setup


def test_professor_cannot_upload_reference_photo(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    resp = client.post(
        f"/api/admin/students/{setup['student_profile_id']}/reference-photo",
        files={"file": ("r.jpg", b"data", "image/jpeg")},
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert resp.status_code == 403


def test_student_cannot_upload_reference_photo(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    resp = client.post(
        f"/api/admin/students/{setup['student_profile_id']}/reference-photo",
        files={"file": ("r.jpg", b"data", "image/jpeg")},
        headers=auth_headers(student_and_token["access_token"]),
    )
    assert resp.status_code == 403


def test_admin_upload_list_get_delete_reference_photo(client, db_session, professor_and_token, student_and_token, admin_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])

    upload = client.post(
        f"/api/admin/students/{setup['student_profile_id']}/reference-photo",
        files={"file": ("r.jpg", b"jpeg-bytes-here", "image/jpeg")},
        headers=auth_headers(admin_and_token["access_token"]),
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["has_reference_photo"] is True

    listed = client.get("/api/admin/students", headers=auth_headers(admin_and_token["access_token"]))
    assert any(s["has_reference_photo"] for s in listed.json())

    fetched = client.get(
        f"/api/admin/students/{setup['student_profile_id']}/reference-photo",
        headers=auth_headers(admin_and_token["access_token"]),
    )
    assert fetched.status_code == 200
    assert fetched.content == b"jpeg-bytes-here"
    assert fetched.headers["content-type"] == "image/jpeg"

    # Re-uploading replaces the existing photo rather than erroring or duplicating rows.
    reupload = client.post(
        f"/api/admin/students/{setup['student_profile_id']}/reference-photo",
        files={"file": ("r2.png", b"png-bytes-here", "image/png")},
        headers=auth_headers(admin_and_token["access_token"]),
    )
    assert reupload.status_code == 200, reupload.text
    refetched = client.get(
        f"/api/admin/students/{setup['student_profile_id']}/reference-photo",
        headers=auth_headers(admin_and_token["access_token"]),
    )
    assert refetched.content == b"png-bytes-here"

    deleted = client.delete(
        f"/api/admin/students/{setup['student_profile_id']}/reference-photo",
        headers=auth_headers(admin_and_token["access_token"]),
    )
    assert deleted.status_code == 204

    missing = client.get(
        f"/api/admin/students/{setup['student_profile_id']}/reference-photo",
        headers=auth_headers(admin_and_token["access_token"]),
    )
    assert missing.status_code == 404


def test_unsupported_reference_photo_type_rejected(client, db_session, professor_and_token, student_and_token, admin_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    resp = client.post(
        f"/api/admin/students/{setup['student_profile_id']}/reference-photo",
        files={"file": ("r.gif", b"data", "image/gif")},
        headers=auth_headers(admin_and_token["access_token"]),
    )
    assert resp.status_code == 422


def test_oversized_reference_photo_rejected(client, db_session, professor_and_token, student_and_token, admin_and_token, monkeypatch):
    from types import SimpleNamespace

    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    monkeypatch.setattr(
        "app.services.admin_service.get_settings", lambda: SimpleNamespace(reference_photo_max_bytes=10)
    )
    resp = client.post(
        f"/api/admin/students/{setup['student_profile_id']}/reference-photo",
        files={"file": ("r.jpg", b"x" * 100, "image/jpeg")},
        headers=auth_headers(admin_and_token["access_token"]),
    )
    assert resp.status_code == 422
