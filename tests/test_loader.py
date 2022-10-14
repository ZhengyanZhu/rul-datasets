import os
import unittest
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union
from unittest import mock

import numpy as np
import pytest
import torch

from rul_datasets import loader, utils
from tests.templates import LoaderInterfaceTemplate


@dataclass
class DummyLoader(loader.AbstractLoader):
    fd: int
    window_size: int
    max_rul: int
    percent_broken: Optional[float] = None
    percent_fail_runs: Optional[Union[float, List[int]]] = None
    truncate_val: bool = True

    _NUM_TRAIN_RUNS = {1: 100}

    def _default_window_size(self, fd):
        return 15

    def prepare_data(self):
        pass

    def load_split(self, split: str) -> Tuple[List[torch.Tensor], List[torch.Tensor]]:
        pass


class TestAbstractLoader(unittest.TestCase):
    def test_check_compatibility(self):
        this = DummyLoader(1, 30, 125)
        this.check_compatibility(DummyLoader(1, 30, 125))
        self.assertRaises(ValueError, this.check_compatibility, DummyLoader(1, 20, 125))
        self.assertRaises(ValueError, this.check_compatibility, DummyLoader(1, 30, 120))

    def test_get_compatible(self):
        this = DummyLoader(1, 30, 125)
        with self.subTest("get same"):
            other = this.get_compatible()
            this.check_compatibility(other)
            self.assertEqual(this.fd, other.fd)
            self.assertEqual(30, other.window_size)
            self.assertEqual(30, this.window_size)
            self.assertEqual(this.max_rul, other.max_rul)
            self.assertEqual(this.percent_broken, other.percent_broken)
            self.assertEqual(this.percent_fail_runs, other.percent_fail_runs)
            self.assertEqual(this.truncate_val, other.truncate_val)
        with self.subTest("get different"):
            other = this.get_compatible(2, 0.2, 0.8, False)
            this.check_compatibility(other)
            self.assertEqual(2, other.fd)
            self.assertEqual(15, other.window_size)
            self.assertEqual(15, this.window_size)  # original loader is made compatible
            self.assertEqual(this.max_rul, other.max_rul)
            self.assertEqual(0.2, other.percent_broken)
            self.assertEqual(0.8, other.percent_fail_runs)
            self.assertEqual(False, other.truncate_val)

    def test_get_complement(self):
        with self.subTest("float percent_fail_runs"):
            this = DummyLoader(1, 30, 125, percent_fail_runs=0.8)
            other = this.get_complement(0.8, False)
            self.assertListEqual(other.percent_fail_runs, list(range(80, 100)))
            self.assertEqual(0.8, other.percent_broken)
            self.assertEqual(False, other.truncate_val)
        with self.subTest("list percent_fail_runs"):
            this = DummyLoader(1, 30, 125, percent_fail_runs=list(range(80)))
            other = this.get_complement(0.8, False)
            self.assertListEqual(other.percent_fail_runs, list(range(80, 100)))
            self.assertEqual(0.8, other.percent_broken)
            self.assertEqual(False, other.truncate_val)
        with self.subTest("empty complement"):
            this = DummyLoader(1, 30, 125)  # Uses all runs
            other = this.get_complement(0.8, False)
            self.assertFalse(other.percent_fail_runs)  # Complement is empty
            self.assertEqual(0.8, other.percent_broken)
            self.assertEqual(False, other.truncate_val)


@pytest.mark.needs_data
class TestCMAPSSLoader(unittest.TestCase):
    NUM_CHANNELS = len(loader.CmapssLoader._DEFAULT_CHANNELS)

    @classmethod
    def setUpClass(cls):
        for fd in range(1, 5):
            loader.CmapssLoader(fd).prepare_data()

    def test_run_shape_and_dtype(self):
        window_sizes = [30, 20, 30, 15]
        for n, win in enumerate(window_sizes, start=1):
            rul_loader = loader.CmapssLoader(n)
            for split in ["dev", "val", "test"]:
                with self.subTest(fd=n, split=split):
                    self._check_split(rul_loader, split, win)

    def _check_split(self, rul_loader, split, window_size):
        features, targets = rul_loader.load_split(split)
        for run, run_target in zip(features, targets):
            self._assert_run_correct(run, run_target, window_size)

    def _assert_run_correct(self, run, run_target, win):
        self.assertEqual(win, run.shape[2])
        self.assertEqual(self.NUM_CHANNELS, run.shape[1])
        self.assertEqual(len(run), len(run_target))
        self.assertEqual(torch.float32, run.dtype)
        self.assertEqual(torch.float32, run_target.dtype)

    def test_default_window_size(self):
        window_sizes = [30, 20, 30, 15]
        for n, win in enumerate(window_sizes, start=1):
            rul_loader = loader.CmapssLoader(n)
            self.assertEqual(win, rul_loader.window_size)

    def test_override_window_size(self):
        window_size = 40
        for n in range(1, 5):
            dataset = loader.CmapssLoader(n, window_size=window_size)
            for split in ["dev", "val", "test"]:
                with self.subTest(fd=n, split=split):
                    features, targets = dataset.load_split(split)
                    for run in features:
                        self.assertEqual(window_size, run.shape[2])

    def test_default_feature_select(self):
        rul_loader = loader.CmapssLoader(1)
        self.assertListEqual(rul_loader._DEFAULT_CHANNELS, rul_loader.feature_select)

    def test_feature_select(self):
        dataset = loader.CmapssLoader(1, feature_select=[4, 9, 10, 13, 14, 15, 22])
        for split in ["dev", "val", "test"]:
            features, _ = dataset.load_split(split)
            for run in features:
                self.assertEqual(7, run.shape[1])

    def test_percent_fail_runs(self):
        full_dataset = loader.CmapssLoader(fd=1, window_size=30)
        full_dev, full_dev_targets = full_dataset.load_split("dev")
        full_val = full_dataset.load_split("val")[0]
        full_test = full_dataset.load_split("test")[0]

        dataset = loader.CmapssLoader(fd=1, window_size=30, percent_fail_runs=0.8)
        trunc_dev, trunc_dev_targets = dataset.load_split("dev")

        self.assertGreater(len(full_dev), len(trunc_dev))
        self.assertAlmostEqual(0.8, len(trunc_dev) / len(full_dev), delta=0.01)
        self.assertEqual(len(full_val), len(dataset.load_split("val")[0]))
        self.assertEqual(len(full_test), len(dataset.load_split("test")[0]))

        for full_run, trunc_run in zip(full_dev, trunc_dev):
            self.assertEqual(0.0, torch.dist(trunc_run, full_run))
        for full_targets, trunc_targets in zip(full_dev_targets, trunc_dev_targets):
            self.assertEqual(0.0, torch.dist(trunc_targets, full_targets))

    def test_percent_broken(self):
        full_dataset = loader.CmapssLoader(fd=1, window_size=30)
        full_dev, full_dev_targets = full_dataset.load_split("dev")
        full_val = full_dataset.load_split("val")[0]
        full_test = full_dataset.load_split("test")[0]

        dataset = loader.CmapssLoader(fd=1, window_size=30, percent_broken=0.2)
        truncated_dev, truncated_dev_targets = dataset.load_split("dev")

        full_length = sum(len(r) for r in full_dev)
        truncated_length = sum(len(r) for r in truncated_dev)
        self.assertGreater(full_length, truncated_length)
        self.assertAlmostEqual(0.2, truncated_length / full_length, delta=0.01)

        # No failure data in truncated dev data
        self.assertFalse(any(torch.any(r == 1) for r in truncated_dev_targets))

        for full_run, trunc_run in zip(full_dev, truncated_dev):
            trunc_run_length = trunc_run.shape[0]
            self.assertEqual(0.0, torch.dist(trunc_run, full_run[:trunc_run_length]))
        for full_run, trunc_run in zip(full_dev_targets, truncated_dev_targets):
            trunc_run_length = trunc_run.shape[0]
            self.assertEqual(0.0, torch.dist(trunc_run, full_run[:trunc_run_length]))

        # Val dataset_tests not truncated
        for full_run, trunc_run in zip(full_val, dataset.load_split("val")[0]):
            self.assertEqual(len(full_run), len(trunc_run))

        # Test dataset_tests not truncated
        for full_run, trunc_run in zip(full_test, dataset.load_split("test")[0]):
            self.assertEqual(len(full_run), len(trunc_run))

    @mock.patch(
        "rul_datasets.loader.CmapssLoader._truncate_runs",
        wraps=lambda x, y, *args: (x, y),
    )
    def test_val_truncation(self, mock_truncate):
        dataset = loader.CmapssLoader(fd=1, window_size=30)
        with self.subTest(truncate_val=False):
            dataset.load_split("dev")
            mock_truncate.assert_called_once()
            mock_truncate.reset_mock()
            dataset.load_split("val")
            mock_truncate.assert_not_called()

        dataset = loader.CmapssLoader(fd=1, window_size=30, truncate_val=True)
        with self.subTest(truncate_val=True):
            dataset.load_split("dev")
            mock_truncate.assert_called_once()
            mock_truncate.reset_mock()
            dataset.load_split("val")
            mock_truncate.assert_called_once()

    def test_normalization_min_max(self):
        for i in range(1, 5):
            with self.subTest(fd=i):
                full_dataset = loader.CmapssLoader(fd=i, window_size=30)
                full_dev, full_dev_targets = full_dataset.load_split("dev")

                self.assertAlmostEqual(max(torch.max(r).item() for r in full_dev), 1.0)
                self.assertAlmostEqual(min(torch.min(r).item() for r in full_dev), -1.0)

                truncated_dataset = loader.CmapssLoader(
                    fd=i, window_size=30, percent_fail_runs=0.8
                )
                trunc_dev, trunc_dev_targets = truncated_dataset.load_split("dev")
                self.assertLessEqual(max(torch.max(r).item() for r in trunc_dev), 1.0)
                self.assertGreaterEqual(
                    min(torch.min(r).item() for r in trunc_dev), -1.0
                )

                truncated_dataset = loader.CmapssLoader(
                    fd=i, window_size=30, percent_broken=0.2
                )
                trunc_dev, trunc_dev_targets = truncated_dataset.load_split("dev")
                self.assertLessEqual(max(torch.max(r).item() for r in trunc_dev), 1.0)
                self.assertGreaterEqual(
                    min(torch.min(r).item() for r in trunc_dev), -1.0
                )

    def test_truncation_by_index(self):
        full_dataset = loader.CmapssLoader(1)
        full_train, full_train_targets = full_dataset.load_split("dev")
        indices = [50, 60, 70]
        truncated_dataset = loader.CmapssLoader(1, percent_fail_runs=indices)
        trunc_train, trunc_train_targets = truncated_dataset.load_split("dev")

        self.assertEqual(len(indices), len(trunc_train))
        self.assertEqual(len(indices), len(trunc_train_targets))
        for trunc_idx, full_idx in enumerate(indices):
            self.assertEqual(
                0, torch.dist(full_train[full_idx], trunc_train[trunc_idx])
            )
            self.assertEqual(
                0,
                torch.dist(
                    full_train_targets[full_idx], trunc_train_targets[trunc_idx]
                ),
            )


def _raw_csv_exist():
    csv_path = os.path.join(
        loader.FemtoLoader._FEMTO_ROOT,
        loader.FemtoPreparator.SPLIT_FOLDERS["dev"],
        "Bearing1_1",
    )
    csv_exists = os.path.exists(csv_path)

    return csv_exists


@pytest.mark.needs_data
class TestFEMTOLoader(unittest.TestCase):
    NUM_CHANNELS = 2

    def test_run_shape_and_dtype(self):
        window_sizes = [2560, 1500, 1000, 100]
        for win in window_sizes:
            for fd in range(1, 4):
                femto_loader = loader.FemtoLoader(fd, window_size=win)
                for split in ["dev", "test"]:
                    with self.subTest(fd=fd, split=split):
                        self._check_split(femto_loader, split, win)

    def _check_split(self, rul_loader, split, window_size):
        features, targets = rul_loader.load_split(split)
        for run, run_target in zip(features, targets):
            self._assert_run_correct(run, run_target, window_size)

    def _assert_run_correct(self, run, run_target, win):
        self.assertEqual(win, run.shape[2])
        self.assertEqual(self.NUM_CHANNELS, run.shape[1])
        self.assertEqual(len(run), len(run_target))
        self.assertEqual(torch.float32, run.dtype)
        self.assertEqual(torch.float32, run_target.dtype)

    def test_percent_fail_runs(self):
        full_dataset = loader.FemtoLoader(fd=1)
        full_train, full_train_targets = full_dataset.load_split("dev")
        full_test = full_dataset.load_split("test")[0]

        dataset = loader.FemtoLoader(fd=1, percent_fail_runs=0.5)
        trunc_train, trunc_train_targets = dataset.load_split("dev")

        self.assertGreater(len(full_train), len(trunc_train))
        self.assertAlmostEqual(0.5, len(trunc_train) / len(full_train), delta=0.01)
        self.assertEqual(len(full_test), len(dataset.load_split("test")[0]))

        for full_run, trunc_run in zip(full_train, trunc_train):
            self.assertEqual(0.0, torch.dist(trunc_run, full_run))
        for full_targets, trunc_targets in zip(full_train_targets, trunc_train_targets):
            self.assertEqual(0.0, torch.dist(trunc_targets, full_targets))

    def test_percent_broken(self):
        full_dataset = loader.FemtoLoader(fd=1)
        full_train, full_train_targets = full_dataset.load_split("dev")
        full_test = full_dataset.load_split("test")[0]

        dataset = loader.FemtoLoader(fd=1, percent_broken=0.2)
        truncated_train, truncated_train_targets = dataset.load_split("dev")

        full_length = sum(len(r) for r in full_train)
        truncated_length = sum(len(r) for r in truncated_train)
        self.assertGreater(full_length, truncated_length)
        self.assertAlmostEqual(0.2, truncated_length / full_length, delta=0.01)

        # No failure data in truncated train data
        self.assertFalse(any(torch.any(r == 1) for r in truncated_train_targets))

        for full_run, trunc_run in zip(full_train, truncated_train):
            trunc_run_length = trunc_run.shape[0]
            self.assertEqual(0.0, torch.dist(trunc_run, full_run[:trunc_run_length]))
        for full_run, trunc_run in zip(full_train_targets, truncated_train_targets):
            trunc_run_length = trunc_run.shape[0]
            self.assertEqual(0.0, torch.dist(trunc_run, full_run[:trunc_run_length]))

        # Test dataset_tests not truncated
        for full_run, trunc_run in zip(full_test, dataset.load_split("test")[0]):
            self.assertEqual(len(full_run), len(trunc_run))

    @unittest.skip("No val set yet.")
    @mock.patch(
        "rul_datasets.loader.FEMTOLoader._truncate_runs", wraps=lambda x, y: (x, y)
    )
    def test_val_truncation(self, mock_truncate):
        dataset = loader.FemtoLoader(fd=1, window_size=30)
        with self.subTest(truncate_val=False):
            dataset.load_split("dev")
            mock_truncate.assert_called_once()
            mock_truncate.reset_mock()
            dataset.load_split("val")
            mock_truncate.assert_not_called()

        dataset = loader.FemtoLoader(fd=1, window_size=30, truncate_val=True)
        with self.subTest(truncate_val=True):
            dataset.load_split("dev")
            mock_truncate.assert_called_once()
            mock_truncate.reset_mock()
            dataset.load_split("val")
            mock_truncate.assert_called_once()

    def test_standardization(self):
        for i in range(1, 3):
            with self.subTest(fd=i):
                full_dataset = loader.FemtoLoader(fd=i)
                full_train, full_train_targets = full_dataset.load_split("dev")

                self.assertAlmostEqual(
                    0.0, torch.mean(torch.cat(full_train)).item(), delta=0.0001
                )
                self.assertAlmostEqual(
                    1.0, torch.std(torch.cat(full_train)).item(), delta=0.0001
                )

                truncated_dataset = loader.FemtoLoader(fd=i, percent_fail_runs=0.8)
                trunc_train, trunc_train_targets = truncated_dataset.load_split("dev")
                self.assertAlmostEqual(
                    0.0, torch.mean(torch.cat(trunc_train)).item(), delta=0.1
                )
                self.assertAlmostEqual(
                    1.0, torch.std(torch.cat(trunc_train)).item(), delta=0.1
                )

                # percent_broken is supposed to change the std but not the mean
                truncated_dataset = loader.FemtoLoader(fd=i, percent_broken=0.2)
                trunc_train, trunc_train_targets = truncated_dataset.load_split("dev")
                self.assertAlmostEqual(
                    0.0, torch.mean(torch.cat(trunc_train)).item(), delta=0.1
                )

    def test_truncation_by_index(self):
        full_dataset = loader.FemtoLoader(1)
        full_train, full_train_targets = full_dataset.load_split("dev")
        truncated_dataset = loader.FemtoLoader(1, percent_fail_runs=[1])
        trunc_train, trunc_train_targets = truncated_dataset.load_split("dev")

        self.assertEqual(1, len(trunc_train))
        self.assertEqual(1, len(trunc_train_targets))
        self.assertEqual(0, torch.dist(full_train[1], trunc_train[0]))
        self.assertEqual(0, torch.dist(full_train_targets[1], trunc_train_targets[0]))


@pytest.mark.needs_data
class TestFEMTOPreperator:
    NUM_SAMPLES = {
        1: {"dev": 3674, "test": 9047},
        2: {"dev": 1708, "test": 4560},
        3: {"dev": 2152, "test": 352},
    }

    @pytest.mark.skipif(not _raw_csv_exist(), reason="Raw CSV files not found.")
    @pytest.mark.parametrize("fd", [1, 2, 3])
    @pytest.mark.parametrize("split", ["dev", "test"])
    def test_file_discovery(self, fd, split):
        preparator = loader.FemtoPreparator(fd, loader.FemtoLoader._FEMTO_ROOT)
        csv_paths = preparator._get_csv_file_paths(split)
        expected_num_files = self.NUM_SAMPLES[fd][split]
        actual_num_files = len(sum(csv_paths, []))
        assert actual_num_files == expected_num_files

    @pytest.mark.skipif(not _raw_csv_exist(), reason="Raw CSV files not found.")
    def test_loading_one_file(self):
        preparator = loader.FemtoPreparator(1, loader.FemtoLoader._FEMTO_ROOT)
        csv_paths = preparator._get_csv_file_paths("dev")
        features = preparator._load_feature_file(csv_paths[0][0])
        assert isinstance(features, np.ndarray)
        assert features.shape == (preparator.DEFAULT_WINDOW_SIZE, 2)

    @pytest.mark.skip("Takes a lot of time.")
    @pytest.mark.parametrize("fd", [1, 2, 3])
    @pytest.mark.parametrize("split", ["dev", "test"])
    def test_preparation(self, fd, split):
        preparator = loader.FemtoPreparator(fd, loader.FemtoLoader._FEMTO_ROOT)
        preparator.prepare_split(split)
        expected_file_path = preparator._get_run_file_path(split)
        assert os.path.exists(expected_file_path)
        expected_scaler_path = preparator._get_scaler_path()
        assert os.path.exists(expected_scaler_path)

    @pytest.mark.parametrize("fd", [1, 2, 3])
    @pytest.mark.parametrize("split", ["dev", "test"])
    def test_converted_files(self, fd, split):
        preparator = loader.FemtoPreparator(fd, loader.FemtoLoader._FEMTO_ROOT)
        features, targets = preparator.load_runs(split)
        expected_num_time_steps = self.NUM_SAMPLES[fd][split]
        actual_num_target_steps = sum(len(f) for f in features)
        assert actual_num_target_steps == expected_num_time_steps
        actual_num_target_steps = sum(len(t) for t in targets)
        assert actual_num_target_steps == expected_num_time_steps

    @pytest.mark.parametrize("fd", [1, 2, 3])
    def test_scaler(self, fd):
        preparator = loader.FemtoPreparator(fd, loader.FemtoLoader._FEMTO_ROOT)
        scaler = preparator.load_scaler()
        expected_samples = self.NUM_SAMPLES[fd]["dev"] * preparator.DEFAULT_WINDOW_SIZE
        assert 2 == scaler.n_features_in_
        assert expected_samples == scaler.n_samples_seen_


class TestCMAPSSLoaderInterface(unittest.TestCase, LoaderInterfaceTemplate):
    def setUp(self):
        self.loader_type = loader.CmapssLoader


class TestFEMTOLoaderInterface(unittest.TestCase, LoaderInterfaceTemplate):
    def setUp(self):
        self.loader_type = loader.FemtoLoader
