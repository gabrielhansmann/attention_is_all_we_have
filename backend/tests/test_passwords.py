import pytest

from app.auth import passwords


@pytest.fixture(autouse=True)
def fast_scrypt(monkeypatch):
    monkeypatch.setattr(passwords, "N", 2**10)     # stored hashes carry their own parameters; tests need not be slow


def test_a_hash_verifies_only_for_the_right_password():
    h = passwords.hash_password("correct horse battery")
    assert h.startswith("scrypt$") and "correct horse" not in h
    assert passwords.verify_password("correct horse battery", h)
    assert not passwords.verify_password("correct horse batterz", h)
    assert not passwords.verify_password("", h)


def test_each_hash_has_its_own_salt():
    assert passwords.hash_password("same password 123") != passwords.hash_password("same password 123")


def test_hash_parameters_come_from_the_stored_value_so_they_can_be_raised_later(monkeypatch):
    old = passwords.hash_password("a long enough password")
    monkeypatch.setattr(passwords, "N", 2**11)
    assert passwords.verify_password("a long enough password", old)


@pytest.mark.parametrize("stored", ["", "garbage", "scrypt$x$y$z$q$r", "bcrypt$1$2$3$4$5", "scrypt$1024$8$1$!!$!!", None])
def test_malformed_stored_values_are_just_wrong_never_an_error(stored):
    assert passwords.verify_password("anything at all", stored) is False


def test_password_policy_gives_actionable_messages():
    with pytest.raises(ValueError, match="at least 12"):
        passwords.check_policy("short")
    with pytest.raises(ValueError, match="at most 256"):
        passwords.check_policy("x" * 257)
    passwords.check_policy("exactly12chr")


def test_burn_time_runs_without_error():
    passwords.burn_time()
