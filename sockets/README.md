# Socket Families Evaluation

This folder contains programs and scripts which can be used to analyze transmit
and receive latencies encountered by a packet within the kernel. Currently, we
can use both AF_PACKET and AF_XDP socket protocol families to send and receive data.

It contains the following programs:
* __tools/tsn-talker__: send packets at specified rate and size. It captures time just
  before sending the packet and embeds it in the payload.
* __tools/tsn-listener__: receives the packets sent by tsn-talker and extract the
  timestamp in the payload. It will also extract the hardware receive timestamp
  and print the 2 timestamps to stdout in CSV format.
* __experiment/run_experiment.py__: Automation script to run tsn-talker and
  tsn-listener in different configurations.
* __analysis/run_analysis.py__: Script to analyze the timestamp and print statistics.
* __misc/tsn_setup.json__: Example configuration file for run_experiment.py.

## Running the Experiment

### Linux\* Kernel Modifications

In order to reduce noise and consistently measure latency involved in the
transmission and reception of packets, it's recommended to use a realtime kernel.
As an example, we provide a kernel config file at socket/misc folder. It's
currently based on Linux kernel version 5.2.21-rt13[^footnote].
The major changes in the kernel configuration are:
* Disable Retpoline.
* Set PCIE ASPM to "Performance".
* Enable  Ftrace with hist triggers.
* set 'idle=poll' in kernel command-line.

Note that in production environments, it's necessary to do a proper assessment
of any kernel configuration option, based on workload, security and power
consumption expectations.

If it is desired to isolate tsn-talker and tsn-listener application on a
specific core, following kernel command-line arguments can be included:
* `irqaffinity=0`
* `nohz_full=5`
* `isolcpus=nohz,domain,5`

After the system has booted, the CPU should be taken offline and back online so
that the timers and interrupts on the CPU can be migrated to another CPU.
```
echo 0 > /sys/devices/system/cpu/cpu5/online
echo 1 > /sys/devices/system/cpu/cpu5/online
```
Change the CPU number from 5 to desired CPU. Note that cpu0_hotplug needs to be
included in the kernel commandline in order to take cpu0 offline. Also,
irqaffinity will have to be changed. For more information look at
https://www.kernel.org/doc/html/latest/core-api/cpu_hotplug.html.

To learn more about how to isolate different kernel threads look at
https://www.kernel.org/doc/html/latest/admin-guide/kernel-per-CPU-kthreads.html

### Experiment Setup

Easiest way to use the framework to collect latency measurements is by having
two systems, connected back-to-back, using TSN capable NICs. One will act as
TSN Talker, while the other will act as TSN Listener. Currently, the framework
assumes systems are connected back-to-back, so propagation time between the
systems is considered insignificant and thus ignored.

Time synchronization is setup on both systems using Linuxptp. The framework
will also setup time synchronization. For more information about it, check
the guide at: https://tsn.readthedocs.io/timesync.html.

In addition, following configuration is applied by the framework:
* Disable "Generic Segmentation Offload" and "TCP Segmentation Offload". This
  will disable "Jumbo Frames". Which means smaller packets are not combined
  into larger packets before being sent over network.
* Disable interrupt coalescing. This will ensure that the packet is delivered to
  the user space ASAP.
* Disable Energy Efficient Ethernet. This will make sure the NIC does not sleep
  when there is no activity.

The system acting as a TSN Talker also sets up qdiscs.

All those configuration steps - as well as setting up VLAN interfaces and IP
stack for control messages of the experiments are done automatically by
the run_experiment.py script. This script reads information from a JSON file
describing the environment setup.

Some important configurations that need to be defined before fist run are:
* `System setup/TSN Interface`: network interface card under test.
* `System setup/PTP Conf`: linuxptp configuration file - usually, gPTP.conf.
* `General Setup/Mode`: if a given host will be acting as TSN talker or
   listener.
* `General Setup/Platform`: platform of the network interface card under test.

Check [configuration file format](#experiment-configuration-json-format)
for more information about other experiment options.

If you are planning to use the AF_XDP socket type to transmit and receive
packets, libbpf needs to be installed on the target systems. Following are the
steps to install libbpf:
```
git clone https://github.com/libbpf/libbpf.git
cd src/
make install
```

Finally, the tsn-talker and tsn-listener executables need to be compiled before
the experiment scripts can be run:
```
cd /path-to-tsn-evaluation-framework-root/sockets/
meson build
cd build
ninja
```
Add their build folder to PATH environment variable:
```
export PATH=$PATH:/path-to-tsn-evaluation-framework-root/sockets/build/
```

#### Additional steps for capturing intermediate Latency

perf with Python\* support is required in order to capture intermediate latency.
Most distributions provide this by default in the linux-tools package.

For Ubuntu\*, perf points to a script which verifies the perf version installed
matches the kernel version. But, when running a custom kernel (e.g. the
PREEMPT_RT kernel), perf corresponding to the kernel may not be available. In
that case, install the closest version of the `linux-tools` package available
and then add it to $PATH as follows:
```
apt install linux-tools-<closest-kernel-version>
export PATH=/usr/lib/linux-tools/<kernel-version-installed>:$PATH
```

#### Note on network management

Network management software, such as systemd-networkd, was found to correlate
with some spikes on latency, even if they are not managing the TSN interface.
As an example, the following commands can be used to stop some network
management services prior to experiment execution:

```
sudo systemctl stop systemd-networkd.socket
sudo systemctl stop systemd-networkd.service
sudo systemctl stop systemd-resolved.service
```

After the experiment, one can enable then again with:

```
sudo systemctl start systemd-networkd.socket
sudo systemctl start systemd-networkd.service
sudo systemctl start systemd-resolved.service
```

Note however that depending on system setup, it may be necessary to stop
other services as well, or at least prevent other services from restarting
network management services.

For other distros and/or network management services, consult their respective
documentation.

### Experiment Execution

First, start run_experiment.py on the system running as TSN Listener:
```
cd /path-to-tsn-evaluation-framework-root/sockets/experiment
sudo python3 run_experiment.py \
    -c ../misc/tsn_setup.json
```
Then, start run_experiment.py on TSN Talker system:
```
cd /path-to-tsn-evaluation-framework-root/sockets/experiment
sudo python3 run_experiment.py \
    -c ../misc/tsn_setup.json
```
The results will be saved in the system which is acting as TSN Listener.

For more information about the parameters run:
```
python3 run_experiment.py -h
```

#### Note on sudo and $PATH

As the framework does some system changes as part of the setup of
experiment, it requires privileged permissions. In some distros though,
when running `sudo`, the $PATH environment variable is not preserved,
so the framework fails to find `tsn-talker` or `tsn-listener` executables.
In such cases, using:
```
sudo --preserve-env=PATH python3 [...]
```
Should help. For more information, check sudo documentation.

## Analysing results

### Generating charts and statistics
The charts and statistics can be generated for the experiment using the
run_analysis.py script as follows:
```
cd /path-to-tsn-evaluation-framework-root/sockets/analysis
python3 run_analysis.py -d /path-to-results-folder/
```

For more information about the parameters run:
```
python3 run_analysis.py -h
```

### Comparing Different Runs
The CSV data generated from Different test runs can be compared in order to
analyze differences between runs. Currently, Bi-histograms and intermediate
latency comparison is supported:
```
python3 run_comparison.py --csv-dir-1 ~/results-1 \
    --csv-dir-1-label "Results Label 1" \
    --csv-dir-2 ~/results-2/csv_data.txt \
    --csv-dir-2-label "Results Label 2"
```

## Unit Testing

Some Python modules may have unit tests available. These tests use the standard
Python unittest framework so no additional dependencies need to be installed.

### Running the tests

To run the available tests, change to the root directory of the repository and
run unittest on the test package.
```
cd /path-to-tsn-evaluation-framework-root
python3 -m unittest sockets.test
```

### Adding new test modules

By running unittest with the `sockets.test` parameter, you are telling unittest
to run any `test_*` methods in the `sockets.test` package. If you add a new
unittest file, you need to import its test methods into the package namespace by
modifying `sockets/test/__init__.py`, otherwise, unittest won't automatically
find them.

In addition, telling unittest to run `sockets.test` makes sockets the root of
the package hierarchy. Any files you may want to test can be imported from the
test module by importing relative to `sockets`

eg. To test `sockets/experiment/util/foo.py`, you'd add a new module called
`sockets/test/test_foo.py`. From `test_foo.py`, you can
```
import sockets.experiment.util.foo
```

## Experiment configuration JSON format

The configuration file uses [JSON](https://www.json.org/json-en.html) format,
and the following sections and values are recognized:

* `System Setup`
  * `TSN Interface` (__string__) name of the TSN interface under test, such as
    `"eth0"`.
  * `PTP Conf` (__string__) path of `linuxptp` tool configuration file.
* `General Setup`
  * `Mode` (__string__) one of `"talker"` or `"listener"`, denoting if local
    system will act as TSN talker or listener.
  * `Platform` (__string__) name of the platform defined in
    `sockets/experiment/platforms`. Each platform defines steps to set them
    up before the experiment. Currently, there's support for `"i210"` and
    `"stmmac"` platforms.
  * `Collect system log` (__boolean__) whether system logs shall be collected
    during the experiment. The logs are collected with `journalctl` tool.
  * `Intermediate latency` (__boolean__) whether intermediate latency data
    should be captured.
  * `Keep perf data` (__boolean__) whether data collected by `perf` tool
    during intermediate latency collection should be kept after the experiment.
    This data can become really huge, and should be kept only for debug
    purposes.
  * `Stress CPUs` (__boolean__) whether `stress-ng` tool shall be used to
    stress system CPUs.
  * `Isolate CPU` (__integer__ or __null__) CPU number where the experiment
    process should be isolated.
  * `Qdisc profile` (__string__) name of the qdisc profile to be used. The
    profiles are defined in the section `Qdiscs profiles`.
  * `Socket Type` (__string__) The socket family to use to transmit and receive
    packets. Currently, AF_PACKET and AF_XDP are supported.
  * `XDP Setup`:
    * `Needs Wakeup` (__boolean__) This sets the XDP_USE_NEEDS_WAKEUP flag when
      using AF_XDP sockets for either transmitting or receiving packets. To
      know more about what the flag does look at:
      https://www.kernel.org/doc/html/latest/networking/af_xdp.html#xdp-use-need-wakeup-bind-flag
    * `Mode` (__string__) Specify the mode in `xsk_socket_config->xdp_flags`.
      Valid values: `"SKB"` or `"Native"`. `"SKB"` will set the
      XDP_FLAGS_SKB_MODE and `"Native"` will set XDP_FLAGS_DRV_MODE. For more
      information look at:
      https://www.kernel.org/doc/html/latest/networking/af_xdp.html
    * `Copy Mode` (__string__) Specify the mechanism used to copy packet data.
      Valid values: `"Copy"` or `"Zero-Copy"`. `"Copy"` will set the XDP_COPY
      flag and `"Zero-Copy"` will set the XDP_ZEROCOPY flag in
      `xsk_socket_config->bind_flags`. For more information, look at:
      https://www.kernel.org/doc/html/latest/networking/af_xdp.html#xdp-copy-and-xdp-zero-copy-bind-flags
  * `VLAN Priority` (__integer__) The value to set for the VLAN Priority field
    in the IEEE 802.1Q tag for the XDP Packets. No effect when `Socket Type` is
    AF_PACKET.
* `Talker Setup`
  * `Destination MAC Address` (__string__) MAC Address of the TSN system, such
    as a broadcast address like `"01AAAAAAAAAA"`.
  * `Experiment profile` (__string__) name of the experiment profile that will
    be used for the experiment. The profiles are defined in the section
    `Experiment profiles`.
  * `Network interference` (__boolean__) whether `iperf3` tool shall be used
    to generate network interference during the run.
  * `Iterations` (__integer__ or __string__) if integer, the number of
    iterations that each experiment will run. If string, the number of seconds
    during each experiment should run - in this case, it must end with an `s`,
    like `"10s"`.
  * `XDP Hardware Queue` (__integer__ or __null__) The hardware queue via which
    the packet should be transmitted. Only useful when the
    `Socket Type` is AF_XDP.
* `Listener Setup`
  * `TSN Hardware Queue` (__integer__ or __null__) The hardware queue where all
    the packets destined for tsn-listener will be routed. This will be applied
    for both AF_PACKET and AF_XDP mode.
  * `Other` (__integer__ or __null__) The hardware queue where all the VLAN and
    PTP related packets will be routed on the listener. Note: This can be
    utilized for both AF_PACKET and AF_XDP `Socket Type`s.
  * `Rx IRQ SMP Affinity` (__null__ or __integer__): This is a mask to set the
    CPU affinity for the interrupt handler corresponding to the Rx hardware
    queue when the listener is running in the AF_XDP mode.
* `Experiment Profiles`<br>
  Each experiment profile is defined as _&lt;name&gt;_:_&lt;array&gt;_.
  _&lt;name&gt;_ is the name of the profile, as is referenced by
  `Talker Setup/Experiment profile` configuration. _&lt;array_&gt; is an array
  describing the experiment factors. Each element is a string like an entry
  to a CSV file: the first entry shall contain the headers
  `"TransmissionInterval,PayloadSize,SO_PRIORITY"`, and subsequent elements
  will describe the values for each experiment. `"TransmissionInterval"` is
  in nanoseconds, `"PayloadSize"` is in bytes and `"SO_PRIORITY"` is the
  socket priority number that should be used to send the experiment data. For
  instance:
  ```js
    "48-100x125u-250u": [
        "TransmissionInterval,PayloadSize,SO_PRIORITY",
        "125000,48,3",
        "125000,100,3",
        "250000,48,3",
        "250000,100,3"
    ]
  ```
  Describes a profile named `"48-100x125u-250u"`, with four entries. Those
  entries all use socket priority 3, and alternate between 125us and 250us
  of transmission interval and between 48 and 100 bytes packets.
* `Qdiscs profiles`<br>
  Each qdisc profile is defined as _&lt;name_&gt;:_&lt;array_&gt;.
  _&lt;name_&gt; is the name of the profile, as is referenced by
  `General Setup/Qdisc profile` configuration. _&lt;array_&gt; is an array
  describing the `tc` tool commands that need to be run, in order, to set up
  the desired qdisc profile. Note that there's no need to start with the
  commands with `tc` - that is done automatically. Also, there's no need to
  add a command to drop existing qdiscs - all qdiscs for the configured TSN
  interface are dropped automatically before the commands are run. The
  following aliases can be utilized in the commands:
  * `$iface`: Name of the interface being tested. This is same as `TSN Interface`.
  * `$tsn_hw_queue`: The hardware queue on the NIC where the incoming AF_XDP
    packets will routed. This is same as `Hardware Queue.XDP`.
  * `$tsn_vlan_prio`: The expected VLAN priority for incoming AF_XDP packets.
    This is same as `VLAN Priority`.
  * `$other_hw_queue`: The hardware queue on the NIC where all the packets
    which are not AF_XDP will be routed. This is same as `Hardware Queue.Other`.

[^footnote]: available at
https://git.kernel.org/pub/scm/linux/kernel/git/rt/linux-rt-devel.git/

\* Other names and brands may be claimed as the property of others.
