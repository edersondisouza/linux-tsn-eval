/*
 * Copyright (c) 2021, Intel Corporation
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#include <arpa/inet.h>
#include <errno.h>
#include <linux/if_ether.h>
#include <net/if.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/time.h>
#include <unistd.h>

#include "xdp-common.h"
#define MAX_XSK_TRIES 5

static int xsk_populate_fill_ring(struct xsk_socket_info *xsk, int num_frames)
{
	int i, num_frames_reserved;
	uint32_t idx;

	num_frames_reserved = xsk_ring_prod__reserve(&xsk->fq,
				     num_frames, &idx);
	for (i = 0; i < num_frames_reserved; i++)
		*xsk_ring_prod__fill_addr(&xsk->fq, idx++) =
			i * XSK_UMEM__DEFAULT_FRAME_SIZE;
	xsk_ring_prod__submit(&xsk->fq, num_frames);

	return num_frames_reserved;
}

int xsk_configure(struct xsk_socket_info *xsk, uint64_t size, char *ifname,
		  int hw_queue, int num_frames, bool tx, int xdp_bind_flags,
		  int xdp_flags)
{
	struct xsk_umem_config umem_cfg = {
		.fill_size = XSK_RING_PROD__DEFAULT_NUM_DESCS,
		.comp_size = XSK_RING_CONS__DEFAULT_NUM_DESCS,
		.frame_size = XSK_UMEM__DEFAULT_FRAME_SIZE,
		.frame_headroom = XSK_UMEM__DEFAULT_FRAME_HEADROOM,
		.flags = 0
	};
	struct xsk_socket_config xsk_cfg = {
		.rx_size = XSK_RING_CONS__DEFAULT_NUM_DESCS,
		.tx_size = XSK_RING_PROD__DEFAULT_NUM_DESCS,
		.libbpf_flags = 0,
		.xdp_flags = xdp_flags,
		.bind_flags = xdp_bind_flags,
	};
	struct rlimit r = {RLIM_INFINITY, RLIM_INFINITY};
	struct xsk_ring_cons *rxr;
	struct xsk_ring_prod *txr;
	int ret, try = 0;
	void *bufs;

	/* Let this app have all resource. Need root */
	if (setrlimit(RLIMIT_MEMLOCK, &r)) {
		perror("ERROR: setrlimit(RLIMIT_MEMLOCK)");
		return -1;
	}

	bufs = mmap(NULL, num_frames * XSK_UMEM__DEFAULT_FRAME_SIZE,
		    PROT_READ | PROT_WRITE,
		    MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	if (bufs == MAP_FAILED) {
		perror("ERROR: mmap failed");
		return -1;
	}
	xsk->buffer = bufs;

	rxr = tx ? NULL : &xsk->rx;
	txr = tx ? &xsk->tx : NULL;

try_again:
	ret = xsk_umem__create(&xsk->umem, bufs,
			       num_frames * XSK_UMEM__DEFAULT_FRAME_SIZE, &xsk->fq,
			       &xsk->cq, &umem_cfg);
	if (ret) {
		perror("Unable to create UMEM");
		munmap(xsk->buffer, num_frames * XSK_UMEM__DEFAULT_FRAME_SIZE);
		return -1;
	}

	ret = xsk_socket__create(&xsk->xsk, ifname, hw_queue, xsk->umem,
				 rxr, txr, &xsk_cfg);

	/* A UMEM region can only be associated with a single hardware queue.
	 * This mapping is done in xsk_socket__create().
	 *
	 * When the XDP socket is destroyed (using xsk_socket__delete()),
	 * clearing the mapping between UMEM and the hardware queue is done as
	 * part of xdp_umem_release_deferred() which is scheduled to be done
	 * later as part of a workqueue.
	 *
	 * If tsn-talker/tsn-listener is run back-to-back, there is a chance
	 * the mapping between UMEM and the Hardware queue from the last socket
	 * is not cleared. So, the socket creation is tried a few times before
	 * it returns an error.
	 */
	if (ret == -EBUSY && try < MAX_XSK_TRIES) {
		try++;
		sleep(1);
		goto try_again;
	}

	if (ret) {
		perror("Unable to create XDP socket");
		xsk_umem__delete(xsk->umem);
		munmap(xsk->buffer, num_frames * XSK_UMEM__DEFAULT_FRAME_SIZE);
		return -1;
	}

	if (!tx) {
		/* There is some bug where the fill queue does not accept any
		 * frames if it is completely full. So, do not populate it
		 * completely.
		 */
		ret = xsk_populate_fill_ring(xsk,
					     XSK_RING_PROD__DEFAULT_NUM_DESCS / 2);
		if (ret != XSK_RING_PROD__DEFAULT_NUM_DESCS / 2) {
			fprintf(stderr, "Unable to add requested frames to fq:\n"
				"frames requested: %d, frames submitted: %d.\n",
				XSK_RING_PROD__DEFAULT_NUM_DESCS / 2, ret);
		}
	}

	xsk->ifindex = if_nametoindex(ifname);
	ret = bpf_get_link_xdp_id(xsk->ifindex, &xsk->bpf_prog_id, 0);
	if (ret) {
		perror("Unable to retrieve BPF program id");
		xsk_socket__delete(xsk->xsk);
		xsk_umem__delete(xsk->umem);
		munmap(xsk->buffer, num_frames * XSK_UMEM__DEFAULT_FRAME_SIZE);
		return -1;
	}

	return 0;
}

void remove_xdp_program(struct xsk_socket_info *xsk)
{
	uint32_t curr_prog_id = 0;

	if (bpf_get_link_xdp_id(xsk->ifindex, &curr_prog_id, 0)) {
		fprintf(stderr, "bpf_get_link_xdp_id failed\n");
		return;
	}

	if (xsk->bpf_prog_id == curr_prog_id)
		bpf_set_link_xdp_fd(xsk->ifindex, -1, 0);
	else if (!curr_prog_id)
		fprintf(stderr, "couldn't find a prog id on a given interface\n");
	else
		fprintf(stderr, "program on interface changed, not removing\n");
}


void xsk_teardown(struct xsk_socket_info *xsk, int num_frames)
{
	xsk_socket__delete(xsk->xsk);
	xsk_umem__delete(xsk->umem);
	munmap(xsk->buffer, num_frames * XSK_UMEM__DEFAULT_FRAME_SIZE);
	remove_xdp_program(xsk);
}
