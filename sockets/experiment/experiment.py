# Copyright (c) 2021, Intel Corporation
#
# SPDX-License-Identifier: BSD-3-Clause

import csv
import errno
import pickle
import platforms
import runners
import socket
import subprocess
from datetime import datetime
from time import sleep
from util import MPPSocket
from util import util


class Experiment:
    def __init__(self, config, results_dir):
        if config is None:
            raise ValueError('Missing configuration object')
        self.config = config

        self.role = util.get_configuration_key(self.config, 'General Setup',
                                               'Mode')
        if self.role not in ['talker', 'listener']:
            # TODO maybe create an invalid config error?
            raise Exception(f'Invalid Mode: {self.role}. '
                            'Expected "talker" or "listener"')

        self.results_dir = results_dir

        self.sys_log = util.get_configuration_key(self.config, 'General Setup',
                                                  'Collect system log')
        self.run_stress = util.get_configuration_key(self.config,
                                                     'General Setup',
                                                     'Stress CPUs')
        self.isol_core = util.get_configuration_key(self.config,
                                                    'General Setup',
                                                    'Isolate CPU')
        self.int_latency = util.get_configuration_key(self.config,
                                                      'General Setup',
                                                      'Intermediate latency')
        self.keep_perf_data = util.get_configuration_key(self.config,
                                                         'General Setup',
                                                         'Keep perf data')
        self.socket_type = util.get_configuration_key(self.config,
                                                      'General Setup',
                                                      'Socket Type')
        self.talker_xdp_hw_queue = util.get_configuration_key(self.config,
                                                              'Talker Setup',
                                                              'XDP Hardware Queue')
        self.listener_xdp_hw_queue = util.get_configuration_key(self.config,
                                                                'Listener Setup',
                                                                'TSN Hardware Queue')
        self.vlan_priority = util.get_configuration_key(self.config,
                                                        'General Setup',
                                                        'VLAN Priority')
        self.xdp_needs_wakeup = util.get_configuration_key(self.config,
                                                           'General Setup',
                                                           'XDP Setup',
                                                           'Needs Wakeup')
        self.xdp_mode = util.get_configuration_key(self.config,
                                                   'General Setup',
                                                   'XDP Setup', 'Mode')
        if self.xdp_mode not in ['SKB', 'Native']:
            raise Exception(f'invalid XDP Mode: {self.xdp_mode}'
                            'Expected: "SKB" or "Native"')

        self.xdp_copy_mode = util.get_configuration_key(self.config,
                                                        'General Setup',
                                                        'XDP Setup',
                                                        'Copy Mode')
        if self.xdp_copy_mode not in ['Copy', 'Zero-Copy']:
            raise Exception(f'invalid XDP Mode: {self.xdp_copy_mode}'
                            'Expected: "Copy" or "Zero-Copy"')

    def __enter__(self):
        if self.sys_log:
            self.start_time = datetime.now()
        self.setup()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.teardown()

        if self.sys_log:
            log_file = open(f'{self.results_dir}/system_log.txt', 'w')
            journal_cmd = [
                'journalctl',
                '--since', self.start_time.strftime('%Y-%m-%d %H:%M'),
                '--output=short-iso-precise']

            process = subprocess.Popen(journal_cmd, stdout=log_file)
            process.wait()
            log_file.close()

    def _read_csv_dict(self, f):
        data = []
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)
        return data

    def _create_runner(self):
        common_params = [self.cmd_socket, self.results_dir, self.iface_name,
                         self.dest_addr, self.run_stress, self.isol_core,
                         self.int_latency, self.keep_perf_data,
                         self.talker_ip]
        xdp_common_params = {'needs_wakeup': self.xdp_needs_wakeup,
                             'mode': self.xdp_mode,
                             'copy_mode': self.xdp_copy_mode}
        if self.role == 'talker':
            iterations = util.get_configuration_key(self.config,
                                                    'Talker Setup',
                                                    'Iterations')
            net_interf = util.get_configuration_key(self.config,
                                                    'Talker Setup',
                                                    'Network interference')
            talker_params = {'iterations': iterations,
                             'network_interference': net_interf}
            if self.socket_type == 'AF_PACKET':
                self.runner = runners.AFPacketTalkerRunner(*common_params,
                                                           **talker_params)
            elif self.socket_type == 'AF_XDP':
                self.runner = runners.AFXDPTalkerRunner(*common_params,
                                                        **talker_params,
                                                        **xdp_common_params,
                                                        xdp_hw_queue=self.talker_xdp_hw_queue,
                                                        vlan_priority=self.vlan_priority)

        elif self.role == 'listener':
            if self.socket_type == 'AF_PACKET':
                irq_name = self.platform._get_irq_name()
                self.runner = runners.AFPacketListenerRunner(*common_params,
                                                             irq_name=irq_name)
            elif self.socket_type == 'AF_XDP':
                self.runner = runners.AFXDPListenerRunner(*common_params,
                                                          **xdp_common_params,
                                                          xdp_hw_queue=self.listener_xdp_hw_queue)

    def _receive_experiment_params(self):
        dumpfile = self.cmd_socket.getmsg()
        self.exp_params = pickle.loads(dumpfile)
        self.dest_addr = self.cmd_socket.getmsg().decode()

    def _send_experiment_params(self):
        exp_profile = util.get_configuration_key(self.config, 'Talker Setup',
                                                 'Experiment profile')
        exp_params = util.get_configuration_key(self.config,
                                                'Experiment Profiles',
                                                exp_profile)
        self.exp_params = self._read_csv_dict(exp_params)
        self.dest_addr = util.get_configuration_key(self.config,
                                                    'Talker Setup',
                                                    'Destination MAC Address')

        # Transfer the experiment params to listener
        self.cmd_socket.send(pickle.dumps(self.exp_params))
        self.cmd_socket.send(self.dest_addr.encode())

    def connect(self):
        if self.role == 'talker':
            self.cmd_socket = self._setup_talker_cmd_socket()
            # talker send experiment params to listener to avoid mistakes
            # on having to keep both parameters (talker and listener) in sync
            self._send_experiment_params()
        else:
            self.cmd_socket = self._setup_listener_cmd_socket()
            self._receive_experiment_params()

    def disconnect(self):
        if self.role == 'talker':
            msg = self.cmd_socket.getmsg()
            if msg != b'LISTENER_END':
                raise Exception('Unexpected listener ending message')
        else:
            self.cmd_socket.send(b'LISTENER_END')

    def run(self):
        self._create_runner()

        for factors in self.exp_params:
            self.runner.run(factors)

    def _setup_talker_cmd_socket(self):
        cmd_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        while True:
            try:
                cmd_socket.connect((self.listener_ip, self.experiment_port))
                break
            except OSError as err:
                if err.errno not in [errno.ECONNREFUSED, errno.EHOSTUNREACH]:
                    raise err
                print('Connection refused - is listener running?')
                sleep(3)
                print('Trying again...')

        print(f'Connected to {self.listener_ip}:{self.experiment_port}')
        return MPPSocket(cmd_socket)

    def _setup_listener_cmd_socket(self):
        cmd_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cmd_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        cmd_socket.bind((self.listener_ip, self.experiment_port))
        cmd_socket.listen(0)

        conn, addr = cmd_socket.accept()
        print(f'Accepted connection from {addr[0]}:{addr[1]}')
        return MPPSocket(conn)

    def setup(self):
        self.platform = platforms.get_platform(self.config)
        self.platform.setup()
        self.listener_ip = self.platform.listener_ip
        self.talker_ip = self.platform.talker_ip
        self.experiment_port = self.platform.experiment_port
        if self.socket_type == 'AF_PACKET':
            self.iface_name = self.platform.vlan_if
        else:
            self.iface_name = self.platform.interface

    def teardown(self):
        self.platform.teardown()
