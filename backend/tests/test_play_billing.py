"""Unit test Google Play Billing — tanpa jaringan, tanpa DB.

Test existing lain bersifat integrasi (butuh server + Mongo). Modul ini menguji
logika murni: pemetaan produk dan verifikasi Play Developer API dengan requests
di-monkeypatch.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import integrations  # noqa: E402
import server  # noqa: E402


class _Resp:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_play_product_mapping():
    assert server.PLAY_PRODUCTS["titisanku_pro_yearly"] == "pro"
    assert server.PLAY_PRODUCTS["titisanku_family_yearly"] == "family"


def test_verify_play_subscription_ok(monkeypatch):
    monkeypatch.setenv("PLAY_PACKAGE_NAME", "com.titisanku.app")
    monkeypatch.setattr(integrations, "firebase_access_token", lambda scopes=None: "tok")
    captured = {}

    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        return _Resp(200, {"paymentState": 1, "orderId": "GPA.1234", "expiryTimeMillis": "9999999999999"})

    monkeypatch.setattr(integrations.requests, "get", fake_get)

    sub = integrations.verify_play_subscription("token-abc", "titisanku_pro_yearly")
    assert sub["orderId"] == "GPA.1234"
    assert "com.titisanku.app" in captured["url"]
    assert "titisanku_pro_yearly" in captured["url"]
    assert "token-abc" in captured["url"]


def test_verify_play_subscription_not_found(monkeypatch):
    monkeypatch.setenv("PLAY_PACKAGE_NAME", "com.titisanku.app")
    monkeypatch.setattr(integrations, "firebase_access_token", lambda scopes=None: "tok")
    monkeypatch.setattr(integrations.requests, "get", lambda *a, **k: _Resp(404))
    with pytest.raises(integrations.IntegrationError):
        integrations.verify_play_subscription("bad", "titisanku_pro_yearly")


def test_verify_requires_package(monkeypatch):
    monkeypatch.delenv("PLAY_PACKAGE_NAME", raising=False)
    monkeypatch.delenv("ANDROID_PACKAGE_NAME", raising=False)
    with pytest.raises(integrations.IntegrationError):
        integrations.verify_play_subscription("t", "titisanku_pro_yearly")


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"paymentState": 1}, True),   # payment received
        ({"paymentState": 2}, True),   # free trial
        ({"paymentState": "1"}, True),  # string dinormalisasi ke int
        ({"paymentState": 0}, False),  # pending, belum dibayar
        ({"paymentState": 3}, False),  # pending deferred upgrade/downgrade
        ({"paymentState": None}, False),
        ({"paymentState": "abc"}, False),
        ({}, False),
    ],
)
def test_play_payment_is_active(payload, expected):
    assert server.play_payment_is_active(payload) is expected

