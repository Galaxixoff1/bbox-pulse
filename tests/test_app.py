import os
import json
import time
import pytest
import tempfile
import app as bbox_app

@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)
    data_file = os.path.join(data_dir, "bbox_history.json")
    speed_file = os.path.join(data_dir, "bbox_speed_state.json")
    monkeypatch.setattr(bbox_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(bbox_app, "DATA_FILE", data_file)
    monkeypatch.setattr(bbox_app, "SPEED_FILE", speed_file)
    monkeypatch.setattr(bbox_app, "redis_client", None)  # force JSON fallback for deterministic test
    bbox_app._last_rx = None
    bbox_app._last_tx = None
    bbox_app._last_time = None
    return data_dir

def test_initial_history_accumulation(tmp_data_dir):
    # Initial run: session stats are 192 GB down, 17.4 GB up
    curr_rx = 192 * 1024**3
    curr_tx = int(17.4 * 1024**3)

    history = bbox_app.update_history_with_current(curr_rx, curr_tx)

    # Check that history cumulative bank starts from initial session box values
    assert history['bank_rx'] >= curr_rx
    assert history['bank_tx'] >= curr_tx
    assert history['last_rx'] == curr_rx
    assert history['last_tx'] == curr_tx

def test_subsequent_history_accumulation(tmp_data_dir):
    curr_rx = 100 * 1024**2
    curr_tx = 10 * 1024**2
    bbox_app.update_history_with_current(curr_rx, curr_tx)

    # Add 50 MB
    delta_rx = 50 * 1024**2
    delta_tx = 5 * 1024**2
    history = bbox_app.update_history_with_current(curr_rx + delta_rx, curr_tx + delta_tx)

    assert history['bank_rx'] == curr_rx + delta_rx
    assert history['bank_tx'] == curr_tx + delta_tx

def test_box_reset_handling(tmp_data_dir):
    curr_rx = 100 * 1024**2
    curr_tx = 10 * 1024**2
    bbox_app.update_history_with_current(curr_rx, curr_tx)

    # Box reboots: curr_rx drops to 5 MB
    new_rx = 5 * 1024**2
    new_tx = 1 * 1024**2
    history = bbox_app.update_history_with_current(new_rx, new_tx)

    # bank should accumulate previous session (curr_rx) + new session (new_rx)
    assert history['bank_rx'] == curr_rx + new_rx
    assert history['bank_tx'] == curr_tx + new_tx
    assert history['last_rx'] == new_rx
    assert history['last_tx'] == new_tx

def test_differential_speed_calculation_and_string_bigint(tmp_data_dir, monkeypatch):
    current_time = 1000.0

    def mock_time():
        return current_time

    monkeypatch.setattr(time, "time", mock_time)

    # Initial sample with string BigInt byte inputs
    initial_rx_str = "290847669344"
    initial_tx_str = "10000000000"
    spd_dn, spd_up = bbox_app.update_and_get_speed(initial_rx_str, initial_tx_str)
    # First measurement has no delta -> 0.0
    assert spd_dn == 0.0
    assert spd_up == 0.0

    # Advance time by 1.0 second
    # Add 125,000,000 bytes (1 Gbps = 1,000,000,000 bits/s = 125 MB/s)
    current_time = 1001.0
    next_rx_str = str(290847669344 + 125000000)
    next_tx_str = str(10000000000 + 12500000)  # 100 Mbps = 12.5 MB/s

    spd_dn, spd_up = bbox_app.update_and_get_speed(next_rx_str, next_tx_str)
    # 1 Gbps = 1,000,000 kbps
    assert pytest.approx(spd_dn, 0.01) == 1000000.0
    # 100 Mbps = 100,000 kbps
    assert pytest.approx(spd_up, 0.01) == 100000.0

    # Test human_speed formatting (< 1 Gbps / 1,000,000 kbps -> Mb/s, >= 1 Gbps -> Gb/s)
    assert bbox_app.human_speed(spd_dn) == "1.00 Gb/s"
    assert bbox_app.human_speed(spd_up) == "100.0 Mb/s"
    assert bbox_app.human_speed(951200) == "951.2 Mb/s"
    assert bbox_app.human_speed(0) == "0 Mb/s"


def test_speed_calculation_security_resets(tmp_data_dir, monkeypatch):
    current_time = 2000.0
    monkeypatch.setattr(time, "time", lambda: current_time)

    # Seed baseline
    bbox_app.update_and_get_speed("100000000", "50000000")

    # 1. Box reboot scenario: curr_rx < last_rx
    current_time = 2001.0
    spd_dn, spd_up = bbox_app.update_and_get_speed("5000000", "1000000")
    assert spd_dn == 0.0
    assert spd_up == 0.0

    # 2. Invalid t_diff (t_diff <= 0)
    current_time = 2001.0  # same timestamp
    spd_dn, spd_up = bbox_app.update_and_get_speed("10000000", "2000000")
    assert spd_dn == 0.0
    assert spd_up == 0.0


def test_peak_speed_tracking(tmp_data_dir, monkeypatch):
    current_time = 3000.0
    monkeypatch.setattr(time, "time", lambda: current_time)

    # Baseline
    bbox_app.update_and_get_speed("100000000", "50000000")

    # High speed sample (1 Gbps)
    current_time = 3001.0
    rx1 = str(100000000 + 125000000)
    tx1 = str(50000000 + 12500000)
    bbox_app.update_and_get_speed(rx1, tx1)

    state = bbox_app.load_speed_state()
    assert pytest.approx(state['peak_down'], 0.01) == 1000000.0
    assert pytest.approx(state['peak_up'], 0.01) == 100000.0

    # Lower speed sample should not lower peak
    current_time = 3002.0
    rx2 = str(int(rx1) + 12500000)  # 100 Mbps
    tx2 = str(int(tx1) + 1250000)
    bbox_app.update_and_get_speed(rx2, tx2)

    state_after = bbox_app.load_speed_state()
    assert pytest.approx(state_after['peak_down'], 0.01) == 1000000.0
    assert pytest.approx(state_after['peak_up'], 0.01) == 100000.0
