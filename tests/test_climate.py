"""Climate normals are a pure fold over daily rows; the archive call is faked."""
import json
from datetime import date

from parkwild.climate import build_climate, monthly_normals
from parkwild.config import BBox, Park


def test_monthly_normals_average_per_day_and_sum_per_year():
    days = ["2024-01-01", "2024-01-02", "2025-01-01", "2024-07-01"]
    rows = monthly_normals(days, [2.0, 4.0, 6.0, 30.0], [-10.0, -8.0, -6.0, 12.0], [0.0, 5.0, 0.4, 0.0], [10.0, 0.0, 2.0, 0.0])
    jan, jul = rows[0], rows[6]
    assert jan["tmax"] == 4.0 and jan["tmin"] == -8.0
    assert jan["precip_mm"] == 3 and jan["snow_cm"] == 6.0 and jan["wet_days"] == 0   # 5.4 mm and 12 cm over two years; one wet day over two years rounds to 0
    assert jul["tmax"] == 30.0 and rows[3]["tmax"] is None


def test_build_climate_writes_the_file(tmp_path, monkeypatch):
    class R:
        status_code = 200

        def raise_for_status(self): pass
        def json(self):
            return {"elevation": 1500.0, "daily": {"time": ["2025-06-01", "2025-06-02"], "temperature_2m_max": [25.0, 27.0],
                    "temperature_2m_min": [10.0, 12.0], "precipitation_sum": [0.0, 2.0], "snowfall_sum": [0.0, 0.0]}}
    class S:
        def __init__(self): self.params = None
        def get(self, url, params=None, **kw):
            self.params = params
            return R()
    monkeypatch.setattr("parkwild.climate.write_park_manifest", lambda out_dir, key: None)
    park = Park(key="t", name="T", state="XX", inat_place_id=1, bbox=BBox(-113.2, 37.1, -112.8, 37.5))
    s = S()
    stats = build_climate(park, tmp_path, session=s, today=date(2026, 9, 6))
    j = json.loads((tmp_path / "climate.json").read_text())
    assert j["years"] == [2016, 2025] and s.params["start_date"] == "2016-01-01" and s.params["end_date"] == "2025-12-31"
    assert abs(j["lat"] - 37.3) < 1e-6 and j["at"] == "park centre" and j["months"][5]["tmax"] == 26.0 and stats["elevation_m"] == 1500.0
    (tmp_path / "places.json").write_text(json.dumps({"places": [{"name": "Zion Lodge", "lon": -112.9576, "lat": 37.2513, "near": {"n": 739}}]}))
    build_climate(park, tmp_path, session=s, today=date(2026, 9, 6))
    j2 = json.loads((tmp_path / "climate.json").read_text())
    assert j2["at"] == "Zion Lodge" and abs(j2["lat"] - 37.2513) < 1e-6
