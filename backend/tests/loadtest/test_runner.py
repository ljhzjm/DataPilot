from app.loadtest.runner import _percentile


def test_percentile_handles_empty_and_ordered_values() -> None:
    assert _percentile([], 0.95) == 0
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert _percentile(values, 0.50) == 3.0
    assert _percentile(values, 0.95) == 5.0
