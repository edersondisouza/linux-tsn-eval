# TSN Evaluation Framework for Linux\* OS

This repository provides tools to automate the measurement and evaluation
of latency that Linux Time Sensitive Networking (TSN) systems are subject to.
Latency information collected include End-to-End, transmission, reception and
intermediate - inside the OS - latency.

Latency measurements are performed for two socket families usually used for
TSN traffic:
* AF_PACKET
* AF_XDP

There are two set of tools which are utilized to evaluate both TSN Talker and
Listener scenarios. The helper tools to automate the execution of experiments
are landed in _sockets/experiment_ directory while tools that automate the data
analysis are landed in _sockets/analysis_. Instructions on how to run
experiments, collect and analyse data are provided in the README file under
_sockets_ directory.

## Dependencies

Python3 (3.7 or higer) is a requirement for running the framework. A few
external python3 modules are also needed for the analysis steps.
All the Python\* related dependencies can be installed by running:
```
$ pip install -r requirements.txt
```

Other (non-Python) dependencies needed to run the framework are:

* linuxptp
* iproute2
* ethtool
* stress-ng (for CPU interference support)
* perf with Python bindings (for intermediate latency capture support)
* libbpf (for AF_XDP sockets)
* iperf (for network interference support)

## Disclaimer

In order to correctly perform its activities, such as setting network
parameters up, sending data using privileged sockets and collecting
kernel performance data, the framework requires privileged access to
the device in which it runs - i.e. root access.

It also may, depending on the configuration of the evaluation being
run, stress the CPU and Network interface under test.

Hence, the framework is only intended to be used in validation or testing
environments, NOT for production environments.

 \* Other names and brands may be claimed as the property of others.
