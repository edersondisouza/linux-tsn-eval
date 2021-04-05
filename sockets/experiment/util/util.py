# Copyright (c) 2021, Intel Corporation
#
# SPDX-License-Identifier: BSD-3-Clause

import subprocess


class MissingConfigurationError(Exception):
    def __init__(self, *key):
        self.missing_key = key

    def __str__(self):
        key_string = self.__build_key_string()
        error_msg = (f'\n\nThe parameter\n{key_string} '
                     'is missing from the configuration file.\n'
                     'Please specify it and try again.')
        return error_msg

    def __build_key_string(self):
        indent = 0
        key_string = ''
        for subkey in self.missing_key:
            key_string += ' ' * indent + subkey + ':\n'
            indent += 2
        return key_string


class SubprocessError(Exception):
    def __init__(self, command, hint, stderr):
        self.hint = hint
        self.stderr = stderr
        self.command = ' '.join(command)

    def __str__(self):
        error_description = ('\n\nThe command\n'
                             f'{self.command}\n'
                             'failed with the following message\n\n'
                             f'{self.stderr}\n\n')
        if self.hint is not None:
            error_description += ('The most likely cause of this failure is:\n'
                                  f'{self.hint}')
        return error_description


def get_configuration_key(configuration, *args):
    try:
        current_value = configuration
        for arg in args:
            current_value = current_value[arg]
        return current_value
    except KeyError:
        raise MissingConfigurationError(*args)


def set_configuration_key(configuration, value, *args):
    current_value = configuration
    for arg in args[:-1]:
        if arg not in current_value.keys():
            current_value[arg] = dict()
        current_value = current_value[arg]

    current_value[args[-1]] = value


def run(command, failure_hint=None):
    result = subprocess.run(command, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, universal_newlines=True)
    if result.returncode != 0:
        raise SubprocessError(command, failure_hint, result.stderr)
    return result
