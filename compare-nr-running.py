#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Create heatmap and find imbalances from recorded
sched_update_nr_running events with trace-cmd.
Copyright (C) 2019  Jiri Vozar

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import argparse
from datetime import datetime, timedelta
import math
import sys
import re

import numpy as np
import matplotlib
#matplotlib.use('agg')  # Make it work also on machines without tkinter
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib import collections as mc
from matplotlib.ticker import MultipleLocator

def draw_report(title, time_axis0, map_values0, differences0, imbalances0, sums0, time_axis1, map_values1, differences1, imbalances1, sums1, image_file=None, numa_cpus={}):
    # Transpose heat map data to right axes
    map_values0 = np.array(map_values0)[:-1, :].transpose()
    map_values1 = np.array(map_values1)[:-1, :].transpose()

    # Group CPU lines by NUMA nodes
    if numa_cpus:
        new_order = []
        for k, v in numa_cpus.items():
            new_order += v
        map_values0 = map_values0[new_order]
        map_values1 = map_values1[new_order]

    # Add blank row to correctly plot all rows with data
    map_values0 = np.vstack((map_values0, np.zeros(map_values0.shape[1])))
    map_values1 = np.vstack((map_values1, np.zeros(map_values1.shape[1])))

    cmap = ListedColormap(['#000000', '#305090', '#40b080', '#f0e020', '#f04010'])
    boundaries = [-0.5, 0.5, 1.5, 2.5, 3.5, 4.5]
    norm = BoundaryNorm(boundaries, cmap.N, clip=True)

    fig, axs = plt.subplots(nrows=4, ncols=1, gridspec_kw=dict(height_ratios=[4, 4, 1, 2]),
                            figsize=(20, 15), sharex=True) # , constrained_layout=True)
    fig.subplots_adjust(hspace=0.1)

    # Draw the main heat map
    x_grid0, y_grid0 = np.meshgrid(time_axis0, range(len(map_values0)))
    mesh0 = axs[0].pcolormesh(x_grid0, y_grid0, map_values0, vmin=0, vmax=4, cmap=cmap, norm=norm)

    axs[0].set_xlim(min(time_axis0[0], time_axis1[0]), max(time_axis0[-1], time_axis1[-1]))
    axs[0].set_ylim([0, map_values0.shape[0] - 1])

    cmap1 = ListedColormap(['#000000', '#305090', '#40b080', '#f0e020', '#f04010'])
    norm1 = BoundaryNorm(boundaries, cmap1.N, clip=True)

    x_grid1, y_grid1 = np.meshgrid(time_axis1, range(len(map_values1)))
    mesh1 = axs[1].pcolormesh(x_grid1, y_grid1, map_values1, vmin=0, vmax=4, cmap=cmap1, norm=norm1)

    axs[1].set_xlim(min(time_axis0[0], time_axis1[0]), max(time_axis0[-1], time_axis1[-1]))
    axs[1].set_ylim([0, map_values1.shape[0] - 1])

    # Create colorbar
    cbar = fig.colorbar(mesh0, cax=plt.axes([0.95, 0.05, 0.02, 0.9]),
                        extend='max', ticks=range(5))
    cbar.ax.set_yticklabels(['0', '1', '2', '3', '4+'])
    plt.subplots_adjust(bottom=0.05, right=0.9, top=0.95, left=0.05)

    # Draw line with differences
    axs[2].step(time_axis0, differences0, where='post', color='green', alpha=0.8)
    axs[2].step(time_axis1, differences1, where='post', color='blue', alpha=0.8)

    # Draw imbalances
    for i in imbalances0:
        axs[2].plot(i[0][0], i[0][1], 'rx')
    lc = mc.LineCollection(imbalances0,
                           colors=np.tile((1, 0, 0, 1), (len(imbalances0), 1)),
                           linewidths=2)
    axs[2].add_collection(lc)
    for i in imbalances1:
        axs[2].plot(i[0][0], i[0][1], 'rx')
    lc = mc.LineCollection(imbalances1,
                           colors=np.tile((1, 0, 0, 1), (len(imbalances1), 1)),
                           linewidths=2)
    axs[2].add_collection(lc)

    # Draw line with sums
    axs[3].step(time_axis0, sums0, where='post', color='green', alpha=0.8)
    axs[3].step(time_axis1, sums1, where='post', color='blue', alpha=0.8)

    axs[0].set_ylabel("CPUs")
    axs[1].set_ylabel("CPUs")
    axs[2].set_ylabel("Max difference")
    axs[3].set_ylabel("Sum of tasks")
    axs[3].set_xlabel("Timestamp (seconds)")

    axs[2].set_ylim(ymin=0)
    axs[2].set_xlim(min(time_axis0[0], time_axis1[0]), max(time_axis0[-1], time_axis1[-1]))
    axs[2].grid()
    axs[3].set_ylim(ymin=0)
    axs[3].set_xlim(min(time_axis0[0], time_axis1[0]), max(time_axis0[-1], time_axis1[-1]))
    axs[3].grid()

    # Separate CPUs with lines by NUMA nodes
    if numa_cpus:
        plt.sca(axs[0])
        axs[0].grid(True, which='major', axis='y', linestyle='--', color='w')
        axs[0].yaxis.set_minor_locator(MultipleLocator(1))
        plt.yticks(range(0, map_values0.shape[0] - 1, len(numa_cpus[0])),
                   map(lambda x: "Node " + str(x), range(len(numa_cpus.keys()))))

        plt.sca(axs[1])
        axs[1].grid(True, which='major', axis='y', linestyle='--', color='w')
        axs[1].yaxis.set_minor_locator(MultipleLocator(1))
        plt.yticks(range(0, map_values1.shape[0] - 1, len(numa_cpus[0])),
                   map(lambda x: "Node " + str(x), range(len(numa_cpus.keys()))))
    else:
        plt.sca(axs[0])
        axs[0].set_yticks(range(map_values0.shape[0] - 1))
        plt.sca(axs[1])
        axs[1].set_yticks(range(map_values1.shape[0] - 1))

    plt.sca(axs[0])
    plt.title(title)

    if image_file:
        plt.savefig(image_file)
    else:
        plt.show()


def read_nodes(lscpu_file):
    numa_cpus = {}
    for line in lscpu_file:
        # Find number of CPUs and NUMA nodes:
        if line[:7] == 'CPU(s):':
            cpu_nb = int(line[7:])
        elif line[:13] == 'NUMA node(s):':
            nodes_nb = int(line[13:])

        # Find NUMA nodes associated with CPUs:
        elif line[:9] == 'NUMA node':
            words = line.split()
            cpus = words[-1].split(',')
            for cpu in cpus:
                if '-' in cpu:
                    w = cpu.split('-')
                    for i in range(int(w[0]), int(w[1]) + 1):
                        numa_cpus.setdefault(int(words[1][4:]), []).append(i)
                else:
                    numa_cpus.setdefault(int(words[1][4:]), []).append(int(cpu))

    return numa_cpus


def process_report(title, input_file, sampling, threshold, duration, ebpf_file=False, image_file=None, numa_cpus={}):
    cpus_count = 0
    time_axis = []
    map_values = []
    differences = []
    imbalances = []
    sums = []
    counter = 0

    if ebpf_file:
        if numa_cpus:
            cpus_count = max(numa_cpus[max(numa_cpus.keys())]) + 1
        else:
            print("lscpu file is needed for eBPF input")
            exit(1)
    else:
        cpus_count = int(input_file.readline().split('=')[1])

    last_row = np.zeros(cpus_count)
    map_values.append(last_row)

    last_imbalance_start = 0
    point_time = 0
    start_time = -1

    if ebpf_file:
        reg_exp=re.compile(r"^.*-([0-9]+).*\[([0-9]+)\] ([0-9]+): sched_nr_running: nr_running=([0-9]+)$")
    else:
        reg_exp=re.compile(r"^.*-(\d+).*\s(\d+[.]\d+): sched_update_nr_running: cpu=(\d+) .*nr_running=(\d+)")

    for line in input_file:
        match = reg_exp.findall(line)

        # Check the correct event
        if len(match) != 1:
            continue

        pid = int(match[0][0])
        if ebpf_file:
            point_time = float(match[0][2]) / 1_000_000_000.0
            cpu = int(match[0][1])
        else:
            point_time = float(match[0][1])
            cpu = int(match[0][2])
        value = int(match[0][3])
        if pid == 0:
            if value > 0:
                value -= 1

        if start_time < 0:
            start_time += point_time
        point_time -= start_time

        row = np.copy(last_row)
        row[cpu] = value
        row_min = min(row)
        row_max = max(row)
        diff = row_max - row_min

        # Check the start of imbalance
        if diff >= threshold and last_imbalance_start == 0:
            last_imbalance_start = point_time
        if diff < threshold and last_imbalance_start != 0:
            # Print and store long imbalances
            if (point_time - last_imbalance_start) >= duration:
                imbalances.append([(last_imbalance_start, threshold),
                                    (point_time, threshold)])
                print(f"Imbalance from timestamp {last_imbalance_start}"
                f" lasting {point_time - last_imbalance_start} seconds")
            last_imbalance_start = 0

        # Store plotting data with optional sampling
        counter += 1
        if counter >= sampling:
            counter = 0
            map_values.append(row)
            differences.append(diff)
            sums.append(sum(row))
            time_axis.append(point_time)
        last_row = row

    # Check for unreported imbalance lasting to the very end of input
    if last_imbalance_start != 0 \
       and (point_time - last_imbalance_start) >= duration:
        imbalances.append([(last_imbalance_start, threshold),
                            (point_time, threshold)])
        print(f"Imbalance from timestamp {last_imbalance_start}"
        f" lasting {point_time - last_imbalance_start} seconds")

    if not imbalances:
        print("No imbalance found")

    #draw_report(title, time_axis, map_values, differences, imbalances, sums, image_file, numa_cpus)
    return time_axis, map_values, differences, imbalances, sums


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Create heatmap and find"
        " imbalances from recorded sched_update_nr_running events with trace-cmd.")
    parser.add_argument("input_file0", nargs="?", type=argparse.FileType('r'), default=sys.stdin)
    parser.add_argument("input_file1", nargs="?", type=argparse.FileType('r'), default=sys.stdin)
    parser.add_argument("--sampling", default=1, type=int,
                        help="Sampling of plotted data to reduce drawing point_time")
    parser.add_argument("--threshold", default=2, type=int,
                        help="Minimal difference of process count considered as imbalance")
    parser.add_argument("--duration", default=0.05, type=float,
                        help="Minimal duration of imbalance worth reporting")
    parser.add_argument('--ebpf', action='store_true',
                        help='Expect output from eBPF script instad of trace-cmd'
                        ' (requires lscpu file)')
    parser.add_argument("--image-file", type=str, default=None,
                        help="Save plotted heatmap to file instead of showing")
    parser.add_argument("--lscpu-file", type=argparse.FileType('r'), default=None,
                        help="File with output of lscpu from observed machine")
    parser.add_argument("--name", type=str, default=None,
                        help="Filename to be displayed in graph. Usefull when reading input from stdin.")

    try:
        args = parser.parse_args()
    except SystemExit:
        sys.exit(1)

    numa_cpus = {}
    if args.lscpu_file:
        numa_cpus = read_nodes(args.lscpu_file)

    method = "eBPF" if args.ebpf else "trace-cmd"

    if args.name:
        title = "Plot of '" + args.name + "' produced with " + method
    else:
        title = "Plot of '" + args.input_file0.name + "' produced with " + method

    if args.input_file0.name.endswith(".xz"):
        args.input_file0.close()
        import lzma
        with lzma.open(args.input_file0.name, 'rt') as decompressed:
            time_axis0, map_values0, differences0, imbalances0, sums0 = \
            process_report(title, decompressed, args.sampling, args.threshold,
                           args.duration, args.ebpf, args.image_file, numa_cpus)
    else:
        time_axis0, map_values0, differences0, imbalances0, sums0 = \
        process_report(title, args.input_file0, args.sampling, args.threshold,
                       args.duration, args.ebpf, args.image_file, numa_cpus)

    if args.input_file1.name.endswith(".xz"):
        args.input_file1.close()
        import lzma
        with lzma.open(args.input_file1.name, 'rt') as decompressed:
            time_axis1, map_values1, differences1, imbalances1, sums1 = \
            process_report(title, decompressed, args.sampling, args.threshold,
                           args.duration, args.ebpf, args.image_file, numa_cpus)
    else:
        time_axis1, map_values1, differences1, imbalances1, sums1 = \
        process_report(title, args.input_file1, args.sampling, args.threshold,
                       args.duration, args.ebpf, args.image_file, numa_cpus)

    draw_report(title, time_axis0, map_values0, differences0, imbalances0, sums0, time_axis1, map_values1, differences1, imbalances1, sums1, args.image_file, numa_cpus)