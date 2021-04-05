/*
 * Copyright (c) 2021, Intel Corporation
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>

#define NUM_SIGNALS 3

int running = 1;

static void terminate_prog(int sig)
{
	running = 0;
}

int handle_signals(void)
{
	static const int signal_list[NUM_SIGNALS] = {SIGINT, SIGQUIT, SIGTERM};
	struct sigaction sa;
	int i;

	memset(&sa, 0, sizeof(sa));
	sa.sa_handler = terminate_prog;

	for (i = 0; i < NUM_SIGNALS; i++) {
		if (sigaction(signal_list[i], &sa, NULL) == -1) {
			fprintf(stderr, "Cannot handle %s: %s.\n",
					strsignal(signal_list[i]),
					strerror(errno));
			return -1;
		}
	}

	return 0;
}
