# Copyright (c) 2021, Intel Corporation
#
# SPDX-License-Identifier: BSD-3-Clause

import csv
import multiprocessing
import os
import pickle
import signal
import subprocess
from syslog import syslog
from time import sleep


class Runner:
    # Subclasses are expected to override their perf events and filters. A pair
    # (event, filter) is expected. If filter is None, no filter is added.
    # The following alias are understood to ease filter creation:
    #   $payload_len (current payload len; 18 is added to make up for headers)
    #   $phy_name (name of the physical interface)
    #   $vlan_tci (vlan tag control information, tailored for socket priority)
    _perf_events = []

    def __init__(self, cmd_socket, results_dir, iface_name, dest_addr,
                 run_stress, isol_core, intermediate_latency, keep_perf_data,
                 talker_ip):
        self.command = []
        self.cmd_socket = cmd_socket
        self.results_dir = results_dir
        self.iface_name = iface_name
        self.dest_addr = dest_addr
        self.run_stress = run_stress
        self.isol_core = isol_core
        self.intermediate_latency = intermediate_latency
        self.keep_perf_data = keep_perf_data
        self.stress_cmd = [
            'stress-ng',
            '--cpu', str(multiprocessing.cpu_count()),
            '--cpu-method', 'loop'
        ]
        self.talker_ip = talker_ip
        self.interference_process = None

    def run(self):
        raise NotImplementedError('Must implement run()')

    def _insert_cmd(self, cmd):
        cmd.extend(self.command)
        self.command = cmd

    def _get_tai_offset(self):
        timer_list = open('/proc/timer_list', 'r')
        timer_list_str = timer_list.read()

        start, part, end = timer_list_str.partition('ktime_get_clocktai\n')
        clock_tai_str = end.splitlines()[0]

        return int(clock_tai_str.split()[1])

    def _generate_perf_cmd(self, perf_output_name, payload_size, socket_prio):
        # Here we use --mmap-pages argument to ensure that no events are being
        # dropped by `perf record`.
        perf_cmd = [
            'perf', 'record', '-a',
            '--mmap-pages', '128M',
            '-k', 'CLOCK_MONOTONIC',
            '-o', perf_output_name
        ]

        if len(self._perf_events) == 0:
            raise NotImplementedError('Must override _perf_events')

        for (event, filter_) in self._perf_events:
            perf_cmd.extend(['-e', event])
            if filter_ is not None:
                payload_size = int(payload_size) + 18  # To account for headers
                iface_name = self._get_phy_iface_name(self.iface_name)
                # The 5 below is vlan id - currently hardcoded, if it stops to
                # be so, this needs to be fixed
                vlan_tci = ((int(socket_prio) & 0x3) << 13) | 5

                filter_ = (filter_.replace('$payload_len', str(payload_size))
                                  .replace('$phy_name', iface_name)
                                  .replace('$vlan_tci', str(vlan_tci)))
                perf_cmd.extend(['--filter', filter_])

        return perf_cmd

    def _process_intermediate_tstamps(self, iface_name, tai_mono_offset,
                                      perf_output_name, perf_script_name):
        trace_file_name = '/tmp/trace_out.txt'

        # Collect Intermediate Timestamps
        parse_cmd = [
            'perf', 'script',
            '-i', perf_output_name,
            '-s', perf_script_name,
            trace_file_name,
            self._get_phy_iface_name(iface_name),
            str(tai_mono_offset)
        ]

        parse_process = subprocess.Popen(parse_cmd)
        parse_process.wait()

        dataset = self._read_csv(trace_file_name)

        os.remove(trace_file_name)

        return dataset

    def _get_phy_iface_name(self, vlan_iface_name):
        cmd = ['ip', 'link', 'show', vlan_iface_name]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
        out, _ = process.communicate()
        return out.split('@')[1].split(':')[0]

    def _read_csv(self, f):
        close_on_exit = False
        if isinstance(f, str):
            f = open(f, 'r', newline='')
            close_on_exit = True

        data = []
        reader = csv.reader(f)
        for row in reader:
            data.append(row)

        if close_on_exit:
            f.close()

        return data

    def _start_stress(self):
        if self.run_stress:
            self.stress_process = subprocess.Popen(self.stress_cmd)

    def _stop_stress(self):
        if self.run_stress:
            self.stress_process.send_signal(signal.SIGTERM)
            self.stress_process.wait()
            self.stress_process = None

    def _insert_isol_core(self):
        if self.isol_core is not None:
            syslog(f'Isolating listener on core {self.isol_core}')
            self._insert_cmd(['taskset', '-c', str(self.isol_core)])

    def _insert_intermediate_latency(self, factors):
        perf_output_name = None
        if self.intermediate_latency:
            perf_output_name = (f'{self.results_dir}/perf-'
                                f'{factors["PayloadSize"]}-'
                                f'{factors["TransmissionInterval"]}.data')
            self._insert_cmd(self._generate_perf_cmd(perf_output_name,
                                                     factors['PayloadSize'],
                                                     factors['SO_PRIORITY']))

        return perf_output_name

    def _start_network_interference(self):
        raise NotImplementedError('Must implement '
                                  '_start_network_interference()')

    def _stop_interference(self):
        if self.interference_process is not None:
            self.interference_process.send_signal(signal.SIGTERM)
            self.interference_process.wait()
            self.interference_process = None


class TalkerRunner(Runner):
    _cmd_name = 'tsn-talker'

    def __init__(self, *args, iterations, network_interference):
        super(TalkerRunner, self).__init__(*args)
        self.interference_cmd = ['iperf3', '-s']
        self.iterations = iterations
        self.network_interference = network_interference

    def _transfer_intermediate_tstamps(self, dataset):
        # Transfer intermediate timestamp data to the Listener
        self.cmd_socket.send(b'INTERMEDIATE_TSTAMPS_INCOMING')
        self.cmd_socket.send(pickle.dumps(dataset))

    def _calculate_iterations(self, factors):
        iterations = self.iterations
        if isinstance(self.iterations, str):
            if self.iterations[-1:] == 's':
                iterations = int(int(self.iterations[:-1]) * 1000000000 /
                                 int(factors['TransmissionInterval']))
            else:
                iterations = self.iterations

        return iterations

    def _insert_run_command(self, factors, iterations):
        cmd = [
            'chrt', '--fifo', '98',
            self._cmd_name,
            '-i', self.iface_name,
            '-d', self.dest_addr,
            '-n', str(iterations),
            '-p', factors['SO_PRIORITY'],
            '-s', factors['PayloadSize'],
            '-D', factors['TransmissionInterval']]
        self._insert_cmd(cmd)

    def run(self, factors):
        out_file = open(f'{self.results_dir}/output_file.txt', 'a')
        err_file = open(f'{self.results_dir}/errors_file.txt', 'a')

        data = self.cmd_socket.getmsg()
        while data != b'START_TALKER':
            data = self.cmd_socket.getmsg()

        tai_mono_offset = self._get_tai_offset()

        self._start_stress()
        self._start_network_interference()
        iterations = self._calculate_iterations(factors)
        self._insert_run_command(factors, iterations)
        self._insert_isol_core()
        perf_output_name = self._insert_intermediate_latency(factors)

        syslog(
            f'Commencing talker experiment. {iterations} iterations, '
            f'{factors["PayloadSize"]} payload size and '
            f'{factors["TransmissionInterval"]} transmission interval\n'
            f'TAI-monotonic offset {tai_mono_offset}')
        process = subprocess.Popen(self.command, stdout=out_file,
                                   stderr=err_file)
        process.wait()
        syslog('Completed talker experiment')

        self._stop_interference()
        self._stop_stress()

        if tai_mono_offset != self._get_tai_offset():
            print("WARNING: The offset between CLOCK_TAI and CLOCK_MONOTONIC "
                  "has changed. Data might be invalid")

        self.cmd_socket.send(b'STOP_LISTENER')

        if self.intermediate_latency:
            dataset = self._process_intermediate_tstamps(self.iface_name,
                                                         tai_mono_offset,
                                                         perf_output_name)
            self._transfer_intermediate_tstamps(dataset)
            if not self.keep_perf_data:
                os.remove(perf_output_name)
        else:
            self.cmd_socket.send(b'NO_INTERMEDIATE_TSTAMPS')

        self.command = []

        err_file.close()
        out_file.close()

    def _start_network_interference(self):
        if self.network_interference:
            self.interference_process = subprocess.Popen(self.interference_cmd)
            self.cmd_socket.send(b'START_NETWORK_INTERFERENCE')
        else:
            self.cmd_socket.send(b'NO_NETWORK_INTERFERENCE')


class AFPacketTalkerRunner(TalkerRunner):
    _perf_events = [
        ('syscalls:sys_enter_sendto', f"comm == '{TalkerRunner._cmd_name}'"),
        ('net:net_dev_queue', 'len <= $payload_len'),
        ('net:net_dev_start_xmit', 'protocol == 0x22f0 || '
                                   'vlan_tci == $vlan_tci'),
        ('net:net_dev_xmit', 'len <= $payload_len')
    ]

    def _process_intermediate_tstamps(self, *args):
        perf_script_name = 'tx-intermediate-perf-script.py'

        return (super(AFPacketTalkerRunner, self).
                _process_intermediate_tstamps(*args, perf_script_name))


class AFXDPTalkerRunner(TalkerRunner):
    def __init__(self, *args, **kwargs):
        self.xdp_hw_queue = kwargs.pop('xdp_hw_queue')
        self.vlan_priority = kwargs.pop('vlan_priority')
        self.needs_wakeup = kwargs.pop('needs_wakeup')
        self.xdp_mode = kwargs.pop('mode')
        self.xdp_copy_mode = kwargs.pop('copy_mode')
        super(AFXDPTalkerRunner, self).__init__(*args, **kwargs)

        if self.intermediate_latency is True:
            NotImplementedError('Intermediate latency metrics not supported on'
                                'AF_XDP Socket.')

    def _insert_run_command(self, *args):
        super(AFXDPTalkerRunner, self)._insert_run_command(*args)

        syslog(f'Running XDP socket on queue {self.xdp_hw_queue}'
               f'with VLAN Priority {self.vlan_priority}, '
               f'mode: {self.xdp_mode} and copy mode: {self.xdp_copy_mode}')
        self.command.extend(['-X', str(self.xdp_hw_queue),
                             '-V', str(self.vlan_priority)])

        if self.needs_wakeup:
            self.command.append('-w')

        if self.xdp_mode == 'Native':
            self.command.append('-N')
        else:
            self.command.append('-S')

        if self.xdp_copy_mode == 'Copy':
            self.command.append('-C')
        else:
            self.command.append('-Z')


class ListenerRunner(Runner):
    _cmd_name = 'tsn-listener'

    def __init__(self, *args):
        super(ListenerRunner, self).__init__(*args)
        self.interference_cmd = ['iperf3', '-c', self.talker_ip, '-t', '0',
                                 '-R']

    def _receive_intermediate_tstamps(self):
        dumpfile = self.cmd_socket.getmsg()
        intr_data = pickle.loads(dumpfile)
        return intr_data

    def _write_dataset(self, dataset, intr_data_talker, intr_data_listener,
                       csv_file):
        csv_writer = csv.writer(csv_file)

        # On the very first write, we add the headers
        if csv_file.tell() == 0:
            header = []
            header.append(dataset[0][0])  # sw tx ts
            if intr_data_talker is not None:
                header.extend(intr_data_talker[0])
            header.append(dataset[0][1])  # hw rx ts
            if intr_data_listener is not None:
                header.extend(intr_data_listener[0])
            header.append(dataset[0][2])  # sw rx ts
            csv_writer.writerow(header)

        for i in range(1, len(dataset)):
            row = []
            row.append(dataset[i][0])  # sw tx ts
            if intr_data_talker is not None:
                row.extend(intr_data_talker[i])
            row.append(dataset[i][1])  # hw rx ts
            if intr_data_listener is not None:
                row.extend(intr_data_listener[i])
            row.append(dataset[i][2])  # sw rx ts
            csv_writer.writerow(row)

    def _insert_run_command(self, factors):
        cmd = [
            'chrt', '--fifo', '98',
            self._cmd_name,
            '-i', self.iface_name,
            '-s', factors['PayloadSize']]
        self._insert_cmd(cmd)

    def run(self, factors):
        intr_data_talker = None
        intr_data_listener = None
        out_file = open(f'{self.results_dir}/.out_file', 'w+')
        err_file = open(f'{self.results_dir}/errors_file.txt', 'a')

        self._start_stress()
        self._insert_run_command(factors)
        self._insert_isol_core()
        perf_output_name = self._insert_intermediate_latency(factors)

        process = subprocess.Popen(self.command, stdout=out_file,
                                   stderr=err_file)

        # When tsn-listener enables RX timestamping, NIC is reset and ptp4l
        # is disrupted. So, wait for sometime for ptp4l to reconnect.
        sleep(60)

        tai_mono_offset = self._get_tai_offset()
        syslog(
            f'Commencing listener experiment. {factors["PayloadSize"]} '
            f'payload size and {factors["TransmissionInterval"]} '
            f'transmission interval\nTAI-monotonic offset: {tai_mono_offset}')

        self.cmd_socket.send(b'START_TALKER')
        self._start_network_interference()
        data = self.cmd_socket.getmsg()
        while data != b'STOP_LISTENER':
            data = self.cmd_socket.getmsg()

        self._stop_interference()
        self._stop_stress()

        process.send_signal(signal.SIGINT)
        process.wait()

        syslog('Completed listener experiment')

        data = self.cmd_socket.getmsg()
        if data == b'INTERMEDIATE_TSTAMPS_INCOMING':
            intr_data_talker = self._receive_intermediate_tstamps()

        if self.intermediate_latency:
            if tai_mono_offset != self._get_tai_offset():
                print("WARNING: Offset between CLOCK_TAI and CLOCK_MONOTONIC "
                      "has changed. Data might be invalid")

            intr_data_listener = (
                self._process_intermediate_tstamps(
                    self.iface_name,
                    tai_mono_offset,
                    perf_output_name))
            if not self.keep_perf_data:
                os.remove(perf_output_name)

        csv_file_name = (f'{self.results_dir}/results-{factors["PayloadSize"]}'
                         f'-{factors["TransmissionInterval"]}.csv')

        if self.intermediate_latency or intr_data_talker is not None:
            out_file.seek(0)
            dataset = self._read_csv(out_file)

            with open(csv_file_name, 'w') as csv_file:
                self._write_dataset(dataset, intr_data_talker,
                                    intr_data_listener, csv_file)
            out_file.close()
            os.remove(out_file.name)
        else:
            # Without intermediate latency, renaming out_file should be quicker
            out_file.close()
            os.rename(out_file.name, csv_file_name)

        err_file.close()

        self.command = []

        return csv_file_name

    def _start_network_interference(self):
        data = self.cmd_socket.getmsg()
        if data == b'NO_NETWORK_INTERFERENCE':
            return
        elif data == b'START_NETWORK_INTERFERENCE':
            self.interference_process = subprocess.Popen(self.interference_cmd)
        else:
            raise Exception(f'Unexpected listener message {data}')


class AFPacketListenerRunner(ListenerRunner):
    def __init__(self, *args, irq_name):
        super(AFPacketListenerRunner, self).__init__(*args)
        self.irq_name = irq_name

        self._perf_events = [
            ('irq:irq_handler_entry', f"name ~ '{self.irq_name}*'"),
            ('net:napi_gro_receive_entry', 'protocol == 0x22f0'),
            ('net:netif_receive_skb', "name ~ "
                                      "'$phy_name*' && len <= $payload_len"),
            ('syscalls:sys_exit_recvmsg', f"comm == '{self._cmd_name}'")
        ]

    def _process_intermediate_tstamps(self, *args):
        perf_script_name = 'rx-intermediate-perf-script.py'

        return (super(ListenerRunner, self).
                _process_intermediate_tstamps(*args, perf_script_name))


class AFXDPListenerRunner(ListenerRunner):
    def __init__(self, *args, xdp_hw_queue, needs_wakeup, mode, copy_mode):
        super(AFXDPListenerRunner, self).__init__(*args)
        self.xdp_hw_queue = xdp_hw_queue
        self.needs_wakeup = needs_wakeup
        self.xdp_mode = mode
        self.xdp_copy_mode = copy_mode

        if self.intermediate_latency is True:
            NotImplementedError('Intermediate latency metrics not supported on'
                                'AF_XDP Socket.')

    def _insert_run_command(self, *args):
        super(AFXDPListenerRunner, self)._insert_run_command(*args)

        syslog(f'Running XDP socket on queue {self.xdp_hw_queue}, '
               f'mode: {self.xdp_mode} and copy mode: {self.xdp_copy_mode}')
        self.command.extend(['-X', str(self.xdp_hw_queue)])

        if self.needs_wakeup:
            self.command.append('-w')

        if self.xdp_mode == 'Native':
            self.command.append('-N')
        else:
            self.command.append('-S')

        if self.xdp_copy_mode == 'Copy':
            self.command.append('-C')
        else:
            self.command.append('-Z')
