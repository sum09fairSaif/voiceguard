import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import switch as script


def test_status_shows_every_switch_on_by_default(switch_store, capsys):
    assert script.main(["status"], store=switch_store) == 0

    out = capsys.readouterr().out
    for name in ("signups", "voice_checks", "enrollment"):
        assert f"{name}" in out
    assert "OFF" not in out


def test_flipping_off_records_who_and_why(switch_store, capsys):
    script.main(["signups", "off", "--by", "Gabriel", "--reason", "signup flood"], store=switch_store)

    record = switch_store.find_one({"_id": "signups"})
    assert record["on"] is False
    assert record["changed_by"] == "Gabriel"
    out = capsys.readouterr().out
    assert "signups is now OFF" in out
    assert "signup flood" in out


def test_flipping_back_on(switch_store):
    script.main(["enrollment", "off", "--by", "G", "--reason", "x"], store=switch_store)
    script.main(["enrollment", "on", "--by", "G", "--reason", "fixed"], store=switch_store)

    assert switch_store.find_one({"_id": "enrollment"})["on"] is True


@pytest.mark.parametrize(
    "argv",
    [["signups", "off"], ["signups", "off", "--by", "G"], ["signups"], ["logins", "off", "--by", "G", "--reason", "x"]],
)
def test_a_flip_needs_a_known_switch_a_state_who_and_why(switch_store, argv):
    with pytest.raises(SystemExit):
        script.main(argv, store=switch_store)

    assert switch_store.count_documents({}) == 0


def test_status_mentions_a_setting_that_forces_a_switch_off(switch_store, monkeypatch, capsys):
    import config

    monkeypatch.setattr(config, "VOICE_CHECKS_ENABLED", False)

    script.main(["status"], store=switch_store)

    assert "forced off by VOICE_CHECKS_ENABLED=false" in capsys.readouterr().out


# --- Pausing enrollment strands new sign-ups (Sumehra's review on #164) ---------


def test_turning_enrollment_off_with_signups_on_warns(switch_store, capsys):
    script.main(["enrollment", "off", "--by", "G", "--reason", "model service slow"], store=switch_store)

    assert "WARNING: enrollment is off but signups is on" in capsys.readouterr().err


def test_no_warning_once_signups_are_off_too(switch_store, capsys):
    script.main(["signups", "off", "--by", "G", "--reason", "x"], store=switch_store)
    capsys.readouterr()

    script.main(["enrollment", "off", "--by", "G", "--reason", "x"], store=switch_store)

    assert "WARNING" not in capsys.readouterr().err


def test_turning_signups_back_on_while_enrollment_is_off_warns(switch_store, capsys):
    script.main(["signups", "off", "--by", "G", "--reason", "x"], store=switch_store)
    script.main(["enrollment", "off", "--by", "G", "--reason", "x"], store=switch_store)
    capsys.readouterr()

    script.main(["signups", "on", "--by", "G", "--reason", "x"], store=switch_store)

    assert "WARNING: enrollment is off but signups is on" in capsys.readouterr().err


def test_status_warns_about_the_stranding_combination(switch_store, capsys):
    script.main(["enrollment", "off", "--by", "G", "--reason", "x"], store=switch_store)
    capsys.readouterr()

    script.main(["status"], store=switch_store)

    assert "WARNING" in capsys.readouterr().err


def test_no_warning_in_normal_operation(switch_store, capsys):
    script.main(["status"], store=switch_store)

    assert capsys.readouterr().err == ""
