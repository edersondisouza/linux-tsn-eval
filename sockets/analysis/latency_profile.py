# Copyright (c) 2021, Intel Corporation
#
# SPDX-License-Identifier: BSD-3-Clause

import numpy as np
import pandas as pd
import os

from metrics import (rx_intermediate_classes, tx_intermediate_classes)
from plots import StackedBarChart


# Generates a stacked bar chart comparing sets of intermediate latencies
# (where intermediate latencies are any latencies that can be viewed as a
# breakdown of a bigger latency).
class LatencyProfile:
    # `metrics_sets` is list of pairs (A, B), where A is the name of the
    # metric_set (such as 'Machine A') and B is list of metrics.
    # `metrics_types_sets` is a list of pairs (C, D), where C is the name
    # of the metric_type_set (such as 'Transmit') and D is a list of Metric
    # classes (such as all Transmit intermediate metrics).
    def __init__(self, metric_sets, metrics_types_sets, results_dir):
        self.metric_sets = metric_sets
        self.metrics_types_sets = metrics_types_sets
        self.results_dir = results_dir
        self.averages = []

    def _process_datasets_metrics(self):
        # Will generate datasets x intermediate_metrics averages
        for metric_set in self.metric_sets:
            metric_set_name = metric_set[0]
            metric_set_metrics = metric_set[1]

            for metric_type_set in self.metrics_types_sets:
                metric_type_set_name = metric_type_set[0]
                metric_type_set_types = metric_type_set[1]

                self.averages.append(self._metric_avg(metric_set_name,
                                                      metric_set_metrics,
                                                      metric_type_set_name,
                                                      metric_type_set_types))

    def _metric_avg(self, metric_set_name, metric_set_metrics,
                    metric_type_set_name, metric_type_set_types):
        avgs = []
        name = f'{metric_set_name}\n{metric_type_set_name}'
        relevant_types = [metric_type
                          for metric_type in metric_type_set_types]
        relevant_metrics = [metric
                            for metric in metric_set_metrics
                            if type(metric) in relevant_types]

        if len(relevant_metrics) > 0:
            for metric_type in metric_type_set_types:
                avg = np.mean(pd.concat([metric.metric
                              for metric in relevant_metrics
                              if isinstance(metric, metric_type)]))
                avgs.append((metric_type.short_name, avg))

        return (name, avgs)

    def _plot(self):
        sbcc = StackedBarChart()
        for avg in self.averages:
            if len(avg[1]) > 0:
                sbcc.add_bar(*avg)
        return sbcc

    def chart(self):
        self._process_datasets_metrics()
        sbcc = self._plot()
        self._finish_chart(sbcc)

    def _finish_chart(self, sbcc):
        raise NotImplementedError('Must implement _finish_chart()')


# Generates a stacked bar chart comparing Receive and Transmit intermediate
# metrics. Usually will be used to get the average intermediate (Transmit and
# Receive) latencies from the same experiment.
class IntermediateLatencyProfile(LatencyProfile):
    # `metrics` is a list of Receive or Transmit intermediate metrics.
    def __init__(self, metrics, results_dir):
        metrics = [('', metrics)]
        metric_types = [('Transmit', tx_intermediate_classes),
                        ('Receive', rx_intermediate_classes)]
        super(IntermediateLatencyProfile, self).__init__(metrics,
                                                         metric_types,
                                                         results_dir)

    def _finish_chart(self, sbcc):
        filename = f'{self.results_dir}/avg-intermediate-latency-bar-chart.png'
        sbcc.plot('Average Intermediate Latency Chart', filename)


# Generates a stacked bar chart comparing two sets of intermediate metrics.
# Each set can be composed of both Transmit and Receive intermediate latency,
# and each set is usually from a different experiment. If there is both
# Transmit and Receive metrics on each set, four bars will be generated. If
# only one type of metric is present, just two bars will be generated.
class IntermediateLatencyComparisonProfile(IntermediateLatencyProfile):
    # `metrics_a` and `metrics_b` are pairs (A, B) where A is the name of
    # the metrics (such as 'Machine A') and B is a list of Transmit or Receive
    # metrics (or both).
    # `name` is a prefix to be added to the generated chart filename, that will
    # be something like {name}-avg-intermediate-comp-latency-bar-chart.png
    def __init__(self, metrics_a, metrics_b, name, results_dir):
        super(IntermediateLatencyComparisonProfile,
              self).__init__(None, results_dir)
        self.metric_sets = [metrics_a, metrics_b]
        self.name = name

    def _finish_chart(self, sbcc):
        os.makedirs(self.results_dir, exist_ok=True)

        filename = (f'{self.results_dir}/'
                    f'{self.name}-avg-intermediate-comp-latency-bar-chart.png')
        if len([avg for avg in self.averages if len(avg[1]) > 0]) > 2:
            sbcc.bar_distance = 1
        sbcc.plot('Average Intermediate Latency Comparison Chart', filename)
