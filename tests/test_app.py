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

def test_speed_calculation_and_holding(tmp_data_dir):
    # Initial call sets baseline
    spd_dn, spd_up = bbox_app.update_and_get_speed(1000000, 500000)
    assert spd_dn == 0.0
    assert spd_up == 0.0

    # Wait 1s and download 1MB (8,000,000 bits)
    time.sleep(1.0)
    spd_dn, spd_up = bbox_app.update_and_get_speed(2000000, 1000000)
    assert spd_dn > 0.0
    assert spd_up > 0.0

    recorded_speed_dn = spd_dn

    # Quick subsequent call with 0 delta (e.g. within 1 second) should hold previous non-zero speed
    spd_dn_hold, spd_up_hold = bbox_app.update_and_get_speed(2000000, 1000000)
    assert spd_dn_hold == recorded_speed_dn

def test_peak_speed_tracking(tmp_data_dir):
    # Initialize speed baseline
    bbox_app.update_and_get_speed(1000000, 500000)

    time.sleep(0.6)
    spd_dn1, spd_up1 = bbox_app.update_and_get_speed(5000000, 2000000)

    state = bbox_app.load_speed_state()
    assert state['peak_down'] == spd_dn1
    assert state['peak_up'] == spd_up1

    # Lower speed should not decrease recorded peak speed
    time.sleep(0.6)
    spd_dn2, spd_up2 = bbox_app.update_and_get_speed(5100000, 2050000)
    assert spd_dn2 < spd_dn1

    state_after = bbox_app.load_speed_state()
    assert state_after['peak_down'] == spd_dn1
    assert state_after['peak_up'] == spd_up1
