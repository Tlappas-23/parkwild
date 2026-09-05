import json

import pytest

from parkwild.contracts import ContractError, check_bbox_normalized, check_conservation, check_lon_lat, check_ms_epoch
from parkwild.decisionlog import log_filter


def test_lon_lat_catches_swapped_pair():
    assert check_lon_lat([{"lon": -110.2, "lat": 44.9}, {"lon": None, "lat": None}]) == 1
    with pytest.raises(ContractError):
        check_lon_lat([{"lon": 44.9, "lat": -110.2}])
    with pytest.raises(ContractError):
        check_lon_lat([{"lon": None, "lat": None}], allow_none=False)


def test_bbox_and_epoch_and_conservation():
    assert check_bbox_normalized([{"bbox_x": 0.1, "bbox_y": 0.2, "bbox_w": 0.3, "bbox_h": 0.4}]) == 1
    with pytest.raises(ContractError):
        check_bbox_normalized([{"bbox_x": 0.9, "bbox_y": 0.2, "bbox_w": 0.3, "bbox_h": 0.4}])
    assert check_ms_epoch([1_700_000_000_000, None]) == 1
    with pytest.raises(ContractError):
        check_ms_epoch([1_700_000_000])          # seconds, not ms
    check_conservation(10, 7, 3)
    with pytest.raises(ContractError):
        check_conservation(10, 7, 2, stage="x")


def test_decision_log_appends_json_lines(tmp_path):
    path = tmp_path / "log.jsonl"
    e1 = log_filter("stage", "rule", 10, 7, path=path, threshold=0.2)
    log_filter("stage", "rule", 7, 7, path=path)
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(lines) == 2 and lines[0]["n_dropped"] == 3 and lines[0]["threshold"] == 0.2 and e1["stage"] == "stage"
