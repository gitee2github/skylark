#! /usr/bin/python
# coding=UTF-8
"""
Copyright (c) Huawei Technologies Co., Ltd. 2022. All rights reserved.
skylark licensed under the Mulan PSL v2.
You can use this software according to the terms and conditions of the Mulan PSL v2.
You may obtain a copy of Mulan PSL v2 at:
    http://license.coscl.org.cn/MulanPSL2
THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
PURPOSE.
See the Mulan PSL v2 for more details.
Author: Jinhao Gao
Create: 2022-05-30
Description: This file is used for providing a power analyzer
"""
# @code

import os

from logger import LOGGER
from qos_controller import cpucontroller


class PowerAnalyzer:
    def __init__(self):
        self.underclocking_dict = {}
        self.power_hotspot_dict = {}
        self.freq_threshold = 0
        self.tdp_threshold = 0
        self.package_tdp_threshold = {}
        self.abnormal_threshold = 0
        self.quota_threshold = 0
        self.qos_controller = cpucontroller.CpuController()

    def set_hotspot_threshold(self, data_collector):
        self.tdp_threshold = float(os.getenv("TDP_THRESHOLD"))
        self.freq_threshold = float(os.getenv("FREQ_THRESHOLD"))
        self.abnormal_threshold = int(os.getenv("ABNORMAL_THRESHOLD"))
        self.quota_threshold = float(os.getenv("QUOTA_THRESHOLD"))
        self.__check_threshold_validity()

        self.freq_threshold = float(os.getenv("FREQ_THRESHOLD")) * data_collector.host_info.cpu_turbofreq_mhz
        LOGGER.info("Frequency threshold is %.2f, abnormal times threshold is %d, bandwidth threshold is %.2f"
                    % (self.freq_threshold, self.abnormal_threshold, self.quota_threshold))

        for package in data_collector.host_info.host_topo.package_set:
            self.package_tdp_threshold[package] = self.tdp_threshold * \
                                          data_collector.host_info.cpu_tdp_watt[package]
            LOGGER.info("Package %d tdp threshold is %.2fW" % (package, self.package_tdp_threshold.get(package)))

    def power_manage(self, data_collector, qos_controller):
        self.__power_analysis(data_collector.host_info)

        for package in self.power_hotspot_dict:
            if self.power_hotspot_dict.get(package):
                self.__usage_analysis(data_collector.host_info.host_topo,
                                      data_collector.guest_info, package, qos_controller)

        qos_controller.check_adjust_recover_list(data_collector.guest_info)
        qos_controller.limit_domain_bandwidth(data_collector.guest_info,
                                              self.quota_threshold, self.abnormal_threshold)
        qos_controller.recovery_domain_bandwidth(data_collector.guest_info)
        qos_controller.refresh_adjust_recover_list()

    def __power_analysis(self, host_info):
        self.power_hotspot_dict.clear()
        self.underclocking_dict.clear()

        package_energy_dict = host_info.old_host_status_data.package_data_dict
        for package in package_energy_dict:
            package_id = package_energy_dict.get(package).package_id
            if package_energy_dict.get(package).energy_watt > self.package_tdp_threshold.get(package):
                self.underclocking_dict[package_id] = []
                self.power_hotspot_dict[package_id] = True
                for cpu in host_info.old_host_status_data.cpu_data_list:
                    if cpu.package_id == package_energy_dict.get(package).package_id and \
                            cpu.curr_freq < self.freq_threshold:
                        self.underclocking_dict.get(package_id).append(cpu.cpu_id)
                LOGGER.info("Package %d underclocking cpu list is %s"
                            % (package, self.underclocking_dict.get(package_id)))
            else:
                self.power_hotspot_dict[package_id] = False
        LOGGER.info("Package power hotspot list is %s" % self.power_hotspot_dict)

    def __usage_analysis(self, host_topo, guest_info, package_id, qos_controller):
        package_domain_set = set()
        package_domain_usage_dict = dict()
        if len(self.underclocking_dict.get(package_id)) != 0:
            for cpu in self.underclocking_dict.get(package_id):
                guest_info.running_domain_in_cpus[cpu].sort(reverse=True)
                for domain in guest_info.running_domain_in_cpus[cpu]:
                    if domain[3] == 1 and domain[0] != 0:
                        qos_controller.domain_adjust_dict[domain[1]] = self.abnormal_threshold
                        LOGGER.debug("Domain %s(%d) usage on CPU%d is %f"
                                     % (domain[2], domain[1], cpu, domain[0]))
                        break
        else:
            for cpu in range(host_topo.max_cpu_nums):
                if host_topo.cpu_topo_list[cpu] == package_id:
                    for domain in guest_info.running_domain_in_cpus[cpu]:
                        if domain[3] == 1 and domain[0] != 0:
                            package_domain_set.add(domain[1])
            for domain in package_domain_set:
                package_domain_usage_dict[domain] = guest_info.vm_dict[domain].package_usage_dict.get(package_id)
            package_domain_usage_list = sorted(package_domain_usage_dict.items(),
                                               key=lambda x: x[1], reverse=True)
            abnormal_vm_counts = 3
            for domain in package_domain_usage_list:
                if not abnormal_vm_counts:
                    break
                qos_controller.domain_adjust_dict[domain[0]] = self.abnormal_threshold
                abnormal_vm_counts -= 1

    def __check_threshold_validity(self):
        tdp_threshold_range = (0.8, 1)
        freq_threshold_range = (0.9, 1)
        quota_threshold_range = (0.8, 1)
        abnormal_threshold_range = (1, 5)

        if self.tdp_threshold < tdp_threshold_range[0] or \
                self.tdp_threshold > tdp_threshold_range[1] or \
                self.freq_threshold < freq_threshold_range[0] or \
                self.freq_threshold > freq_threshold_range[1] or \
                self.quota_threshold < quota_threshold_range[0] or \
                self.quota_threshold > quota_threshold_range[1] or \
                self.abnormal_threshold < abnormal_threshold_range[0] or \
                self.abnormal_threshold > abnormal_threshold_range[1]:
            LOGGER.error("Threshold parameter is invalid.")
            raise ValueError
