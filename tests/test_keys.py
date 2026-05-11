from radio_key_daemon.keys import Debouncer


def test_debounce_is_tracked_per_key():
    debouncer = Debouncer(default_debounce_ms=250)

    assert debouncer.should_fire("KEY_F12", now=10.0) is True
    assert debouncer.should_fire("KEY_F12", now=10.1) is False
    assert debouncer.should_fire("KEY_F11", now=10.1) is True
    assert debouncer.should_fire("KEY_F12", now=10.251) is True


def test_debounce_allows_per_key_override():
    debouncer = Debouncer(default_debounce_ms=250)

    assert debouncer.should_fire("KEY_F12", now=20.0, debounce_ms=1000) is True
    assert debouncer.should_fire("KEY_F12", now=20.5, debounce_ms=1000) is False
    assert debouncer.should_fire("KEY_F12", now=21.001, debounce_ms=1000) is True
