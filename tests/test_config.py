from waterreminder import config as C


def test_missing_file_writes_defaults(tmp_path):
    p = tmp_path / "sub" / "config.toml"
    c = C.load(p)
    assert p.exists() and c == C.Config()


def test_roundtrip(tmp_path):
    p = tmp_path / "c.toml"
    c = C.Config(days=[1, 2], interval_min=1, messages=['say "hi"\\x', "b"], start="08:30")
    C.save(c, p)
    assert C.load(p) == c


def test_invalid_toml_falls_back_and_keeps_file(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("this is [not toml")
    assert C.load(p) == C.Config()
    assert p.read_text() == "this is [not toml"


def test_bad_values_use_defaults_per_key(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('interval_min = "abc"\nstart = "25:99"\nvolume = 500\nsound = "nope"\ndays = [0, 9]\nsnooze_min = 7\n')
    c = C.load(p)
    assert c.interval_min == 45 and c.start == "09:00" and c.volume == 100
    assert c.sound == "drop" and c.days == [0] and c.snooze_min == 7


def test_unknown_keys_ignored(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("bogus = 1\n")
    assert C.load(p) == C.Config()
