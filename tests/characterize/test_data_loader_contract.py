"""Lock down DataFactory.load dispatch on each registered source_type."""
from astraeus.data.loader import (
    DataFactory,
    DataLoaderStrategy,
    NASAArchiveLoader,
    CSVLoader,
    JSONLoader,
    universal_load_lightcurve,
)
import numpy as np
import pytest


def test_three_strategies_registered():
    assert "api" in DataFactory._strategies
    assert "csv" in DataFactory._strategies
    assert "json" in DataFactory._strategies
    assert isinstance(DataFactory._strategies["api"], NASAArchiveLoader)
    assert isinstance(DataFactory._strategies["csv"], CSVLoader)
    assert isinstance(DataFactory._strategies["json"], JSONLoader)


def test_data_loader_strategy_is_abstract():
    """DataLoaderStrategy cannot be instantiated directly."""
    with pytest.raises(TypeError):
        DataLoaderStrategy()


def test_data_factory_load_unsupported_raises_value_error():
    with pytest.raises(ValueError) as exc_info:
        DataFactory.load("parquet", "/tmp/x")
    assert "parquet" in str(exc_info.value)


def test_data_factory_load_csv_returns_three_tuple(tmp_path):
    """CSV loader returns (time, flux, flux_err) as np.float64 arrays."""
    csv = tmp_path / "test.csv"
    csv.write_text("time,flux,flux_err\n0.0,1.0,0.01\n1.0,0.99,0.01\n")
    t, f, e = DataFactory.load("csv", str(csv))
    assert t.dtype == np.float64
    assert f.dtype == np.float64
    assert e.dtype == np.float64
    assert len(t) == 2


def test_universal_load_lightcurve_delegates_to_factory():
    """The module-level helper must be a thin wrapper around DataFactory.load."""
    import inspect
    src = inspect.getsource(universal_load_lightcurve)
    assert "DataFactory.load" in src
