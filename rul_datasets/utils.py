import os
from typing import List, Optional, Callable

import numpy as np


def get_csv_files_in_path(path: str, condition: Optional[Callable] = None) -> List[str]:
    if condition is None:
        feature_files = [f for f in os.listdir(path)]
    else:
        feature_files = [f for f in os.listdir(path) if condition(f)]
    feature_files = sorted(os.path.join(path, f) for f in feature_files)

    return feature_files


def get_targets_from_file_paths(
    file_paths: List[List[str]], timestep_from_file_path: Callable
) -> List[np.ndarray]:
    """
    Create the RUL targets based on the file paths of the feature files.

    The function extracts the feature file path from each path. The supplied
    conversion function extracts the time step from it. Afterwards the RUL is
    calculated by subtracting each time step from the maximum time step plus 1.

    Args:
        file_paths: list of runs represented as lists of feature file paths
        timestep_from_file_path: Function to convert a feature file path to a time step

    Returns:
        A list of RUL target arrays for each run

    """
    targets = []
    for run_files in file_paths:
        run_targets = np.empty(len(run_files))
        for i, file_path in enumerate(run_files):
            run_targets[i] = timestep_from_file_path(file_path)
        run_targets = np.max(run_targets) - run_targets + 1
        targets.append(run_targets)

    return targets