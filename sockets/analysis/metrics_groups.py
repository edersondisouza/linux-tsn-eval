# Copyright (c) 2021, Intel Corporation
#
# SPDX-License-Identifier: BSD-3-Clause

import numpy as np
import pandas as pd
import os

from metrics import (HwRxMetric, hw_sw_classes, rx_intermediate_classes,
                     tx_intermediate_classes)
from plots import RunSequenceGroupPlot


# Perform several analysis of groups of metrics, generating grouped scatter
# plots, overall stats and stats grouped by factor.
class MetricGroupAnalysis():
    name = 'Add a proper name!'

    def __init__(self, metrics, results_dir):
        self.metrics = metrics
        self.results_dir = results_dir
        self.metrics_types = sorted({type(metric) for metric in self.metrics},
                                    key=lambda mt: mt.name)
        # Gets a list of unique factors
        self.factors_list = [metric.factors for metric in self.metrics]
        self.factors_list = [dict(f)
                             for f in set(tuple(factor.items())
                                          for factor in self.factors_list)]
        self.factors_list.sort(key=lambda f:
                               (f['PayloadSize'], f['TransmissionInterval']))

    # Returns a list of dictionaries containing the stats for each metric, and
    # a special key 'metric', which contains the metric short name.
    # If summary is enabled, a final item is added to main list, where 'metric'
    # value is 'Total'.
    def stats(self, summary=False):
        stats = []
        for metric_type in self.metrics_types:
            all_values = pd.concat([metric.metric
                                    for metric in self.metrics
                                    if isinstance(metric, metric_type)])
            mean = np.mean(all_values)
            stdev = np.std(all_values)
            minimum = np.min(all_values)
            maximum = np.max(all_values)
            r = maximum - minimum
            cv = (stdev / mean) * 100
            stats.append({'metric': metric_type.short_name, 'mean': mean,
                          'stdev': stdev, 'minimum': minimum,
                          'maximum': maximum, 'r': r, 'cv': cv})

        if summary:
            all_values = pd.concat([metric.metric
                                    for metric in self.metrics])
            mean = np.mean(all_values)
            stdev = np.std(all_values)
            minimum = np.min(all_values)
            maximum = np.max(all_values)
            r = maximum - minimum
            cv = (stdev / mean) * 100
            stats.append({'metric': 'Total', 'mean': mean,
                          'stdev': stdev, 'minimum': minimum,
                          'maximum': maximum, 'r': r, 'cv': cv})

        return stats

    # Returns a list of pairs (A, B), where A is a dictionary with
    # 'PayloadSize' and 'TransmissionInterval' as keys, and B is a list of
    # pairs (C, D), where C is the short name of the metric, and D is
    # a dictionary with the stats of the metric. If summary is enabled,
    # a final item is added to main list, where PayloadSize and
    # TransmissionInterval values are 'ALL', and list of summary for each
    # metric.
    def stats_per_factor(self, summary=False):
        stats = []
        for factors in self.factors_list:
            factor_stats = []
            metrics = [metric
                       for metric in self.metrics
                       if metric.factors == factors]
            metrics.sort(key=lambda m: m.name)

            for metric in metrics:
                factor_stats.append((metric.short_name, metric.stats()))

            stats.append((factors, factor_stats))

        if summary:
            factor_stats = []
            stats_per_type = self.stats()  # TODO maybe cache this?
            for spt in stats_per_type:
                factor_stats.append((spt['metric'], spt))

            stats.append(({'PayloadSize': 'ALL',
                         'TransmissionInterval': 'ALL'}, factor_stats))

        return stats

    def _plot(self, data_list, title, filename):
        rsp = RunSequenceGroupPlot(data_list)
        rsp.plot(title, filename)

    def _run_sequence(self, metrics, title, filename, sw_transmit_time):
        data_list = []
        for metric in metrics:
            if sw_transmit_time:
                indices = pd.to_datetime(
                        self.dataframe['SoftwareTransmitTimestamp'])
            else:
                indices = np.arange(len(metric.metric))

            data_list.append((metric.short_name, indices, metric.metric))

        self._plot(data_list, title, filename)

    def run_sequences(self, sw_transmit_time=False):
        # Get dir ready
        charts_directory = f'{self.results_dir}/time_sequence'
        os.makedirs(charts_directory, exist_ok=True)

        for factors in self.factors_list:
            transmission_interval_us = int(
                factors["TransmissionInterval"] / 1000)
            payload_size = factors["PayloadSize"]
            filename = (f'{charts_directory}/'
                        f'graph_{payload_size}_bytes_'
                        f'{transmission_interval_us}_us.png')

            metrics = [metric
                       for metric in self.metrics
                       if metric.factors == factors]

            title = (f'{self.name} Latency ('
                     f'Transmission Interval: {transmission_interval_us} us '
                     f'Payload: {payload_size} bytes '
                     f'Iterations: {len(metrics[0].metric)})')

            self._run_sequence(metrics, title, filename, sw_transmit_time)


class RxIntermediateLatencyMetrics(MetricGroupAnalysis):
    name = 'Receive Intermediate'

    def __init__(self, *args):
        super(RxIntermediateLatencyMetrics, self).__init__(*args)
        self._validate_metrics()

    def _validate_metrics(self):
        valid_rx_metrics = {*rx_intermediate_classes}
        if not valid_rx_metrics.issuperset(self.metrics_types):
            diff = self.metrics_types - valid_rx_metrics
            raise Exception(f'Invalid metric(s) for Rx Latency: {diff}')

    def _plot(self, data_list, title, filename):
        rsp = RunSequenceGroupPlot(data_list)
        for data in data_list:
            if data[0] == HwRxMetric.short_name:
                rsp.colour_masks[data[0]] = [
                        {'mask': data[2] == 0, 'colour': 'C3'},
                        {'mask': data[2] != 0, 'colour': 'C0'}
                ]

        rsp.plot(title, filename)


class TxIntermediateLatencyMetrics(MetricGroupAnalysis):
    name = 'Transmit Intermediate'

    def __init__(self, *args):
        super(TxIntermediateLatencyMetrics, self).__init__(*args)
        self._validate_metrics()

    def _validate_metrics(self):
        valid_tx_metrics = {*tx_intermediate_classes}
        if not valid_tx_metrics.issuperset(self.metrics_types):
            diff = self.metrics_types - valid_tx_metrics
            raise Exception(f'Invalid metric(s) for Tx Latency: {diff}')


class HwVsSwLatencyMetrics(MetricGroupAnalysis):
    name = 'Hardware vs Software'

    def __init__(self, *args):
        super(HwVsSwLatencyMetrics, self).__init__(*args)
        self._validate_metrics()

    def _validate_metrics(self):
        valid_hw_vs_sw_metrics = {*hw_sw_classes}
        if not valid_hw_vs_sw_metrics.issuperset(self.metrics_types):
            diff = self.metrics_types - valid_hw_vs_sw_metrics
            raise Exception(f'Invalid metric(s) for Hw vs Sw Latency: {diff}')


# Convenience class to group a single metric. Useful to get stats summary
# for the metric.
class SimpleMetricGroup(MetricGroupAnalysis):
    def __init__(self, name, *args):
        super(SimpleMetricGroup, self).__init__(*args)
        self.name = name
