# Copyright (c) 2021, Intel Corporation
#
# SPDX-License-Identifier: BSD-3-Clause

import numpy as np
import pandas as pd
import os

from plots import HistogramGroupPlot


class FactorAnalysis:
    name = 'Add a proper name!'

    def __init__(self, metrics, results_dir):
        self.metrics = metrics
        self.results_dir = results_dir
        self.factor = ''

    def _factor_value_label(self, factor_value):
        raise NotImplementedError('Must implement _factor_value_label()')

    def __histogram(self, metrics):
        all_values = pd.concat([metric.metric for metric in metrics])
        max_latency = np.max(all_values)
        min_latency = np.min(all_values)

        iterations = max([len(metric.metric) for metric in metrics])
        factor_values = {metric.factors[self.factor] for metric in metrics}
        hp = HistogramGroupPlot(len(factor_values), min_latency, max_latency,
                                iterations)
        for fv in sorted(factor_values):
            values = pd.concat([metric.metric for metric in metrics
                               if metric.factors[self.factor] == fv])
            mean = np.mean(values)
            stdev = np.std(values)
            data_hist, edges = np.histogram(values, bins='sqrt')
            hp.add_histogram(data_hist, edges, mean, stdev,
                             self._factor_value_label(fv))

        os.makedirs(self.results_dir, exist_ok=True)

        norm_name = self.name.lower().replace(' ', '_')
        metric_norm_name = metrics[0].name.lower().replace(' ', '_')
        filename = (f'{self.results_dir}/'
                    f'vary_{norm_name}_for_{metric_norm_name}.png')
        title = f'Vary {self.name} for {metrics[0].name} Latency'
        hp.plot(title, filename)

    def histograms(self):
        # Group all our metrics by their type, so they can be properly
        # compared against our factor
        metrics_types = {type(metric) for metric in self.metrics}
        for metric_type in metrics_types:
            metrics = ([metric for metric in self.metrics
                       if isinstance(metric, metric_type)])
            self.__histogram(metrics)


class PayloadFactor(FactorAnalysis):
    name = 'Payload Size'

    def __init__(self, *args):
        super(PayloadFactor, self).__init__(*args)
        self.factor = 'PayloadSize'

    def _factor_value_label(self, factor_value):
        return f'{factor_value} bytes'


class TxIntervalFactor(FactorAnalysis):
    name = 'Transmission Interval'

    def __init__(self, *args):
        super(TxIntervalFactor, self).__init__(*args)
        self.factor = 'TransmissionInterval'

    def _factor_value_label(self, factor_value):
        return f'{int(factor_value/1000)} us'
