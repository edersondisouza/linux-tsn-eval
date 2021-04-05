# Copyright (c) 2021, Intel Corporation
#
# SPDX-License-Identifier: BSD-3-Clause

import pandas as pd
import os

from plots import BiHistogram


# Generates a bihistogram comparing two sets of metrics.
class MetricsComparison():
    # `metrics_a` and `metrics_b` should be pairs (A, B), where A is the name
    # of the sets of metric (will appear as Y legend on bihistogram) and B is
    # a list of metrics (such as a list of TotalRxMetric).
    # `name` is the name of the comparison, will appear on the bihistogram
    # title
    def __init__(self, metrics_a, metrics_b, name, results_dir):
        self.metrics_a = metrics_a
        self.metrics_b = metrics_b
        self.results_dir = results_dir
        self.name = name

    def plot(self):
        values_a = pd.concat([metric.metric for metric in self.metrics_a[1]])
        values_b = pd.concat([metric.metric for metric in self.metrics_b[1]])
        bh = BiHistogram((self.metrics_a[0], values_a),
                         (self.metrics_b[0], values_b))

        os.makedirs(self.results_dir, exist_ok=True)

        norm_name = self.name.lower().replace(' ', '_')
        filename = f'{self.results_dir}/{norm_name}-bi-hist.png'
        bh.plot(self.name, filename)
