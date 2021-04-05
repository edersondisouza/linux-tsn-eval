#!/usr/bin/env python3

# Copyright (c) 2021, Intel Corporation
#
# SPDX-License-Identifier: BSD-3-Clause

import argparse

from analysis import Analysis
from datetime import datetime
from latency_profile import IntermediateLatencyComparisonProfile
from metrics import (TotalRxMetric, TotalTxMetric, rx_intermediate_classes,
                     tx_intermediate_classes)
from metrics_comparison import MetricsComparison


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv-dir-1', dest='csv_dir_1',
                        required=True,
                        help='CSV directory with timestamp data to compare')
    parser.add_argument('--csv-dir-1-label', dest='csv_dir_1_label',
                        required=True,
                        help='Label for csv-file-1')
    parser.add_argument('--csv-dir-2', dest='csv_dir_2',
                        required=True,
                        help='CSV directory with timestamp data to compare')
    parser.add_argument('--csv-dir-2-label', dest='csv_dir_2_label',
                        required=True,
                        help='Label for csv-file-2')
    parser.add_argument('-g', dest='comp_graph_dir',
                        default='graph_'
                                f'{datetime.now().strftime("%Y-%m-%d-%H-%M")}',
                        help='Directory where comparison graph will be stored')
    args = parser.parse_args()

    metrics_of_interest = [TotalRxMetric, *rx_intermediate_classes,
                           TotalTxMetric, *tx_intermediate_classes]

    analysis_1 = Analysis(args.csv_dir_1, args.comp_graph_dir)
    analysis_2 = Analysis(args.csv_dir_2, args.comp_graph_dir)

    analysis_1.analyse(metrics_of_interest)
    analysis_2.analyse(metrics_of_interest)

    mc = MetricsComparison((args.csv_dir_1_label,
                            analysis_1.metrics_of([TotalTxMetric])),
                           (args.csv_dir_2_label,
                            analysis_2.metrics_of([TotalTxMetric])),
                           'Total Transmit Comparison', args.comp_graph_dir)
    mc.plot()

    mc = MetricsComparison((args.csv_dir_1_label,
                            analysis_1.metrics_of([TotalRxMetric])),
                           (args.csv_dir_2_label,
                            analysis_2.metrics_of([TotalRxMetric])),
                           'Total Receive Comparison', args.comp_graph_dir)
    mc.plot()

    if (len(analysis_1.metrics_of([*rx_intermediate_classes])) > 0 and
            len(analysis_2.metrics_of([*rx_intermediate_classes])) > 0):
        ilcp = IntermediateLatencyComparisonProfile(
                (args.csv_dir_1_label,
                    analysis_1.metrics_of([*rx_intermediate_classes])),
                (args.csv_dir_2_label,
                    analysis_2.metrics_of([*rx_intermediate_classes])),
                'receive', args.comp_graph_dir)
        ilcp.chart()

    if (len(analysis_1.metrics_of([*tx_intermediate_classes])) > 0 and
            len(analysis_2.metrics_of([*tx_intermediate_classes])) > 0):
        ilcp = IntermediateLatencyComparisonProfile(
                (args.csv_dir_1_label,
                    analysis_1.metrics_of([*tx_intermediate_classes])),
                (args.csv_dir_2_label,
                    analysis_2.metrics_of([*tx_intermediate_classes])),
                'transmit', args.comp_graph_dir)
        ilcp.chart()

    print(f'Results saved at {args.comp_graph_dir}')


if __name__ == "__main__":
    main()
