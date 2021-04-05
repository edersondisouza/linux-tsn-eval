# Copyright (c) 2021, Intel Corporation
#
# SPDX-License-Identifier: BSD-3-Clause

from util.util import run


class EthTool:
    def __init__(self, interface):
        self.interface = interface

    def get_driver_info(self):
        output = run(['ethtool', '-i', self.interface],
                     f'The interface {self.interface}, specified in the '
                     'configuration file, is invalid')
        return self.__parse(output.stdout)

    def __get_features(self):
        output = run(['ethtool', '-k', self.interface],
                     f'The interface {self.interface}, specified in the '
                     'configuration file, is invalid')
        return self.__parse(output.stdout)

    def __get_coalescing_options(self):
        output = run(['ethtool', '-c', self.interface])
        return self.__parse(output.stdout)

    def set_gso(self, state):
        features = self.__get_features()
        old_state = features['generic-segmentation-offload']
        run(['ethtool', '-K', self.interface, 'gso', state])
        # return teardown step
        return lambda: run(['ethtool', '-K', self.interface, 'gso', old_state])

    def set_tso(self, state):
        features = self.__get_features()
        old_state = features['tcp-segmentation-offload']
        run(['ethtool', '-K', self.interface, 'tso', state])
        # return teardown step
        return lambda: run(['ethtool', '-K', self.interface, 'tso', old_state])

    def set_coalescing_option(self, option, value):
        current_options = self.__get_coalescing_options()
        current_value = current_options[option]
        if str(value) != current_value:
            run(['ethtool', '-C', self.interface, option, str(value)])
            # return teardown step
            return lambda: run(['ethtool', '-C', self.interface, option,
                               current_value])
        else:
            return lambda: None

    def __get_eee(self):
        output = run(['ethtool', '--show-eee', self.interface])
        return self.__parse(output.stdout)['EEE status']

    def set_eee(self, state):
        if self.__get_eee() == 'disabled':
            old_state = 'off'
        else:
            old_state = 'on'
        run(['ethtool', '--set-eee', self.interface, 'eee', state])
        return lambda: run(['ethtool', '--set-eee', self.interface, 'eee',
                           old_state])

    def __parse(self, output):
        output_dict = {}
        for line in output.splitlines():
            s = line.strip()
            if s != '':
                items = s.split(':', 1)
                if len(items) == 2:
                    output_dict[items[0]] = items[1].strip()
        return output_dict

    def set_rxvlan(self, state):
        features = self.__get_features()
        old_state = features['rx-vlan-offload']
        run(['ethtool', '-K', self.interface, 'rxvlan', state])
        # return teardown step
        return lambda: run(['ethtool', '-K', self.interface, 'rxvlan',
                            old_state])

    def set_rx_filter_vlan(self, vlan_priority, hw_queue):
        # We need to pass the 16-but TCI and vlan priority is bits 13:15
        output = run(['ethtool', '-N', self.interface,
                      'flow-type', 'ether',
                      'vlan', str(vlan_priority << 13),
                      'vlan-mask', '0x1FFF',
                      'action', str(hw_queue)])

        if output.stderr != '':
            raise Exception(f'ERROR: {output.stderr}')

        filter_id = output.stdout.split()[-1]

        return lambda: run(['ethtool', '-N', self.interface,
                            'delete', filter_id])

    def set_rx_filter_ethertype(self, ethertype, hw_queue):
        output = run(['ethtool', '-N', self.interface,
                      'flow-type', 'ether',
                      'proto', str(ethertype),
                      'action', str(hw_queue)])

        if output.stderr != '':
            raise Exception(f'ERROR: {output.stderr}')

        filter_id = output.stdout.split()[-1]

        return lambda: run(['ethtool', '-N', self.interface,
                            'delete', filter_id])


class IP:
    def __init__(self, interface):
        self.interface = interface

    def set_interface_ip_address(self, address):
        run(['ip', 'addr', 'add', address + '/24', 'dev', self.interface])
        # return the teardown command
        return lambda: run(['ip', 'addr', 'del', address + '/24', 'dev',
                           self.interface])

    def get_interface_info(self):
        output = run(['ip', 'addr', 'show', self.interface]).stdout
        tokens = output.split()
        state_keyword_location = tokens.index('state')
        state = tokens[state_keyword_location + 1]
        mac_keyword_location = tokens.index('link/ether')
        mac_address = tokens[mac_keyword_location + 1]
        return (mac_address, state)

    def set_interface_up(self):
        run(['ip', 'link', 'set', 'dev', self.interface, 'up'])
        # return the teardown command
        return lambda: run(['ip', 'link', 'set', 'dev', self.interface,
                           'down'])

    def set_mtu(self, mtu):
        old_mtu = self.__get_mtu()
        run(['ip', 'link', 'set', 'dev', self.interface, 'mtu', str(mtu)])
        # return the teardown command
        return lambda: run(['ip', 'link', 'set', 'dev', self.interface, 'mtu',
                            old_mtu])

    def __get_mtu(self):
        output = run(['ip', 'addr', 'show', self.interface]).stdout
        tokens = output.split()
        mtu_keyword_location = tokens.index('mtu')
        return tokens[mtu_keyword_location + 1]

    def add_vlan(self):
        run(['ip', 'link', 'add', 'link', self.interface, 'name', 'tsn_vlan',
             'type', 'vlan', 'id', '5', 'egress-qos-map', '2:2', '3:3'])
        return lambda: run(['ip', 'link', 'del', 'tsn_vlan'])

    def add_multicast_address(self, dest_addr):
        run(['ip', 'maddr', 'add', dest_addr, 'dev', self.interface])

        return lambda: run(['ip', 'maddr', 'del', dest_addr, 'dev',
                            self.interface])


class IRQ:
    def __init__(self, irq_name):
        self.irq_name = irq_name
        self.irq_num = None

    def __get_irq_num(self):
        if self.irq_num is not None:
            return self.irq_num

        proc_irqs = open('/proc/interrupts', 'r')
        for line in proc_irqs.readlines():
            irq_info = line.split()
            if irq_info[-1] == self.irq_name:
                self.irq_num = irq_info[0][:-1]
                return self.irq_num

        raise Exception(f'IRQ not found. Does the interrupt ({self.irq_name})'
                        ' exist?')

    def __get_irq_smp_affinity(self):
        irq_num = self.__get_irq_num()
        current_mask = run(['cat', f'/proc/irq/{irq_num}/smp_affinity'])

        return current_mask.stdout

    def __set_irq_smp_affinity(self, cpu_affinity_mask):
        irq_num = self.__get_irq_num()
        irq_smp_aff_file = open(f'/proc/irq/{irq_num}/smp_affinity', 'w')

        irq_smp_aff_file.write(cpu_affinity_mask)
        irq_smp_aff_file.close()

    def set_irq_smp_affinity(self, cpu_affinity_mask):
        current_mask = self.__get_irq_smp_affinity()

        self.__set_irq_smp_affinity(str(cpu_affinity_mask))
        return lambda: self.__set_irq_smp_affinity(current_mask)
