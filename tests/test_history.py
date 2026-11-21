import json
from datetime import UTC, datetime

from kp9.history import History
from kp9.httpclient import Response
from kp9.model import AuthBearer, Body
from kp9.redact import MASK, Redactor
from kp9.resolve import ResolvedRequest

SECRET = "tok-123"
WHEN = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)


def make_req(**kw):
    base = dict(
        method="POST",
        url="https://api.test/items",
        params={"key": SECRET},
        headers={"Authorization": f"Bearer {SECRET}", "X-Trace": "t1"},
        body=Body(type="json", content={"password": SECRET, "qty": 1}),
        auth=AuthBearer(token=SECRET),
    )
    base.update(kw)
    return ResolvedRequest(**base)


def make_resp(body=b'{"token": "tok-123", "id": 1}', content_type="application/json"):
    return Response(
        status=201,
        reason="Created",
        headers=[("content-type", content_type), ("set-cookie", "sid=abc")],
        body=body,
        elapsed_ms=12.5,
    )


def test_record_and_get_roundtrip_redacted(tmp_path):
    h = History(tmp_path / "h.db")
    hid = h.record(
        req=make_req(),
        response=make_resp(),
        error=None,
        redactor=Redactor([SECRET]),
        env="qa",
        request_path="groups/a/b/c.json",
        now=WHEN,
    )
    e = h.get(hid)
    assert e is not None
    assert e.ts == "2026-11-20T10:00:00+00:00"
    assert (e.env, e.request_path, e.method) == ("qa", "groups/a/b/c.json", "POST")
    assert e.url == f"https://api.test/items?key={MASK}"
    assert SECRET not in e.request_json
    doc = json.loads(e.request_json)
    assert doc["headers"] == {"Authorization": MASK, "X-Trace": "t1"}
    assert doc["auth"] == {"type": "bearer"}
    assert ("set-cookie", MASK) in e.response_headers
    r = e.response()
    assert r is not None and r.status == 201 and r.elapsed_ms == 12.5
    assert json.loads(r.text()) == {"token": MASK, "id": 1}


def test_failed_execution_has_no_response(tmp_path):
    h = History(tmp_path / "h.db")
    hid = h.record(
        req=make_req(),
        response=None,
        error=f"network: fallo con {SECRET}",
        redactor=Redactor([SECRET]),
        env=None,
        request_path=None,
    )
    e = h.get(hid)
    assert e.status is None
    assert e.response() is None
    assert e.error == f"network: fallo con {MASK}"


def test_list_newest_first_and_last_for(tmp_path):
    h = History(tmp_path / "h.db")
    red = Redactor()
    a = h.record(
        req=make_req(),
        response=make_resp(),
        error=None,
        redactor=red,
        env="qa",
        request_path="a.json",
    )
    b = h.record(
        req=make_req(), response=None, error="x", redactor=red, env="qa", request_path="b.json"
    )
    c = h.record(
        req=make_req(),
        response=make_resp(),
        error=None,
        redactor=red,
        env="qa",
        request_path="a.json",
    )
    assert [e.id for e in h.list()] == [c, b, a]
    assert h.last_for("a.json").id == c
    assert h.last_for("zzz.json") is None
    assert h.get(9999) is None


def test_binary_body_stored_raw(tmp_path):
    h = History(tmp_path / "h.db")
    png = b"\x89PNG\r\n\x1a\n\x00\x00"
    hid = h.record(
        req=make_req(),
        response=make_resp(png, "image/png"),
        error=None,
        redactor=Redactor([SECRET]),
        env="qa",
        request_path=None,
    )
    assert h.get(hid).response().body == png


def test_persists_across_instances(tmp_path):
    h = History(tmp_path / "h.db")
    h.record(
        req=make_req(), response=None, error="x", redactor=Redactor(), env=None, request_path=None
    )
    h.close()
    assert len(History(tmp_path / "h.db").list()) == 1
