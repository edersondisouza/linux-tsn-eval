# Copyright (c) 2021, Intel Corporation
#
# SPDX-License-Identifier: BSD-3-Clause

from util import util
from . import i210
from . import stmmac

platforms = {
    "i210": i210.I210,
    "stmmac": stmmac.StmmacPlatform,
}


def get_platform(configuration):
    platform_name = util.get_configuration_key(
        configuration, 'General Setup', 'Platform')
    return platforms[platform_name](configuration)
