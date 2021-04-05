/*
 * Copyright (c) 2021, Intel Corporation
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#pragma once

#include <bpf/xsk.h>

struct xsk_socket_info {
	struct xsk_ring_cons rx;
	struct xsk_ring_prod tx;
	struct xsk_ring_prod fq;
	struct xsk_ring_cons cq;
	struct xsk_umem *umem;
	void *buffer;
	struct xsk_socket *xsk;
	uint32_t bpf_prog_id;
	int ifindex;
};

int xsk_configure(struct xsk_socket_info *xsk, uint64_t size, char *ifname,
		  int hw_queue, int num_frames, bool tx, int xdp_bind_flags,
		  int xdp_flags);

void xsk_teardown(struct xsk_socket_info *xsk, int num_frames);
