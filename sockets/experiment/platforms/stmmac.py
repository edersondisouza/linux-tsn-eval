# Copyright (c) 2021, Intel Corporation
#
# SPDX-License-Identifier: BSD-3-Clause

from . import common, tools
from util.util import run


class StmmacPlatform(common.CommonPlatform):
    def __init__(self, *args):
        super(StmmacPlatform, self).__init__(*args)
        self.tx_timestamp_timeout = 5

    def _get_irq_name(self):
        return f'{self.interface}:rx-'

    def _enable_interface_optimisations(self):
        mode = self._get_configuration_key('General Setup', 'Mode')
        socket_type = self._get_configuration_key('General Setup',
                                                  'Socket Type')

        ethtool = tools.EthTool(self.interface)
        self.teardown_list.append(ethtool.set_tso('off'))
        if mode.lower() == 'listener':
            if socket_type == 'AF_XDP':
                ethtool.set_rxvlan('off')
            else:
                ethtool.set_rxvlan('on')
        self.teardown_list.append(ethtool.set_coalescing_option('rx-usecs', 5))
        self.teardown_list.append(ethtool.set_coalescing_option('tx-usecs', 1000))
        self.teardown_list.append(ethtool.set_coalescing_option('tx-frames', 1))

    def _setup_rx_filters(self):
        mode = self._get_configuration_key('General Setup', 'Mode')

        if mode.lower() == 'listener':
            self.teardown_list.append(lambda: run(['tc', 'qdisc', 'del',
                                                   'dev', self.interface,
                                                   'parent', 'ffff:']))
