#!/usr/bin/env python3

# Copyright (c) 2021, Intel Corporation
#
# SPDX-License-Identifier: BSD-3-Clause

import argparse
import os
import sys

from analysis import Analysis
from datetime import datetime
from factors import (PayloadFactor, TxIntervalFactor)
from latency_profile import IntermediateLatencyProfile
from metrics import (E2EMetric, TotalRxMetric, TotalTxMetric,
                     hw_sw_classes, rx_intermediate_classes,
                     tx_intermediate_classes)
from metrics_groups import (HwVsSwLatencyMetrics, RxIntermediateLatencyMetrics,
                            SimpleMetricGroup, TxIntermediateLatencyMetrics)
from tabulate import tabulate


def report_intermediate_stats(name, stats, m_classes, dir_name):
    header = ['PayloadSize', 'TransmissionInterval']
    for m_class in m_classes:
        header.append(f'{m_class.short_name}\nMean')
        header.append(f'{m_class.short_name}\nMax')

    table = []
    for stat in stats:
        table.append([stat[0]['PayloadSize'],
                     fmt_trans_int(stat[0]['TransmissionInterval'])])

        # Go over classes so we can keep table ordered by "layer"
        for m_class in m_classes:
            fs = [s for s in stat[1] if s[0] == m_class.short_name][0]
            table[-1].append(fs[1]['mean'])
            table[-1].append(fs[1]['maximum'])

    with open(f'{dir_name}/latency_stats_per_experiment.txt', 'w') as f:
        f.write(f'{name} Latency Statistics (Per Experiment)\n\n')
        f.write(tabulate(table, header, tablefmt='grid', floatfmt='.3f'))


def fmt_trans_int(ti):
    return ti if isinstance(ti, str) else int(ti / 1000)


def report_intermediate_overall_stats(name, m_classes, stats, total_stats,
                                      dir_name):
    header = ['Metric', 'Mean(us)', 'Stdev(us)', 'Min(us)', 'Max(us)',
              'Range(us)', 'CV']
    table = []

    # Go over classes so we can keep table ordered by "layer"
    for m_class in m_classes:
        s = [s for s in stats if s['metric'] == m_class.short_name][0]
        table.append([s['metric'], s['mean'], s['stdev'],
                     s['minimum'], s['maximum'], s['r'], s['cv']])

    s = total_stats[-1]
    table.append(['Total Latency', s['mean'], s['stdev'], s['minimum'],
                 s['maximum'], s['r'], s['cv']])

    norm_name = name.lower().replace(' ', '_')
    with open(f'{dir_name}/{norm_name}_latency_overall_stats.txt', 'w') as f:
        f.write(f'Overall {name} Latency Statistics\n\n')
        f.write(tabulate(table, header, tablefmt='grid', floatfmt='.3f'))


def report_single_metric_stats(stats, name, dir_name):
    header = ['Payload(bytes)', 'TransmissionInterval(us)', 'Mean(us)',
              'Stdev(us)', 'Min(us)', 'Max(us)', 'Range(us)', 'CV']

    table = []
    for stat in stats:
        # Check MetricGroupAnalysis.stats_per_factor() if curious
        # about [1][0][1]
        s = stat[1][0][1]
        table.append([stat[0]['PayloadSize'],
                     fmt_trans_int(stat[0]['TransmissionInterval'])])
        table[-1].extend([s['mean'], s['stdev'], s['minimum'], s['maximum'],
                         s['r'], s['cv']])

    with open(f'{dir_name}/latency_stats_per_experiment.txt', 'w') as f:
        f.write(f'{name} Latency Statistics (Per Experiment)\n\n')
        f.write(tabulate(table, header, tablefmt='grid', floatfmt='.3f'))


def intermediate_latency_analysis(metrics, name, ilm_cls, total_stats,
                                  dir_name, m_classes, args):
    dir_name = f'{args.graphs_dir}/{dir_name}'
    os.makedirs(dir_name, exist_ok=True)
    ilm = ilm_cls(metrics, dir_name)
    report_intermediate_stats(name, ilm.stats_per_factor(summary=True),
                              m_classes, dir_name)

    if total_stats is not None:
        report_intermediate_overall_stats(name, m_classes, ilm.stats(),
                                          total_stats, dir_name)

    if not args.disable_time_sequence:
        ilm.run_sequences()

    if not args.disable_grouped:
        hist_dir = f'{dir_name}/grouped_histograms'
        PayloadFactor(metrics, hist_dir).histograms()
        TxIntervalFactor(metrics, hist_dir).histograms()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', dest='csv_dir',
                        required=True,
                        help='Directory with CSV data from all test runs')
    parser.add_argument('-s', dest='soft_transmit_time',
                        action='store_true',
                        help='Set SW transmit timestamp as X-axis ticks')
    parser.add_argument('-g', dest='graphs_dir',
                        default='graph_'
                                f'{datetime.now().strftime("%Y-%m-%d-%H-%M")}',
                        help='Directory where results will be stored')
    parser.add_argument('--disable-time-sequence',
                        dest='disable_time_sequence', action='store_true',
                        help='Don\'t create time-sequence graphs')
    parser.add_argument('--disable-grouped', dest='disable_grouped',
                        action='store_true',
                        help='Don\'t create grouped graphs')
    parser.add_argument('--disable-rx', dest='disable_rx',
                        action='store_true',
                        help='Don\'t analyze RX data')
    parser.add_argument('--disable-tx', dest='disable_tx',
                        action='store_true',
                        help='Don\'t analyze TX data')
    parser.add_argument('--disable-end-to-end', dest='disable_end_to_end',
                        action='store_true',
                        help='Don\'t produce end-to-end report')
    parser.add_argument('--disable-hw-vs-sw', dest='disable_hw_vs_sw',
                        action='store_true',
                        help='Don\'t produce HW vs SW report')
    args = parser.parse_args()

    analysis = Analysis(args.csv_dir, args.graphs_dir)

    rx_int_metric_cls = rx_intermediate_classes
    tx_int_metric_cls = tx_intermediate_classes
    rx_metric_cls = [TotalRxMetric, *rx_int_metric_cls]
    tx_metric_cls = [TotalTxMetric, *tx_int_metric_cls]
    e2e_metric_cls = [E2EMetric]
    sw_hw_metric_cls = hw_sw_classes

    metrics_of_interest = []
    if not args.disable_rx:
        metrics_of_interest.extend(rx_metric_cls)

    if not args.disable_tx:
        metrics_of_interest.extend(tx_metric_cls)

    if not args.disable_end_to_end:
        metrics_of_interest.extend(e2e_metric_cls)

    if not args.disable_hw_vs_sw:
        metrics_of_interest.extend(sw_hw_metric_cls)

    if len(metrics_of_interest) == 0:
        print('Nothing to do. Were all analysis disabled?')
        sys.exit(0)

    analysis.analyse(metrics_of_interest)

    # General metrics
    for metric_cls in [TotalRxMetric, TotalTxMetric, E2EMetric]:
        metrics = analysis.metrics_of([metric_cls])
        if len(metrics) == 0:
            continue

        dir_name = f'{args.graphs_dir}/{metric_cls.norm_name()}'

        smg = SimpleMetricGroup(metric_cls.name, metrics, dir_name)
        os.makedirs(dir_name, exist_ok=True)
        report_single_metric_stats(smg.stats_per_factor(summary=True),
                                   metric_cls.name, dir_name)

        if not args.disable_time_sequence:
            [m.run_sequence() for m in metrics]

        if not args.disable_grouped:
            hist_dir = f'{dir_name}/grouped_histograms'
            PayloadFactor(metrics, hist_dir).histograms()
            TxIntervalFactor(metrics, hist_dir).histograms()

    # RX intermediate
    metrics = analysis.metrics_of(rx_int_metric_cls)
    if len(metrics) > 0:
        smg = SimpleMetricGroup(None, analysis.metrics_of([TotalRxMetric]), '')
        intermediate_latency_analysis(metrics, 'Receive',
                                      RxIntermediateLatencyMetrics,
                                      smg.stats(), 'receive_intermediate',
                                      rx_int_metric_cls, args)

    # TX intermediate
    metrics = analysis.metrics_of(tx_int_metric_cls)
    if len(metrics) > 0:
        smg = SimpleMetricGroup(None, analysis.metrics_of([TotalTxMetric]), '')
        intermediate_latency_analysis(metrics, 'Transmit',
                                      TxIntermediateLatencyMetrics,
                                      smg.stats(), 'transmit_intermediate',
                                      tx_int_metric_cls, args)

    # Average of all intermediate
    metrics = analysis.metrics_of([*rx_int_metric_cls, *tx_int_metric_cls])
    if len(metrics) > 0:
        ilp = IntermediateLatencyProfile(metrics, args.graphs_dir)
        ilp.chart()

    # HW vs SW
    metrics = analysis.metrics_of(sw_hw_metric_cls)
    if len(metrics) > 0:
        # Hw vs Sw is, at the end, another intermediate latency
        intermediate_latency_analysis(metrics, 'Hardware vs Software',
                                      HwVsSwLatencyMetrics, None, 'hw_vs_sw',
                                      sw_hw_metric_cls, args)

    print(f'Results saved at {args.graphs_dir}')


if __name__ == "__main__":
    main()
