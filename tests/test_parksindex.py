"""Licence parsing is pure; the Wikipedia and Commons calls are exercised by the real run."""
from parkwild.parksindex import pick_licence, strip_html


def _em(short, artist="<a href='x'>Jane Doe</a>", url="https://creativecommons.org/licenses/by-sa/4.0"):
    return {"LicenseShortName": {"value": short}, "Artist": {"value": artist}, "LicenseUrl": {"value": url}}


def test_reusable_licences_pass_with_a_text_credit():
    for short in ("CC BY-SA 4.0", "CC BY 2.0", "CC0", "Public domain", "PD-USGov-NPS"):
        lic = pick_licence(_em(short))
        assert lic and lic["license"] == short and lic["artist"] == "Jane Doe"


def test_non_reusable_or_missing_licences_are_refused():
    for short in ("GFDL", "Fair use", "Copyrighted free use", ""):
        assert pick_licence(_em(short)) is None
    assert pick_licence({}) is None


def test_artist_html_is_stripped_and_cut():
    assert strip_html("<p>  Jon   Sullivan, <i>PD Photo</i>. </p>") == "Jon Sullivan, PD Photo."
    long = pick_licence(_em("CC BY 4.0", artist="x" * 200))
    assert long and len(long["artist"]) == 80 and long["artist"].endswith("…")
