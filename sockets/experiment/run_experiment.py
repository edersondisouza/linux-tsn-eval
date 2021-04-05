#!/usr/bin/env python3

# Copyright (c) 2021, Intel Corporation
#
# SPDX-License-Identifier: BSD-3-Clause

import argparse
import experiment
import json
import os
import shutil
import sys
from datetime import datetime
from util import util

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', dest='config_file',
                        default='tsn_setup.json',
                        help='Experiment configuration file')
    parser.add_argument('-i', dest='interface_name',
                        help='Interface to use for transmission.')
    parser.add_argument('-d', dest='dest_addr',
                        help='Destination MAC Address')
    parser.add_argument('-r', dest='results_dir',
                        default='results_'
                                f'{datetime.now().strftime("%Y-%m-%d-%H-%M")}',
                        help='Directory to save collected data.')
    parser.add_argument('-R', dest='role',
                        choices=['talker', 'listener'],
                        help='Choose role: \'talker\' or \'listener\'')
    parser.add_argument('-I', dest='intermediate_latency',
                        action='store_true',
                        help='Capture intermediate latency ')
    parser.add_argument('-S', dest='run_stress',
                        action='store_true',
                        help='Run stress-ng along with the tsn-listener')
    parser.add_argument('--collect-system-log', dest='enable_log',
                        action='store_true',
                        help='Collect system logs during the run')
    parser.add_argument('--keep-perf-data', dest='keep_perf_data',
                        action='store_true',
                        help='Keep perf.data files collected on intermediate '
                             'latency collection')
    parser.add_argument('--isolate-core', dest='isol_core',
                        help='Specify a core to isolate talker/listener')
    parser.add_argument('--enable-network-interference', dest='network_interf',
                        choices=['yes', 'no'],
                        help='Run iperf3 to simulate network interference')
    parser.add_argument('--socket_type', dest='socket_type',
                        choices=['AF_PACKET', 'AF_XDP'],
                        help='Choose socket family type.')
    parser.add_argument('--talker-xdp-hw-queue', dest='talker_xdp_hw_queue',
                        help='Hardware queue to use for XDP traffic on Talker.')
    parser.add_argument('--listener-hw-queue', dest='listener_tsn_hw_queue',
                        help='Hardware queue where Listener related packets '
                             'will be routed. This applies to both AF_XDP '
                             'and AF_PACKET sockets.')
    parser.add_argument('--listener-other-hw-queue',
                        dest='listener_other_hw_queue',
                        help='Hardware queue to route traffic not related to '
                             'Listener. Applicable for both AF_PACKET and '
                             'AF_XDP sockets.')
    parser.add_argument('--vlan-priority', dest='vlan_priority',
                        help='VLAN priority for XDP Ethernet Frame Header')
    parser.add_argument('--xdp-needs-wakeup',
                        dest='xdp_needs_wakeup',
                        choices=['yes', 'no'],
                        help='set XDP_USE_NEEDS_WAKEUP flag for AF_XDP')
    parser.add_argument('--rx-irq-smp-affinity', dest='rx_irq_affinity',
                        help='Set SMP Affinity Mask for IRQ thread'
                             ' corresponding to the Rx Hardware queue.'
                             ' Only useful in AF_XDP Mode.')
    parser.add_argument('--xdp-mode', dest='xdp_mode',
                        choices=['SKB', 'Native'],
                        help='Mode for XDP socket.')
    parser.add_argument('--xdp-copy-mode', dest='xdp_copy_mode',
                        choices=['Copy', 'Zero-Copy'],
                        help='Copy mode for XDP socket.')

    group_iter = parser.add_mutually_exclusive_group()
    group_iter.add_argument('-n', dest='test_iterations',
                            help='Number of packets sent for each experiment')
    group_iter.add_argument('-t', dest='test_time', type=int,
                            help='Seconds that each experiment sends packets')

    args = parser.parse_args()

    # Do this check after parse args, so that help can be shown without sudo
    if os.geteuid() != 0:
        sys.stderr.write(
            'This command requires root privileges. Please rerun using sudo\n')
        sys.exit(1)

    with open(args.config_file, 'r') as f:
        config = json.load(f)

        results_dir = args.results_dir
        os.makedirs(results_dir, exist_ok=True)

        if args.role is not None:
            util.set_configuration_key(config, args.role, 'General Setup',
                                       'Mode')
        role = util.get_configuration_key(config, 'General Setup', 'Mode')

        if args.interface_name is not None:
            util.set_configuration_key(config, args.interface_name,
                                       'System Setup', 'TSN Interface')

        if args.dest_addr is not None:
            if role != 'talker':
                raise Exception('Destination MAC Address can only be set on '
                                'talker')
            util.set_configuration_key(config, args.dest_addr, 'Talker Setup',
                                       'Destination MAC Address')

        if args.intermediate_latency:
            util.set_configuration_key(config, True, 'General Setup',
                                       'Intermediate latency')

        if args.enable_log:
            util.set_configuration_key(config, True, 'General Setup',
                                       'Collect system log')

        if args.keep_perf_data:
            util.set_configuration_key(config, True, 'General Setup',
                                       'Keep perf data')

        if args.run_stress:
            util.set_configuration_key(config, True, 'General Setup',
                                       'Stress CPUs')

        if args.isol_core is not None:
            util.set_configuration_key(config, args.isol_core, 'General Setup',
                                       'Isolate CPU')

        if role == 'listener' and (args.test_iterations is not None
                                   or args.test_time is not None):
            raise Exception('Test iterations/time can only be set on talker')

        if args.test_iterations is not None:
            util.set_configuration_key(config, args.test_iterations,
                                       'Talker Setup', 'Iterations')
        elif args.test_time is not None:
            util.set_configuration_key(config, f'{args.test_time}s',
                                       'Talker Setup', 'Iterations')

        if args.network_interf is not None:
            if role != 'talker':
                raise Exception('Network interference can only be set on '
                                'talker')
            util.set_configuration_key(config, args.network_interf == 'yes',
                                       'Talker Setup', 'Network interference')
        if args.socket_type is not None:
            util.set_configuration_key(config, args.socket_type,
                                       'General Setup', 'Socket Type')

        if args.vlan_priority is not None:
            util.set_configuration_key(config, args.vlan_priority,
                                       'General Setup', 'VLAN Priority')

        if args.talker_xdp_hw_queue is not None:
            util.set_configuration_key(config, args.talker_xdp_hw_queue,
                                       'Talker Setup', 'XDP Hardware Queue')

        if args.listener_tsn_hw_queue is not None:
            util.set_configuration_key(config, args.listener_tsn_hw_queue,
                                       'Listener Setup', 'TSN Hardware Queue')

        if args.listener_other_hw_queue is not None:
            util.set_configuration_key(config, args.listener_other_hw_queue,
                                       'Listener Setup',
                                       'Other Hardware Queue')

        if args.xdp_needs_wakeup is not None:
            util.set_configuration_key(config,
                                       args.xdp_needs_wakeup == 'yes',
                                       'General Setup', 'XDP Setup',
                                       'Needs Wakeup')

        if args.rx_irq_affinity is not None:
            util.set_configuration_key(config, args.rx_irq_affinity,
                                       'Listener Setup',
                                       'Rx IRQ SMP Affinity Mask')

        if args.xdp_mode is not None:
            util.set_configuration_key(config, args.xdp_mode,
                                       'General Setup', 'XDP Setup', 'Mode')

        if args.xdp_copy_mode is not None:
            util.set_configuration_key(config, args.xdp_copy_mode,
                                       'General Setup', 'XDP Setup',
                                       'Copy Mode')

        socket_type = util.get_configuration_key(config, 'General Setup',
                                                 'Socket Type')
        if role == 'talker' and socket_type == 'AF_XDP':
            talker_xdp_hw_queue = util.get_configuration_key(config,
                                                             'Talker Setup',
                                                             'XDP Hardware Queue')
            if talker_xdp_hw_queue is None:
                raise Exception('Please specify Hardware queue for AF_XDP')

        if role == 'listener':
            rx_irq_affinity = util.get_configuration_key(config,
                                                         'Listener Setup',
                                                         'Rx IRQ SMP Affinity Mask')

            if socket_type == 'AF_XDP' or rx_irq_affinity is not None:
                listener_tsn_hw_queue = util.get_configuration_key(config,
                                                                   'Listener Setup',
                                                                   'TSN Hardware Queue')
                if listener_tsn_hw_queue is None:
                    raise Exception('Please specify Hardware queue for Listener.'
                                    'Required for AF_XDP or Rx Irq SMP Affinity')

                other_hw_queue = util.get_configuration_key(config,
                                                            'Listener Setup',
                                                            'Other Hardware Queue')
                if other_hw_queue is None:
                    raise Exception('Please specify Hardware queue for '
                                    'non-XDP traffic. Required for AF_XDP or'
                                    ' Rx Irq SMP Affinity')

                vlan_priority = util.get_configuration_key(config, 'General Setup',
                                                           'VLAN Priority')
                if vlan_priority is None:
                    raise Exception('Please specify VLAN priority for XDP Traffic')

        # Convenience check for the experiment executables
        if role == 'talker':
            if shutil.which('tsn-talker') is None:
                raise Exception('tsn-talker not found. '
                                'Ensure it is built and available on PATH')
        elif role == 'listener':
            if shutil.which('tsn-listener') is None:
                raise Exception('tsn-listener not found. '
                                'Ensure it is built and available on PATH')

        ptp_conf = util.get_configuration_key(config, 'System Setup',
                                              'PTP Conf')
        if not os.path.exists(ptp_conf):
            raise Exception('PTP configuration file not found. '
                            'Check System Setup/PTP Conf" on '
                            f'{args.config_file}')

        with experiment.Experiment(config, args.results_dir) as exp:
            exp.connect()
            exp.run()
            exp.disconnect()

        print(f'Results saved at {args.results_dir}')
