from kp9.redact import MASK, Redactor


def test_sensitive_headers_masked_case_insensitive():
    r = Redactor()
    assert r.headers({"authorization": "Bearer x", "Accept": "json"}) == [
        ("authorization", MASK),
        ("Accept", "json"),
    ]
    assert r.headers([("Set-Cookie", "a=1"), ("X-API-KEY", "k"), ("Cookie", "c")]) == [
        ("Set-Cookie", MASK),
        ("X-API-KEY", MASK),
        ("Cookie", MASK),
    ]


def test_extra_headers_configurable():
    assert Redactor(extra_headers=["X-Session"]).headers([("x-session", "abc")]) == [
        ("x-session", MASK)
    ]


def test_secret_values_masked_in_text():
    assert Redactor(["s3cr3t"]).text("a=s3cr3t&b=1") == f"a={MASK}&b=1"


def test_longer_secrets_replaced_first():
    assert Redactor(["abc", "abcdef"]).text("abcdef") == MASK


def test_url_encoded_secret_masked():
    r = Redactor(["p@ss word"])
    assert r.text("x?pw=p%40ss%20word") == f"x?pw={MASK}"
    assert r.text("x?pw=p%40ss+word") == f"x?pw={MASK}"


def test_empty_secret_ignored():
    assert Redactor([""]).text("hola") == "hola"


def test_value_redacts_nested_structures():
    assert Redactor(["tok"]).value({"a": ["Bearer tok", 1], "tok": True}) == {
        "a": [f"Bearer {MASK}", 1],
        MASK: True,
    }


def test_non_sensitive_header_values_still_scrubbed():
    assert Redactor(["tok"]).headers({"X-Trace": "id-tok"}) == [("X-Trace", f"id-{MASK}")]
