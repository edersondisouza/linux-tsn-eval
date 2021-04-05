/*
 * Copyright (c) 2021, Intel Corporation
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#pragma once

#include <linux/if_ether.h>
#include <stdint.h>

#define ETH_P_UADP 0xb62c
#define MAX_SIZE 1500

struct payload {
	uint64_t seqnum;
	uint64_t timestamp;
} __attribute__ ((__packed__));

struct vlan_packet {
	struct ethhdr eth_hdr;
	struct {
		uint16_t tpid;
		uint16_t tci;
	} vlan_tag;
} __attribute__ ((__packed__));
