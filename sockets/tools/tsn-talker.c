/*
 * Copyright (c) 2021, Intel Corporation
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#include <alloca.h>
#include <argp.h>
#include <arpa/inet.h>
#include <inttypes.h>
#include <net/if.h>
#include <linux/if.h>
#include <linux/if_link.h>
#include <linux/if_packet.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/types.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <unistd.h>
#include <time.h>

#include "packet.h"
#include "signals.h"
#include "xdp-common.h"

#define MAGIC 0xCC
#define NSEC_TO_SEC 1000000000ULL
#define NUM_FRAMES (4 * 1024)
#define VLAN_ID 5
#define VLAN_PRIO_SHIFT 13

static char ifname[IFNAMSIZ];
static uint8_t macaddr[ETH_ALEN];
static int priority = -1;
static ssize_t size = 1500;
static uint64_t seq;
static int tx_int = 0;
static int iterations = 1000000;
static int hw_queue = -1;
static int vlan_priority = 1;
static int xdp_bind_flags;
static int xdp_flags;

static struct argp_option options[] = {
	{"copy-mode", 'C', NULL, 0, "Enforce \'copy mode\' for XDP Socket."},
	{"dst-addr", 'd', "MACADDR", 0, "Stream Destination MAC address" },
	{"tx-int", 'D', "NUM", 0, "Interval (in ns) between frame transmission" },
	{"ifname", 'i', "IFNAME", 0, "Network Interface" },
	{"iterations", 'n', "NUM", 0, "Total iterations for the test" },
	{"native-mode", 'N', NULL, 0, "Enforce native (or driver) mode for XDP Socket."},
	{"prio", 'p', "NUM", 0, "SO_PRIORITY to be set in socket" },
	{"payload-size", 's', "NUM", 0, "Payload size for the frames (in bytes)" },
	{"skb-mode", 'S', NULL, 0, "Enforce SKB mode for XDP Socket."},
	{"use-xdp", 'X', "NUM", 0, "Use AF_XDP to transmit data on specified queue." },
	{"vlan-priority", 'V', "NUM", 0, "set VLAN Priority for XDP packets."},
	{"needs-wakeup", 'w', NULL, 0, "Set XDP_USE_NEEDS_WAKEUP flag."},
	{"zero-copy-mode", 'Z', NULL, 0, "Enforce \'zero copy mode\' for XDP Socket."},
	{ 0 }
};

static error_t parser(int key, char *arg, struct argp_state *state)
{
	int res;

	switch (key) {
	case 'C':
		xdp_bind_flags |= XDP_COPY;
		break;
	case 'd':
		res = sscanf(arg, "%hhx:%hhx:%hhx:%hhx:%hhx:%hhx",
			     &macaddr[0], &macaddr[1], &macaddr[2],
			     &macaddr[3], &macaddr[4], &macaddr[5]);
		if (res != 6) {
			printf("Invalid address\n");
			exit(EXIT_FAILURE);
		}

		break;
	case 'D':
		tx_int = atoi(arg);
		break;
	case 'i':
		strncpy(ifname, arg, sizeof(ifname) - 1);
		break;
	case 'n':
		iterations = atoi(arg);
		break;
	case 'N':
		xdp_flags |= XDP_FLAGS_DRV_MODE;
		break;
	case 'p':
		priority = atoi(arg);
		break;
	case 's':
		size = atoi(arg);
		if (size > 1500 || size <= 0) {
			fprintf(stderr, "Invalid size: %ld\n", size);
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
	case 'V':
		vlan_priority = atoi(arg);
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

	return ts.tv_sec * NSEC_TO_SEC + ts.tv_nsec;
}

static int setup_socket(struct sockaddr_ll *sk_addr)
{
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

	sk_addr->sll_ifindex = ifindex;
	memcpy(&sk_addr->sll_addr, macaddr, ETH_ALEN);

	if (priority != -1) {
		res = setsockopt(fd, SOL_SOCKET, SO_PRIORITY, &priority,
				 sizeof(priority));
		if (res < 0) {
			perror("Couldn't set priority");
			goto err;
		}
	}

	return fd;

err:
	close(fd);
	return -1;
}

int run_nanosleep(struct timespec *ts)
{
	int res;

	ts->tv_nsec += tx_int;
	if (ts->tv_nsec >= NSEC_TO_SEC) {
		ts->tv_nsec = ts->tv_nsec % NSEC_TO_SEC;
		ts->tv_sec++;
	}

	res = clock_nanosleep(CLOCK_TAI, TIMER_ABSTIME, ts, NULL);
	if (res && res != EINTR) {
		fprintf(stderr, "clock_nanosleep() returned an error: %s",
			strerror(res));
		return -1;
	}
	return 0;
}

static void get_interface_macaddr(uint8_t *macaddr)
{
	struct ifreq ifr = { 0 };
	int sk_fd;

	strncpy(ifr.ifr_name, ifname, strlen(ifname) + 1);
	sk_fd = socket(AF_PACKET, SOCK_DGRAM, htons(ETH_P_ALL));
	if (sk_fd < 0) {
		perror("Cannot open AF_PACKET socket");
		exit(EXIT_FAILURE);
	}

	ioctl(sk_fd, SIOCGIFHWADDR, &ifr);
	close(sk_fd);
	memcpy(macaddr, ifr.ifr_hwaddr.sa_data, ETH_ALEN);
}

static void gen_eth_frame(void *frame_addr, uint8_t *src_macaddr)
{
	struct vlan_packet *vlan_pkt = (struct vlan_packet *)frame_addr;
	struct ethhdr *eth_hdr = &vlan_pkt->eth_hdr;

	/* ethernet header */
	memcpy(eth_hdr->h_dest, macaddr, ETH_ALEN);
	memcpy(eth_hdr->h_source, src_macaddr, ETH_ALEN);
	eth_hdr->h_proto = htons(ETH_P_8021Q);

	vlan_pkt->vlan_tag.tpid = htons(vlan_priority << VLAN_PRIO_SHIFT | VLAN_ID);

	/*
	 * Usually, ETH_P_TSN is used by TSN applications. But, for stmmac, all
	 * packets tagged with ETH_P_TSN always get routed to queue 0 no matter
	 * what the routing policy. So, use ETH_P_UADP here.
	 */
	vlan_pkt->vlan_tag.tci = htons(ETH_P_UADP);

	/* payload */
	memset(frame_addr + sizeof(*vlan_pkt), MAGIC, size);
}

int xdp_send(struct xsk_socket_info *xsk)
{
	struct xdp_desc *tx_desc;
	uint32_t idx;
	int ret, rcvd;

	if (xsk_ring_prod__reserve(&xsk->tx, 1, &idx) == 1) {
		tx_desc = xsk_ring_prod__tx_desc(&xsk->tx, idx);
		tx_desc->addr = 0;
		tx_desc->len = size + sizeof(struct vlan_packet);

		xsk_ring_prod__submit(&xsk->tx, 1);

		ret = sendto(xsk_socket__fd(xsk->xsk), NULL, 0, MSG_DONTWAIT,
			     NULL, 0);
		if (ret == -1) {
			perror("sendto() failed");
			return -1;
		}
	} else {
		printf("Could not send packet with seq: %ld\n", seq);
	}

	rcvd = xsk_ring_cons__peek(&xsk->cq, 1, &idx);
	if (rcvd > 0)
		xsk_ring_cons__release(&xsk->cq, rcvd);

	return 0;
}

int main(int argc, char *argv[])
{
	struct sockaddr_ll sk_addr = {
		.sll_family = AF_PACKET,
		.sll_protocol = htons(ETH_P_TSN),
		.sll_halen = ETH_ALEN,
	};
	int sk_fd, ret, exit_status = 0;
	uint8_t src_macaddr[ETH_ALEN];
	struct xsk_socket_info xsk;
	extern int running;
	struct timespec ts;
	uint8_t *data;

	handle_signals();

	argp_parse(&argp, argc, argv, 0, NULL, NULL);

	if ((xdp_flags & XDP_FLAGS_DRV_MODE) && (xdp_flags & XDP_FLAGS_SKB_MODE)) {
		fprintf(stderr, "Cannot specify SKB mode and driver mode at same time.");
		exit(1);
	}

	if ((xdp_bind_flags & XDP_ZEROCOPY) && (xdp_bind_flags & XDP_COPY)) {
		fprintf(stderr, "Cannot specify 'zero copy' and 'copy' mode at same time.");
		exit(1);
	}


	if (hw_queue != -1) {
		ret = xsk_configure(&xsk, size, ifname, hw_queue, NUM_FRAMES,
				    true, xdp_bind_flags, xdp_flags);
		if (ret == -1)
			exit(1);

		data = xsk_umem__get_data(xsk.buffer, 0);

		get_interface_macaddr(src_macaddr);
		gen_eth_frame(data, src_macaddr);

		/* move pointer to start of payload */
		data = data + sizeof(struct vlan_packet);
	} else {
		sk_fd = setup_socket(&sk_addr);
		if (sk_fd == -1) {
			fprintf(stderr, "setup_socket() failed\n");
			exit(1);
		}

		data = alloca(size);
		memset(data, MAGIC, size);
	}

	printf("Sending frames...\n");

	clock_gettime(CLOCK_TAI, &ts);

	ret = mlockall(MCL_CURRENT);
	if (ret == -1)
		perror("mlockall failed");

	while (iterations-- && running) {
		struct payload *p = (void *) data;
		ssize_t n;

		p->seqnum = htobe64(seq++);
		p->timestamp = htobe64(timestamp_now(CLOCK_TAI));

		if (hw_queue != -1) {
			ret = xdp_send(&xsk);

			if (ret == -1) {
				exit_status = 1;
				goto exit;
			}
		} else {
			n = sendto(sk_fd, data, size, 0,
				   (struct sockaddr *) &sk_addr,
				   sizeof(sk_addr));

			if (n < 0)
				perror("Failed to send data");

			if (n != size)
				fprintf(stderr, "%ld bytes sent, requested %ld\n",
					n, size);
		}

		if (tx_int > 0) {
			int res;

			res = run_nanosleep(&ts);
			if (res == -1) {
				exit_status = 1;
				goto exit;
			}
		}
	}

exit:
	if (hw_queue != -1)
		xsk_teardown(&xsk, NUM_FRAMES);
	else
		close(sk_fd);
	return exit_status;
}
