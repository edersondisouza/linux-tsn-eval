# Copyright (c) 2021, Intel Corporation
#
# SPDX-License-Identifier: BSD-3-Clause

import subprocess
import os
import time
from . import tools
from syslog import syslog
from util import util


class CommonPlatform:
    def __init__(self, configuration):
        self.conf = configuration
        self.teardown_list = []
        self.vlan_if = 'tsn_vlan'
        self.talker_ip = '169.254.10.10'
        self.listener_ip = '169.254.10.11'
        self.experiment_port = 2000

    def _log_platform(self):
        self._log_interface()
        self._log_kernel()
        self._log_linux_ptp()

    def setup(self):
        self._log_platform()
        self._enable_interface()
        self._enable_interface_optimisations()
        self._set_rx_irq_affinity()
        self._enable_vlan()
        self._set_queuing_discipline()
        self._accept_multicast_addr()
        self._setup_rx_filters()
        self._start_ptp4l()
        self._wait_ptp4l_stabilise()
        self._configure_utc_offset()
        self._start_phc2sys()
        # TODO maybe run check_clocks here to ensure everything
        # is ok before proceeding?

    def teardown(self):
        for teardown_step in reversed(self.teardown_list):
            teardown_step()

    # Validation steps
    def _log_interface(self):
        self.interface = self._get_configuration_key(
            'System Setup', 'TSN Interface')
        ethtool_output = tools.EthTool(self.interface).get_driver_info()
        bus_info = ethtool_output['bus-info']
        controller_name = util.run(['lspci', '-s', bus_info]).stdout
        syslog(f'NIC under test: {controller_name} ')

    def _log_kernel(self):
        output = util.run(['uname', '-a']).stdout
        syslog(f'Kernel under test: {output}')
        kernel_cmdline = open('/proc/cmdline', 'r').read()
        syslog(f'Kernel command line: {kernel_cmdline}')

    def _log_linux_ptp(self):
        version = util.run(['ptp4l', '-v']).stdout
        syslog(f'Linuxptp version: {version}')

    # Setup Steps
    def _enable_interface(self):
        ip_command = tools.IP(self.interface)
        tools.EthTool(self.interface)
        (self.mac, state) = ip_command.get_interface_info()
        if state == 'DOWN':
            self.teardown_list.append(ip_command.set_interface_up())

    def _enable_interface_optimisations(self):
        raise NotImplementedError('Must implement _enable_interface_optimisations()')

    def _set_rx_irq_affinity(self):
        mode = self._get_configuration_key('General Setup', 'Mode')

        if mode.lower() != 'listener':
            return

        hw_queue = self._get_configuration_key('Listener Setup',
                                               'TSN Hardware Queue')
        irq_smp_affinity_mask = self._get_configuration_key('Listener Setup',
                                                            'Rx IRQ SMP Affinity Mask')

        if irq_smp_affinity_mask is not None:
            irq_command = tools.IRQ(self._get_irq_name() + str(hw_queue))
            self.teardown_list.append(irq_command.set_irq_smp_affinity(irq_smp_affinity_mask))

    def _set_queuing_discipline(self):
        qdisc_profile = self._get_configuration_key('General Setup',
                                                    'Qdisc profile')
        tsn_hw_queue = self._get_configuration_key('Listener Setup',
                                                   'TSN Hardware Queue')
        other_hw_queue = self._get_configuration_key('Listener Setup',
                                                     'Other Hardware Queue')
        vlan_priority = self._get_configuration_key('General Setup',
                                                    'VLAN Priority')

        if qdisc_profile is None:
            print("No qdisc profile is being set")
            return

        # First, clean up current qdiscs for interface
        cmd = ['tc', 'qdisc', 'delete', 'dev', self.interface, 'parent',
               'root']
        subprocess.run(cmd)

        commands = self._get_configuration_key('Qdiscs profiles',
                                               qdisc_profile)
        for line in commands:
            line = line.replace('$iface', self.interface)
            line = line.replace('$tsn_hw_queue', str(tsn_hw_queue))
            line = line.replace('$tsn_vlan_prio', str(vlan_priority))
            line = line.replace('$other_hw_queue', str(other_hw_queue))
            cmd = ['tc'] + line.split()
            subprocess.run(cmd)

    def _setup_rx_filters(self):
        socket_type = self._get_configuration_key('Test Setup', 'Socket Type')

        if socket_type == 'AF_XDP':
            raise NotImplementedError('Must implement _setup_rx_filters()')

    def _enable_vlan(self):
        ip_command = tools.IP(self.interface)
        self.teardown_list.append(ip_command.add_vlan())
        vlan_ip_command = tools.IP(self.vlan_if)
        mode = self._get_configuration_key('General Setup', 'Mode')
        if mode.lower() == 'talker':
            vlan_ip_command.set_interface_ip_address(self.talker_ip)
        elif mode.lower() == 'listener':
            vlan_ip_command.set_interface_ip_address(self.listener_ip)
        else:
            raise KeyError(
                'Invalid "General Setup: Mode:" value in the configuration '
                'file')
        self.teardown_list.append(vlan_ip_command.set_interface_up())

    def _start_ptp4l(self):
        ptp_conf_file = os.path.expanduser(
            self._get_configuration_key('System Setup', 'PTP Conf'))
        ptp = subprocess.Popen(
            ['ptp4l', '-i', self.interface, '-f', ptp_conf_file,
             '--step_threshold=1', '-l', '6', '--hwts_filter', 'full'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.teardown_list.append(lambda: ptp.terminate())

    def _configure_utc_offset(self):
        util.run(['pmc', '-u', '-b', '0', '-t', '1',
                  'SET GRANDMASTER_SETTINGS_NP clockClass 248 '
                  'clockAccuracy 0xfe offsetScaledLogVariance 0xffff '
                  'currentUtcOffset 37 leap61 0 leap59 0 '
                  'currentUtcOffsetValid 1 ptpTimescale 1 timeTraceable 1 '
                  'frequencyTraceable 0 timeSource 0xa0'])

    def _start_phc2sys(self):
        phc = subprocess.Popen(['phc2sys', '-s', self.interface, '-c',
                                'CLOCK_REALTIME', '--step_threshold=1',
                                '--transportSpecific=1', '-w'],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.teardown_list.append(lambda: phc.terminate())

    # supporting methods
    def _get_configuration_key(self, *args):
        return util.get_configuration_key(self.conf, *args)

    def _wait_ptp4l_stabilise(self):
        keep_waiting = True
        cmd = ['pmc', '-u', '-b', '0', '-t', '1', 'GET PORT_DATA_SET']
        print('Waiting ptp4l stabilise...')
        while keep_waiting:
            time.sleep(1)

            cp = util.run(cmd)
            lines = cp.stdout.splitlines()
            for line in lines:
                if 'portState' in line:
                    state = line.split()[1]
                    if state.upper() in ['SLAVE', 'MASTER']:
                        keep_waiting = False
                    break

    def _accept_multicast_addr(self):
        ip_command = tools.IP(self.interface)
        dest_mac_addr = self._get_configuration_key('Talker Setup',
                                                    'Destination MAC Address')

        self.teardown_list.append(ip_command.add_multicast_address(dest_mac_addr))

    def _get_irq_name(self):
        return NotImplementedError('Must implement _get_irq_name()')
