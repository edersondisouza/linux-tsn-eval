project('TSN Kernel Evaluation Framework',
	[ 'c' ],
	version: '0,1',
	license: 'BSD-3-Clause',
)

libbpf_dep = dependency('libbpf', method: 'pkg-config')

tsn_talker_sources = ['tools/tsn-talker.c', 'tools/signals.c',
		      'tools/xdp-common.c']
executable('tsn-talker', tsn_talker_sources, dependencies: libbpf_dep)

tsn_listener_sources = ['tools/tsn-listener.c', 'tools/signals.c',
			'tools/xdp-common.c']
executable('tsn-listener', tsn_listener_sources, dependencies: libbpf_dep)
