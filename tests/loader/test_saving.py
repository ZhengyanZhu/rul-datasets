import os.path
from pathlib import Path

import numpy as np
import numpy.testing as npt
import pytest

from rul_datasets.loader import saving


@pytest.mark.parametrize("file_name", ["run", "run.npy", "run.foo"])
def test_save(tmp_path, file_name):
    features = np.empty((10, 2, 5))
    targets = np.empty((10,))
    save_path = os.path.join(tmp_path, file_name)
    saving.save(save_path, features, targets)

    exp_save_path = save_path.replace(".npy", "")
    loaded_features = np.load(exp_save_path + "_features.npy")
    loaded_targets = np.load(exp_save_path + "_targets.npy")
    npt.assert_equal(loaded_features, features)
    npt.assert_equal(loaded_targets, targets)


@pytest.mark.parametrize("file_name", ["run", "run.npy", "run.foo"])
def test_load(tmp_path, file_name):
    features = np.empty((10, 2, 5))
    targets = np.empty((10,))
    exp_file_name = file_name.replace(".npy", "")
    np.save(os.path.join(tmp_path, f"{exp_file_name}_features.npy"), features)
    np.save(os.path.join(tmp_path, f"{exp_file_name}_targets.npy"), targets)

    save_path = os.path.join(tmp_path, file_name)
    loaded_features, loaded_targets = saving.load(save_path)
    npt.assert_equal(loaded_features, features)
    npt.assert_equal(loaded_targets, targets)


@pytest.mark.parametrize("file_name", ["run", "run.npy"])
def test_exists(tmp_path, file_name):
    save_path = os.path.join(tmp_path, file_name)
    assert not saving.exists(save_path)

    Path(os.path.join(tmp_path, "run_features.npy")).touch()
    assert not saving.exists(save_path)

    Path(os.path.join(tmp_path, "run_targets.npy")).touch()
    assert saving.exists(save_path)
