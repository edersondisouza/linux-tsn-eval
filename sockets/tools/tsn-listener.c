/*
 * Copyright (c) 2021, Intel Corporation
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#include <alloca.h>
#include <argp.h>
#include <arpa/inet.h>
#include <errno.h>
#include <inttypes.h>
#include <net/if.h>
#include <linux/if.h>
#include <linux/if_ether.h>
#include <linux/if_link.h>
#include <linux/if_packet.h>
#include <linux/net_tstamp.h>
#include <linux/sockios.h>
#include <poll.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#include "packet.h"
#include "signals.h"
#include "xdp-common.h"

#define NSEC_PER_SEC 1000000000
#define NUM_FRAMES (4 * 1024)

static char ifname[IFNAMSIZ];
static ssize_t size = 1500;
static bool check_seq;
static uint64_t expected_seq;
static int hw_queue = -1;
static int xdp_bind_flags;
static int xdp_flags;

static struct argp_option options[] = {
	{"check-seq", 'c', NULL, 0, "Check sequence number within frame" },
	{"copy-mode", 'C', NULL, 0, "Enforce \'copy mode\' for XDP Socket."},
	{"ifname", 'i', "IFNAME", 0, "Network Interface" },
	{"native-mode", 'N', NULL, 0, "Enforce native (or driver) mode for XDP Socket."},
	{"payload-size", 's', "NUM", 0, "Expected payload size" },
	{"skb-mode", 'S', NULL, 0, "Enforce SKB mode for XDP Socket."},
	{"use-xdp", 'X', "NUM", 0, "Receive data via AF_XDP socket " },
	{"needs-wakeup", 'w', NULL, 0, "Set XDP_USE_NEEDS_WAKEUP flag."},
	{"zero-copy-mode", 'Z', NULL, 0, "Enforce \'zero copy mode\' for XDP Socket."},
	{ 0 }
};

static error_t parser(int key, char *arg, struct argp_state *state)
{
	switch (key) {
	case 'c':
		check_seq = true;
		break;
	case 'C':
		xdp_bind_flags |= XDP_COPY;
		break;
	case 'i':
		strncpy(ifname, arg, sizeof(ifname) - 1);
		break;
	case 'N':
		xdp_flags |= XDP_FLAGS_DRV_MODE;
		break;
	case 's':
		size = atoi(arg);
		if (size > 1500 || size < 0) {
			fprintf(stderr, "Invalid size: %ld", size);
			exit(EXIT_FAILURE);
		}
		break;
	case 'S':
		xdp_flags |= XDP_FLAGS_SKB_MODE;
		break;
	case 'w':
		xdp_bind_flags |= XDP_USE_NEED_WAKEUP;
		break;
	case 'X':
		hw_queue = atoi(arg);
		break;
	case 'Z':
		xdp_bind_flags |= XDP_ZEROCOPY;
		break;
	}

	return 0;
}

static struct argp argp = { options, parser };

static uint64_t timestamp_now(int clockid)
{
	struct timespec ts;

	clock_gettime(clockid, &ts);

	return ts.tv_sec * NSEC_PER_SEC + ts.tv_nsec;
}

int enable_rx_timestamp(const int sock_fd, const char *interface)
{
	int timestamping_flags = SOF_TIMESTAMPING_RX_HARDWARE |
				 SOF_TIMESTAMPING_RAW_HARDWARE;
	struct hwtstamp_config hwconfig = { 0 };
	struct ifreq hwtstamp = { };
	int rc;

	rc = snprintf(hwtstamp.ifr_name, sizeof(hwtstamp.ifr_name), "%s",
		      interface);
	if (rc < 0) {
		fprintf(stderr, "Could not copy Interface name\n");
		return -1;
	} else if (rc >= sizeof(hwtstamp.ifr_name)) {
		fprintf(stderr, "Interface name is too long");
		return -1;
	}

	hwtstamp.ifr_data = (void *)&hwconfig;
	hwconfig.rx_filter = HWTSTAMP_FILTER_ALL;

	if (ioctl(sock_fd, SIOCSHWTSTAMP, &hwtstamp) == -1) {
		perror("ioctl failed");
		return -1;
	}

	if (setsockopt(sock_fd, SOL_SOCKET, SO_TIMESTAMPING, &timestamping_flags,
		       sizeof(timestamping_flags)) == -1) {
		perror("setsockopt failed");
		return -1;
	}

	return 0;
}

static int setup_socket(void)
{
	struct sockaddr_ll sk_addr = {
		.sll_family = AF_PACKET,
		.sll_protocol = htons(ETH_P_TSN),
	};
	int fd, res, ifindex;

	fd = socket(AF_PACKET, SOCK_DGRAM, htons(ETH_P_TSN));
	if (fd < 0) {
		perror("Couldn't open socket");
		return -1;
	}

	ifindex = if_nametoindex(ifname);
	if (!ifindex) {
		perror("Couldn't get interface index");
		goto err;
	}

	sk_addr.sll_ifindex = ifindex;

	res = bind(fd, (struct sockaddr *) &sk_addr, sizeof(sk_addr));
	if (res < 0) {
		perror("Couldn't bind() to interface");
		goto err;
	}

	if (enable_rx_timestamp(fd, ifname))
		fprintf(stderr, "Cannot enable timestamps\n");

	return fd;

err:
	close(fd);
	return -1;
}

void check_sequence(struct payload *p)
{
	uint64_t seq = be64toh(p->seqnum);

	/* If 'expected_seq' is equal to zero, it means this is the
	 * first frame we received so we don't know what sequence
	 * number to expect.
	 */
	if (expected_seq == 0)
		expected_seq = seq;

	if (seq != expected_seq) {
		fprintf(stderr, "Sequence mismatch: expected %" PRIu64
			", got %" PRIu64 "\n", expected_seq, seq);

		expected_seq = seq;
	}

	expected_seq++;
}

static int recv_xdp_frame(struct xsk_socket_info *xsk)
{
	struct pollfd pfd = {
		.fd = xsk_socket__fd(xsk->xsk),
		.events = POLLIN,
	};
	const struct xdp_desc *rx_desc;
	uint32_t idx_rx, idx_fq;
	uint64_t sw_recv_ts, sw_trans_ts;
	unsigned int rcvd;
	struct payload *p;
	struct vlan_packet *hdr;
	char *pkt;
	int ret;

	ret = poll(&pfd, 1, -1);
	if (ret == -1) {
		perror("poll() returned an error");
		return -1;
	}

	rcvd = xsk_ring_cons__peek(&xsk->rx, 1, &idx_rx);
	if (!rcvd)
		return 0;

	rx_desc = xsk_ring_cons__rx_desc(&xsk->rx, idx_rx);
	pkt = xsk_umem__get_data(xsk->buffer, rx_desc->addr);

	/* Record SoftwareReceiveTimestamp. */
	sw_recv_ts = timestamp_now(CLOCK_TAI);

	hdr = (struct vlan_packet *) pkt;
	p = (struct payload *) (pkt + sizeof(struct vlan_packet));
	sw_trans_ts = be64toh(p->timestamp);
	xsk_ring_cons__release(&xsk->rx, rcvd);

	ret = xsk_ring_prod__reserve(&xsk->fq, rcvd, &idx_fq);
	if (ret == rcvd) {
		uint64_t *fq_fill_addr = (uint64_t *) xsk_ring_prod__fill_addr(
							&xsk->fq,
							idx_fq);
		*fq_fill_addr = rx_desc->addr;
		xsk_ring_prod__submit(&xsk->fq, rcvd);
	}

	/*
	 * Usually, ETH_P_TSN is used by TSN applications. But, for stmmac, all
	 * packets tagged with ETH_P_TSN always get routed to queue 0 no matter
	 * what the routing policy. So, expect a packet with ETH_P_UADP from
	 * the talker.
	 */
	if (hdr->vlan_tag.tci != ntohs(ETH_P_UADP))
		return 0;

	if (check_seq)
		check_sequence(p);

	printf("%" PRIu64 ",%" PRIu64 "\n", sw_trans_ts,
		sw_recv_ts);

	return 0;
}

static void recv_frame(int fd)
{
	struct payload *p = (void *) alloca(size);
	struct iovec iov = { p, size };
	struct timespec *ts = NULL;
	uint64_t hw_recv_ts, sw_recv_ts;
	struct cmsghdr *cm;
	struct msghdr msg;
	char control[256];
	ssize_t n;

	memset(control, 0, sizeof(control));
	memset(&msg, 0, sizeof(msg));
	msg.msg_iov = &iov;
	msg.msg_iovlen = 1;
	msg.msg_control = control;
	msg.msg_controllen = sizeof(control);

	n = recvmsg(fd, &msg, 0);
	if (n < 0) {
		perror("Failed to receive data");
		return;
	}

	sw_recv_ts = timestamp_now(CLOCK_TAI);

	if (n != size)
		fprintf(stderr, "Size mismatch: expected %ld, got %ld\n", size, n);

	if (check_seq)
		check_sequence(p);

	/* look for receive timestamp in CMSG Header. */
	for (cm = CMSG_FIRSTHDR(&msg); cm != NULL; cm = CMSG_NXTHDR(&msg, cm)) {
		int level = cm->cmsg_level;
		int type = cm->cmsg_type;

		if (SOL_SOCKET == level && SO_TIMESTAMPING == type) {
			if (cm->cmsg_len < sizeof(*ts) * 3) {
				fprintf(stderr, "short SO_TIMESTAMPING message");
				return;
			}
			ts = (struct timespec *) CMSG_DATA(cm);
			hw_recv_ts = NSEC_PER_SEC * ts[2].tv_sec + ts[2].tv_nsec;
		}
	}

	if (ts)
		printf("%" PRIu64 ",%" PRIu64 ",%" PRIu64 "\n", be64toh(p->timestamp),
			hw_recv_ts, sw_recv_ts);
}

int main(int argc, char *argv[])
{
	struct xsk_socket_info xsk = { 0 };
	extern int running;
	int sk_fd, ret;

	if (handle_signals() == -1)
		exit(1);

	memset(ifname, 0, IFNAMSIZ);
	argp_parse(&argp, argc, argv, 0, NULL, NULL);

	if (ifname[0] == '\0') {
		fprintf(stderr, "Please provide interface name.\n");
		exit(1);
	}

	if (hw_queue != -1) {
		ret = xsk_configure(&xsk, size, ifname, hw_queue, NUM_FRAMES,
				    false, xdp_bind_flags, xdp_flags);
		if (ret == -1)
			exit(1);
	} else {
		sk_fd = setup_socket();
		if (sk_fd < 0)
			exit(1);
	}

	if (hw_queue != -1)
		printf("SoftwareTransmitTimestamp,SoftwareReceiveTimestamp\n");
	else
		printf("SoftwareTransmitTimestamp,HardwareReceiveTimestamp,SoftwareReceiveTimestamp\n");

	ret = mlockall(MCL_CURRENT);
	if (ret == -1)
		perror("mlockall failed");

	while (running) {
		if (hw_queue != -1) {
			ret = recv_xdp_frame(&xsk);
			if (ret == -1) {
				fprintf(stderr, "recv_xdp_frame() returned an error\n");
				break;
			}
		} else {
			recv_frame(sk_fd);
		}
	}

	fflush(stdout);
	if (hw_queue != -1)
		xsk_teardown(&xsk, NUM_FRAMES);
	else
		close(sk_fd);
	return 0;
}
