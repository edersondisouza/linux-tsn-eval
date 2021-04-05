# Copyright (c) 2021, Intel Corporation
#
# SPDX-License-Identifier: BSD-3-Clause

import glob
import os.path
import pandas as pd


class Analysis():
    def __init__(self, csv_dir, results_dir):
        self.file_names = glob.glob(f'{csv_dir}/results-*.csv')
        if len(self.file_names) == 0:
            raise Exception(f'No test CSV results found on dir {csv_dir}')
        self.results_dir = results_dir

    def analyse(self, metrics_of_interest):
        metrics_collection = []
        for file_name in self.file_names:
            dataframe = pd.read_csv(file_name)
            factors = self._factors_from_filename(file_name)
            for metric in metrics_of_interest:
                try:
                    metrics_collection.append(metric(dataframe, factors,
                                              self.results_dir))
                except KeyError:
                    # Silence KeyErrors as they should be result of not
                    # collecting intermediate latency
                    pass

        self.metrics_collection = metrics_collection

    @staticmethod
    def _factors_from_filename(filename):
        filename = os.path.basename(filename)
        payload, trans_int = filename.split('.')[0].split('-')[1:]
        return {'PayloadSize': int(payload),
                'TransmissionInterval': int(trans_int)}

    def metrics_of(self, metric_cls):
        return [m for m in self.metrics_collection if type(m) in metric_cls]
