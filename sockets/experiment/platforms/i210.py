# Copyright (c) 2021, Intel Corporation
#
# SPDX-License-Identifier: BSD-3-Clause

import sys
from . import common, tools
from util import util


class I210(common.CommonPlatform):
    def _get_irq_name(self):
        return f'{self.interface}-TxRx-'

    def _enable_interface_optimisations(self):
        ip_command = tools.IP(self.interface)
        self.teardown_list.append(ip_command.set_mtu(1514))
        ethtool = tools.EthTool(self.interface)
        self.teardown_list.append(ethtool.set_gso('off'))
        self.teardown_list.append(ethtool.set_tso('off'))
        self.teardown_list.append(ethtool.set_coalescing_option('rx-usecs', 0))

        socket_type = self._get_configuration_key('General Setup',
                                                  'Socket Type')
        if socket_type == 'AF_XDP':
            ethtool.set_rxvlan('off')
        else:
            ethtool.set_rxvlan('on')

        try:
            self.teardown_list.append(ethtool.set_eee('off'))
        except util.SubprocessError as err:
            if 'Operation not supported' in err.stderr:
                sys.stderr.write('WARNING: ')
                sys.stderr.write(
                    'Energy Efficient Ethernet not supported on NIC\n')
            else:
                raise

    def _setup_rx_filters(self):
        mode = self._get_configuration_key('General Setup', 'Mode')
        rx_irq_affinity = self._get_configuration_key('Listener Setup',
                                                      'Rx IRQ SMP Affinity Mask')

        if mode.lower() != 'listener' or rx_irq_affinity is None:
            return

        ethtool = tools.EthTool(self.interface)
        tsn_hw_queue = self._get_configuration_key('Listener Setup',
                                                   'TSN Hardware Queue')
        other_hw_queue = self._get_configuration_key('Listener Setup',
                                                     'Other Hardware Queue')
        vlan_priority = self._get_configuration_key('General Setup',
                                                    'VLAN Priority')

        self.teardown_list.append(ethtool.set_rx_filter_vlan(vlan_priority,
                                                             tsn_hw_queue))
        # VLAN Priority 0 corresponds to best effort traffic
        self.teardown_list.append(ethtool.set_rx_filter_vlan(0,
                                                             other_hw_queue))
        # 0x88F7 corresponds to ethertype for PTP packets
        self.teardown_list.append(ethtool.set_rx_filter_ethertype(0x88F7,
                                                                  other_hw_queue))
