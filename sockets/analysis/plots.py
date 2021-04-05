# Copyright (c) 2021, Intel Corporation
#
# SPDX-License-Identifier: BSD-3-Clause

import matplotlib as mpl
mpl.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from matplotlib.ticker import (AutoMinorLocator, FuncFormatter, MaxNLocator,
                               FormatStrFormatter, LogLocator)


class BiHistogram():
    def __init__(self, values_a, values_b):
        self.values_a = values_a
        self.values_b = values_b
        self.xlabel = 'Latency (us)'

    def _plot_hist(self, axis, label, data, colour):
        hist, edges = np.histogram(data, bins='sqrt')
        axis.fill_between(edges[:-1], hist, color=colour, antialiased=False,
                          rasterized=True)
        axis.set_yscale('log')
        axis.set_xscale('log')
        axis.tick_params(axis='y', which='both', labelsize='xx-small')
        axis.set_ylabel(label)
        axis.grid(True, which='both', axis='x', linewidth=0.3)

    def plot(self, title, filename):
        fig, axes = plt.subplots(2, 1, gridspec_kw={'hspace': 0.01},
                                 sharex=True)

        self._plot_hist(axes[0], self.values_a[0], self.values_a[1], 'orange')
        self._plot_hist(axes[1], self.values_b[0], self.values_b[1],
                        'cornflowerblue')

        axes[1].set_xlabel(self.xlabel, fontsize='x-small')
        axes[1].tick_params(axis='x', which='both', labelsize='xx-small',
                            labelrotation=45)
        axes[1].invert_yaxis()

        ax = axes[1].get_xaxis()
        ax.set_minor_formatter(FormatStrFormatter("%.2f"))
        ax.set_major_formatter(FormatStrFormatter("%.2f"))
        for ax in fig.get_axes():
            ax.label_outer()

        fig.suptitle(title)
        plt.savefig(filename, dpi=300)
        plt.close()


class StackedBarChart():
    def __init__(self):
        self.colours = ['gold', 'lightgreen', 'lightsalmon', 'violet',
                        'cornflowerblue', 'lightcoral']
        self.bars = []
        self.bar_distance = 2
        self.ylabel = 'Latency (us)'

    def add_bar(self, legend, values):
        self.bars.append((legend, values))

    def __attribute_colours(self):
        values_names = sorted({value[0]
                               for bar in self.bars
                               for value in bar[1]})
        if len(values_names) > len(self.colours):
            raise Exception('Add more self.colours for stacked bar chart!')
        return dict(zip(values_names, self.colours))

    def plot(self, title, filename):
        values_colours = self.__attribute_colours()

        indices = []
        index = 0
        for bar in self.bars:
            i = 0
            cumu_col = 0
            for value in bar[1]:
                height = value[1]
                plt.bar(index, height, label=value[0],
                        color=values_colours[value[0]], bottom=cumu_col)
                plt.text(index, cumu_col + height / 2,  "%.3f" % height,
                         ha='center', va='center', fontsize=7)
                cumu_col = height + cumu_col
                i = i + 1

            indices.append(index)
            # Bigger increase to better space the bars
            index = index + self.bar_distance

        ax = plt.gca()
        handles, labels = ax.get_legend_handles_labels()
        # Avoid legend repetition by using the label as a key to dict
        labels, handles = zip(*dict(zip(labels, handles)).items())
        plt.subplots_adjust(right=0.8)
        plt.legend(reversed(handles), reversed(labels), loc='upper left',
                   fontsize='x-small', ncol=1, bbox_to_anchor=(1.01, 1.))
        ax.set_xbound(-1, 4)
        ax.set_xticks(indices)
        ax.set_xticklabels([bar[0] for bar in self.bars])
        plt.title(title)
        plt.xticks(fontsize='x-small')
        plt.ylabel(self.ylabel)
        plt.savefig(filename, dpi=300)
        plt.close()


class HistogramGroupPlot():
    def __init__(self, group_size, min_latency, max_latency, iterations):
        self.min_latency = min_latency
        self.max_latency = max_latency
        self.iterations = iterations
        self.fig, self.plots = plt.subplots(group_size, 1, sharex=True)
        if not isinstance(self.plots, np.ndarray):
            self.plots = np.array([self.plots])
        self.plot_idx = 0
        self.xlabel = 'Latency (us)'

    def add_histogram(self, data, edges, mean, stdev, ylabel):
        if self.plot_idx >= len(self.plots):
            raise Exception("Can't add more histograms: group_size too small")

        plot = self.plots[self.plot_idx]
        self.plot_idx += 1

        plot.fill_between(edges[1:], data, antialiased=False, rasterized=True)
        plot.set_xscale('log', subsx=[2, 4, 6, 8])
        plot.set_yscale('log')

        # Set the labels
        plot.text(0.8, 0.8, f'Mean {mean:.2f} us', fontsize=5,
                  transform=plot.transAxes)
        plot.text(0.8, 0.7, f'STDEV {stdev:.2f} us', fontsize=5,
                  transform=plot.transAxes)
        plot.set_ylabel(ylabel)

        # Set limits and locations of ticks
        # Set ylim a bit bigger than strictly needed so there's some headspace
        # on plots
        plot.set_ylim(0.5, self.iterations * 2)
        ax = plot.get_xaxis()
        ax.limit_range_for_scale(self.min_latency, self.max_latency)

        # There isn't any one-size-fits-all for placing Ticks. So, choose Tick
        # Locator depending on the range of data.
        if self.max_latency - self.min_latency < 100:
            ax.set_major_locator(MaxNLocator(nbins=5, steps=[1, 2, 3, 4, 5],
                                             min_n_ticks=4))
            plot.minorticks_off()
        else:
            ax.set_major_locator(LogLocator())

        # Format the ticks and enable grid
        ax.set_minor_formatter(FormatStrFormatter("%.2f"))
        ax.set_major_formatter(FormatStrFormatter("%.2f"))
        plot.tick_params(axis='x', which='both', labelsize='xx-small',
                         labelrotation=45)
        plot.grid(b=True, which='both', axis='x', linewidth=0.3)

    def plot(self, title, filename):
        for ax in self.fig.get_axes():
            ax.label_outer()

        self.plots[-1].set_xlabel(self.xlabel)
        plt.tight_layout(pad=1.5)
        self.fig.suptitle(title, y=0.99)
        self.fig.savefig(filename, dpi=300)
        plt.close()


class RunSequencePlot:
    def __init__(self, data):
        self.data = data
        self.colour_masks = [
                {'mask': np.full_like(self.data[1], True, dtype=bool),
                    'colour': 'C0'}]

    def _format_xtick(self, x, pos):
        return x / 1000000

    def _plot_x_label(self, axis):
        xaxis = axis.get_xaxis()

        if isinstance(self.data[0], np.ndarray):
            xaxis.set_major_formatter(FuncFormatter(self._format_xtick))
            axis.set_xlabel('Iterations (millions)', fontsize='x-small')
        elif np.issubdtype(self.data[0], np.datetime64):
            xaxis_fmt = mdates.DateFormatter("%H:%M:%S")
            xaxis.set_major_formatter(xaxis_fmt)
            axis.set_xlabel('Time (hh:mm:ss)', fontsize='x-small')
            axis.tick_params('x', labelrotation=90)
            plt.subplots_adjust(bottom=0.2)
        else:
            raise Exception('Unknown indices type')

        xaxis.set_minor_locator(AutoMinorLocator())
        xaxis.set_major_locator(MaxNLocator(nbins='auto', prune='upper'))

    def _plot_y_label(self, axis):
        axis.set_ylabel('Latency (us)', fontsize='x-small')
        axis.tick_params(labelsize='xx-small')
        axis.margins(x=0)

    def _plot_scatter(self, axis, indices, values):
        for mask in self.colour_masks:
            axis.plot(indices[mask['mask']], values[mask['mask']], marker='.',
                      markersize=1, linestyle='', c=mask['colour'],
                      rasterized=True)

    def _plot_histogram(self, axis, values):
        hist, edges = np.histogram(values, bins='sqrt')
        axis.fill_betweenx(edges[:-1], hist, color='#9ec0ff',
                           antialiased=False, rasterized=True)
        axis.set_yticks([])
        axis.set_xscale('log')
        axis.set_xlim(left=0.9, right=len(values))
        axis.minorticks_on()
        axis.tick_params(labelsize='xx-small')
        axis.grid(True, which='both', axis='x', linewidth=0.3)
        axis.set_xlabel('Frequency', fontsize='x-small')

    def plot(self, title, filename):
        fig, axes = plt.subplots(1, 2, gridspec_kw={'width_ratios': [2, 1],
                                                    'wspace': 0.01})

        indices = self.data[0]
        values = self.data[1]

        self._plot_x_label(axes[0])
        self._plot_y_label(axes[0])
        self._plot_scatter(axes[0], indices, values)
        self._plot_histogram(axes[1], values)

        fig.suptitle(title, fontsize=8)
        plt.savefig(filename, dpi=300)
        plt.close()


class RunSequenceGroupPlot(RunSequencePlot):
    def __init__(self, data_list):
        self.data_list = data_list
        self.colour_masks = dict()
        for data in self.data_list:
            self.colour_masks[data[0]] = [
                    {'mask': np.full_like(data[2], True, dtype=bool),
                        'colour': 'C0'}]

    def plot(self, title, filename):
        fig, axes = plt.subplots(len(self.data_list), 2,
                                 gridspec_kw={'width_ratios': [2, 1],
                                              'wspace': 0.01})
        if not isinstance(axes[0], np.ndarray):
            axes = np.array([axes])

        # We'll lie to parent that colour_masks is a simple array of masks
        all_colour_masks = self.colour_masks
        for (ax, data) in zip(axes, self.data_list):
            self.data = data[1:]

            name = data[0]
            indices = data[1]
            values = data[2]

            # Here we lie
            self.colour_masks = all_colour_masks[data[0]]

            self._plot_x_label(ax[0])
            self._plot_y_label(ax[0], f'{name} (us)')
            self._plot_scatter(ax[0], indices, values)
            self._plot_histogram(ax[1], values)

        # Undo the lie
        self.colour_masks = all_colour_masks

        for ax in fig.get_axes():
            ax.label_outer()

        fig.suptitle(title, fontsize=8)
        plt.savefig(filename, dpi=300)
        plt.close()

    def _plot_y_label(self, axis, label):
        axis.set_ylabel(label, fontsize='x-small')
        axis.tick_params(labelsize='xx-small')
        axis.margins(x=0)
