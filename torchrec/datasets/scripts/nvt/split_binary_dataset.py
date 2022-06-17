#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

import argparse
import json

import math
import time
import os
from typing import Sequence

import numpy as np

from utils.criteo_constant import DEFAULT_CAT_NAMES, DEFAULT_INT_NAMES, NUM_EMBEDDINGS_PER_FEATURE

from tqdm import tqdm


def get_categorical_feature_type(size: int):
    """This function works both when max value and cardinality is passed.
    Consistency by the user is required"""
    types = (np.int8, np.int16, np.int32)

    for numpy_type in types:
        if size < np.iinfo(numpy_type).max:
            return numpy_type

    raise RuntimeError(
        f"Categorical feature of size {size} is too big for defined types"
    )


def split_binary_file(
    binary_file_path: str,
    output_dir: str,
    categorical_feature_sizes: Sequence[int],
    batch_size: int,
    source_data_type: str = "int32",
):
    record_width = (
        1 + len(DEFAULT_INT_NAMES) + len(categorical_feature_sizes)
    )  # label + numerical + categorical
    bytes_per_feature = np.__dict__[source_data_type]().nbytes
    bytes_per_entry = record_width * bytes_per_feature

    total_size = os.path.getsize(binary_file_path)
    batches_num = int(math.ceil((total_size // bytes_per_entry) / batch_size))

    cat_feature_types = [
        get_categorical_feature_type(cat_size) for cat_size in categorical_feature_sizes
    ]

    file_streams = []
    try:
        input_data_f = open(binary_file_path, "rb")
        file_streams.append(input_data_f)

        numerical_f = open(os.path.join(output_dir, "numerical.bin"), "wb+")
        file_streams.append(numerical_f)

        label_f = open(os.path.join(output_dir, "label.bin"), "wb+")
        file_streams.append(label_f)

        categorical_fs = []
        for i in range(len(categorical_feature_sizes)):
            fs = open(os.path.join(output_dir, f"cat_{i}.bin"), "wb+")
            categorical_fs.append(fs)
            file_streams.append(fs)

        for _ in tqdm(range(batches_num)):
            raw_data = np.frombuffer(
                input_data_f.read(bytes_per_entry * batch_size), dtype=np.int32
            )
            batch_data = raw_data.reshape(-1, record_width)

            numerical_features = batch_data[:, 1 : 1 + len(DEFAULT_INT_NAMES)].view(
                dtype=np.float32
            )
            numerical_f.write(numerical_features.astype(np.float16).tobytes())

            label = batch_data[:, 0]
            label_f.write(label.astype(np.bool).tobytes())

            cat_offset = len(DEFAULT_INT_NAMES) + 1
            for cat_idx, cat_feature_type in enumerate(cat_feature_types):
                cat_data = batch_data[
                    :, (cat_idx + cat_offset) : (cat_idx + cat_offset + 1)
                ].astype(cat_feature_type)
                categorical_fs[cat_idx].write(cat_data.tobytes())
    finally:
        for stream in file_streams:
            stream.close()


def split_dataset(dataset_dir: str, output_dir: str, batch_size: int):
    train_file = os.path.join(dataset_dir, "train_data.bin")
    test_file = os.path.join(dataset_dir, "test_data.bin")
    val_file = os.path.join(dataset_dir, "validation_data.bin")

    target_train = os.path.join(output_dir, "train")
    target_test = os.path.join(output_dir, "test")
    target_val = os.path.join(output_dir, "validation")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(target_train, exist_ok=True)
    os.makedirs(target_test, exist_ok=True)
    os.makedirs(target_val, exist_ok=True)

    split_binary_file(
        test_file,
        target_test,
        NUM_EMBEDDINGS_PER_FEATURE,
        batch_size,
    )
    split_binary_file(
        train_file,
        target_train,
        NUM_EMBEDDINGS_PER_FEATURE,
        batch_size,
    )
    split_binary_file(val_file, target_val, NUM_EMBEDDINGS_PER_FEATURE, batch_size)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_path", type=str, required=True)
    parser.add_argument("--output_path", type=str, required=True)
    parser.add_argument("--batch_size", type=int, required=True)
    args = parser.parse_args()

    start_time = time.time()

    split_dataset(
        dataset_dir=args.input_path,
        output_dir=args.output_path,
        batch_size=args.batch_size,
    )
    print(f"Processing took {time.time()-start_time:.2f} sec")
