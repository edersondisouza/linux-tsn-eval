# Copyright (c) 2021, Intel Corporation
#
# SPDX-License-Identifier: BSD-3-Clause

import numpy as np
import pandas as pd
import os

from plots import RunSequencePlot


class MetricAnalysis:
    name = 'Add a proper name!'
    short_name = 'Add a proper short name!'

    @classmethod
    def norm_name(cls):
        return cls.name.lower().replace(' ', '_')

    def __init__(self, dataframe, factors, results_dir):
        self.dataframe = dataframe
        self.factors = factors
        self.results_dir = results_dir
        self.metric = self.calculate_metric()

    def stats(self):
        mean = np.mean(self.metric)
        stdev = np.std(self.metric)
        minimum = np.min(self.metric)
        maximum = np.max(self.metric)
        r = maximum - minimum
        cv = (stdev / mean) * 100
        return {'payload_size': self.factors['PayloadSize'],
                'transmission_interval': self.factors['TransmissionInterval'],
                'mean': mean, 'stdev': stdev, 'minimum': minimum,
                'maximum': maximum, 'r': r, 'cv': cv}

    def run_sequence(self, sw_transmit_time=False):
        transmission_interval_us = int(self.factors["TransmissionInterval"] /
                                       1000)
        payload_size = self.factors["PayloadSize"]
        chart_title = (f'{self.name} Latency ('
                       f'Transmission Interval: {transmission_interval_us} us '
                       f'Payload: {payload_size} bytes '
                       f'Iterations: {len(self.metric)})')
        norm_name = self.norm_name()
        chart_directory = f'{self.results_dir}/{norm_name}/time_sequence'

        os.makedirs(chart_directory, exist_ok=True)

        chart_filename = (f'{chart_directory}/'
                          f'graph_{payload_size}_bytes_'
                          f'{transmission_interval_us}_us.png')

        if sw_transmit_time:
            indices = pd.to_datetime(
                    self.dataframe['SoftwareTransmitTimestamp'])
        else:
            indices = np.arange(len(self.metric))
        rsp = RunSequencePlot((indices, self.metric))
        rsp.plot(chart_title, chart_filename)

    def calculate_metric(self):
        raise NotImplementedError('Must implement calculate_metric()')

    def _simple_metric(self, field_a, field_b, err_msg):
        try:
            return pd.Series(np.int64(self.dataframe[field_a] -
                                      self.dataframe[field_b]) / 1000)
        except KeyError as err:
            raise KeyError(f'{err} not found. {err_msg}')


class E2EMetric(MetricAnalysis):
    name = 'End to End'
    short_name = 'End to End'

    def __init__(self, *args):
        super(E2EMetric, self).__init__(*args)

    def calculate_metric(self):
        return self._simple_metric('SoftwareReceiveTimestamp',
                                   'SoftwareTransmitTimestamp',
                                   'Was any latency collected?')


class TotalRxMetric(MetricAnalysis):
    name = 'Receive'
    short_name = 'Receive'

    def __init__(self, *args):
        super(TotalRxMetric, self).__init__(*args)

    def calculate_metric(self):
        return self._simple_metric('SoftwareReceiveTimestamp',
                                   'HardwareReceiveTimestamp',
                                   'Was receive latency collected?')


class TotalTxMetric(MetricAnalysis):
    name = 'Transmit'
    short_name = 'Transmit'

    def __init__(self, *args):
        super(TotalTxMetric, self).__init__(*args)

    def calculate_metric(self):
        return self._simple_metric('HardwareReceiveTimestamp',
                                   'SoftwareTransmitTimestamp',
                                   'Was transmit latency collected?')


class HwRxMetric(MetricAnalysis):
    name = 'Hardware Receive'
    short_name = 'Hardware'

    def __init__(self, *args):
        super(HwRxMetric, self).__init__(*args)

    def calculate_metric(self):
        try:
            m = pd.Series((self.dataframe['irq_handler_entry'] -
                          self.dataframe['HardwareReceiveTimestamp']) / 1000)
            # Check DriverRxMetric comment about negative RxHardware
            m.where(m > 0, 0, inplace=True)
            return m
        except KeyError as err:
            raise KeyError(f'{err} not found. '
                           'Was listener intermediate latency collected?')


class HwTxMetric(MetricAnalysis):
    name = 'Hardware Transmit'
    short_name = 'Hardware'

    def __init__(self, *args):
        super(HwTxMetric, self).__init__(*args)

    def calculate_metric(self):
        return self._simple_metric('HardwareReceiveTimestamp',
                                   'net_dev_xmit',
                                   'Was talker intermediate data collected?')


class DriverRxMetric(MetricAnalysis):
    name = 'Driver Receive'
    short_name = 'Driver'

    def __init__(self, *args):
        super(DriverRxMetric, self).__init__(*args)

    # When more than one packet is processed for the same IRQ, RxHardware will
    # be negative, since the new packet will be received after the IRQ. Instead
    # of computing RxHardware negative, let's keep it at zero, and make
    # RxDriver time to account for
    # "napi_gro_receive_entry - HardwareReceiveTimestamp", as it's drivers
    # fault (or feature) that IRQs were not used.
    def calculate_metric(self):
        try:
            df = self.dataframe
            m = pd.Series(np.int64(df['napi_gro_receive_entry'] -
                          df['irq_handler_entry']) / 1000)
            hw_m = df['irq_handler_entry'] - df['HardwareReceiveTimestamp']
            m.where(hw_m > 0,
                    np.int64(df['napi_gro_receive_entry'] -
                             df['HardwareReceiveTimestamp']) / 1000,
                    inplace=True)
            return m
        except KeyError as err:
            raise KeyError(f'{err} not found. '
                           'Was listener intermediate latency collected?')


class DriverTxMetric(MetricAnalysis):
    name = 'Driver Transmit'
    short_name = 'Driver'

    def __init__(self, *args):
        super(DriverTxMetric, self).__init__(*args)

    def calculate_metric(self):
        return self._simple_metric('net_dev_xmit',
                                   'net_dev_start_xmit',
                                   'Was talker intermediate data collected?')


class NetCoreRxMetric(MetricAnalysis):
    name = 'Net-Core Receive'
    short_name = 'Net-Core'

    def __init__(self, *args):
        super(NetCoreRxMetric, self).__init__(*args)

    def calculate_metric(self):
        return self._simple_metric('netif_receive_skb',
                                   'napi_gro_receive_entry',
                                   'Was listener intermediate data collected?')


class NetCoreTxMetric(MetricAnalysis):
    name = 'Net-Core Transmit'
    short_name = 'Net-Core'

    def __init__(self, *args):
        super(NetCoreTxMetric, self).__init__(*args)

    def calculate_metric(self):
        return self._simple_metric('net_dev_start_xmit',
                                   'net_dev_queue',
                                   'Was talker intermediate data collected?')


class VLANTxMetric(MetricAnalysis):
    name = 'VLAN Transmit'
    short_name = 'VLAN'

    def __init__(self, *args):
        super(VLANTxMetric, self).__init__(*args)

    def calculate_metric(self):
        return self._simple_metric('net_dev_queue',
                                   'net_dev_queue_vlan',
                                   'Was talker intermediate data collected?')


class SocketRxMetric(MetricAnalysis):
    name = 'Socket Receive'
    short_name = 'Socket'

    def __init__(self, *args):
        super(SocketRxMetric, self).__init__(*args)

    def calculate_metric(self):
        return self._simple_metric('sys_exit_recvmsg',
                                   'netif_receive_skb',
                                   'Was listener intermediate data collected?')


class SocketTxMetric(MetricAnalysis):
    name = 'Socket Transmit'
    short_name = 'Socket'

    def __init__(self, *args):
        super(SocketTxMetric, self).__init__(*args)

    def calculate_metric(self):
        return self._simple_metric('net_dev_queue_vlan',
                                   'sys_enter_sendto',
                                   'Was talker intermediate data collected?')


class ContextSwitchRxMetric(MetricAnalysis):
    name = 'Context Switch Receive'
    short_name = 'Context Switch'

    def __init__(self, *args):
        super(ContextSwitchRxMetric, self).__init__(*args)

    def calculate_metric(self):
        return self._simple_metric('SoftwareReceiveTimestamp',
                                   'sys_exit_recvmsg',
                                   'Was listener intermediate data collected?')


class ContextSwitchTxMetric(MetricAnalysis):
    name = 'Context Switch Transmit'
    short_name = 'Context Switch'

    def __init__(self, *args):
        super(ContextSwitchTxMetric, self).__init__(*args)

    def calculate_metric(self):
        return self._simple_metric('sys_enter_sendto',
                                   'SoftwareTransmitTimestamp',
                                   'Was talker intermediate data collected?')


class TotalHwMetric(MetricAnalysis):
    name = 'Total Hardware'
    short_name = 'Hardware'

    def __init__(self, *args):
        super(TotalHwMetric, self).__init__(*args)

    def calculate_metric(self):
        # HW rx is a bit more complicated, let's use it's metric class
        rx_hw = HwRxMetric(self.dataframe, self.results_dir, self.factors)
        try:
            m = np.int64(self.dataframe['HardwareReceiveTimestamp'] -
                         self.dataframe['net_dev_xmit']) / 1000
            return rx_hw.metric + m
        except KeyError as err:
            raise KeyError(f'{err} not found. '
                           'Was talker intermediate latency collected?')


class TotalSwMetric(MetricAnalysis):
    name = 'Total Software'
    short_name = 'Software'

    def __init__(self, *args):
        super(TotalSwMetric, self).__init__(*args)

    def calculate_metric(self):
        # Driver rx is a bit more complicated, let's use it's metric class
        rx_driver = DriverRxMetric(self.dataframe, self.results_dir,
                                   self.factors)
        try:
            m = np.int64(self.dataframe['net_dev_xmit'] -
                         self.dataframe['SoftwareTransmitTimestamp'] +
                         self.dataframe['SoftwareReceiveTimestamp'] -
                         self.dataframe['napi_gro_receive_entry']) / 1000
            return rx_driver.metric + m
        except KeyError as err:
            raise KeyError(f'{err} not found. '
                           'Was talker intermediate latency collected?')


# Convenience lists of metric classes
rx_intermediate_classes = [HwRxMetric, DriverRxMetric, NetCoreRxMetric,
                           SocketRxMetric, ContextSwitchRxMetric]
tx_intermediate_classes = [HwTxMetric, DriverTxMetric, NetCoreTxMetric,
                           VLANTxMetric, SocketTxMetric,
                           ContextSwitchTxMetric]
hw_sw_classes = [TotalHwMetric, TotalSwMetric]
