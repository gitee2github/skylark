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
Description: This file is used for providing a CPU QoS controller
"""
# @code

import os

from logger import LOGGER
import util

LOW_PRIORITY_SLICES_PATH = "/sys/fs/cgroup/cpu/low_prio_machine.slice"
LOW_PRIORITY_QOS_LEVEL = -1
OVERLOAG_DETECT_PERIOD_PATH = "/proc/sys/kernel/qos_overload_detect_period_ms"
OVERLOAG_DETECT_PERIOD_MS = 100
OFFLINE_WAIT_INTERVAL_PATH = "/proc/sys/kernel/qos_offline_wait_interval_ms"
OFFLINE_WAIT_INTERVAL_MS = 100
MIN_QUOTA_US = 0


class CpuController:
    def __init__(self):
        self.domain_adjust_dict = {}
        self.domain_recovery_list = []

    @staticmethod
    def set_low_priority_cgroup():
        qos_level_path = os.path.join(LOW_PRIORITY_SLICES_PATH, "cpu.qos_level")
        try:
            util.file_write(qos_level_path, str(LOW_PRIORITY_QOS_LEVEL))
            util.file_write(OVERLOAG_DETECT_PERIOD_PATH, str(OVERLOAG_DETECT_PERIOD_MS))
            util.file_write(OFFLINE_WAIT_INTERVAL_PATH, str(OFFLINE_WAIT_INTERVAL_MS))
        except IOError as error:
            LOGGER.error("Failed to configure CPU QoS for low priority VMs: %s" % str(error))
            raise

    def limit_domain_bandwidth(self, guest_info, quota_threshold, abnormal_threshold):
        global MIN_QUOTA_US
        period_path = os.path.join(LOW_PRIORITY_SLICES_PATH, "cpu.cfs_period_us")
        cfs_period_us = int(util.file_read(period_path))
        MIN_QUOTA_US = 0.9 * cfs_period_us
        vm_slices_path = LOW_PRIORITY_SLICES_PATH

        for domain_id in self.domain_adjust_dict:
            if self.domain_adjust_dict.get(domain_id) == abnormal_threshold:
                domain = guest_info.low_prio_vm_dict.get(domain_id)
                domain_quota_us = int(domain.domain_usage * cfs_period_us * quota_threshold)
                if domain_quota_us < MIN_QUOTA_US:
                    continue

                quota_path = os.path.join(vm_slices_path, domain.cgroup_name, "cpu.cfs_quota_us")

                try:
                    util.file_write(quota_path, str(domain_quota_us), log=False)
                except IOError as error:
                    # If VM doesn't stop, raise exception.
                    if os.access(quota_path, os.F_OK):
                        LOGGER.error("Failed to limit domain %s(%d) cpu bandwidth: %s"
                                     % (domain.domain_name, domain.domain_id, str(error)))
                        raise
                else:
                    LOGGER.info("Domain %s(%d) cpu bandwidth was limitted to %s"
                                % (domain.domain_name, domain.domain_id, domain_quota_us))

    def recovery_domain_bandwidth(self, guest_info):
        vm_slices_path = LOW_PRIORITY_SLICES_PATH

        for domain_id in self.domain_recovery_list:
            domain = guest_info.low_prio_vm_dict.get(domain_id)
            initial_bandwidth = domain.global_quota_config
            quota_path = os.path.join(vm_slices_path, domain.cgroup_name, "cpu.cfs_quota_us")

            try:
                util.file_write(quota_path, str(initial_bandwidth), log=False)
            except IOError as error:
                # If VM doesn't stop, raise exception.
                if os.access(quota_path, os.F_OK):
                    LOGGER.error("Failed to recovery domain %s(%d) cpu bandwidth: %s!"
                                 % (domain.domain_name, domain.domain_id, str(error)))
                    raise
            else:
                LOGGER.info("Domain %s(%d) cpu bandwidth was recoveried to %s"
                            % (domain.domain_name, domain.domain_id, initial_bandwidth))

    def reset_domain_bandwidth(self, guest_info):
        vm_slices_path = LOW_PRIORITY_SLICES_PATH

        for domain_id in guest_info.low_prio_vm_dict:
            domain = guest_info.low_prio_vm_dict.get(domain_id)
            initial_bandwidth = domain.global_quota_config
            quota_path = os.path.join(vm_slices_path, domain.cgroup_name, "cpu.cfs_quota_us")
            try:
                util.file_write(quota_path, str(initial_bandwidth), log=False)
            except IOError:
                if os.access(quota_path, os.F_OK):
                    LOGGER.error("Failed to reset domain %s(%d) cpu bandwidth to its initial bandwidth %s!"
                                 % (domain.domain_name, domain.domain_id, initial_bandwidth))
            else:
                LOGGER.info("Domain %s(%d) cpu bandwidth was reset to %s"
                            % (domain.domain_name, domain.domain_id, initial_bandwidth))

    def check_adjust_recover_list(self, guest_info):
        for domain_id in list(self.domain_adjust_dict):
            if domain_id not in guest_info.low_prio_vm_dict:
                del self.domain_adjust_dict[domain_id]
            elif self.domain_adjust_dict.get(domain_id) == 0:
                del self.domain_adjust_dict[domain_id]
                self.domain_recovery_list.append(domain_id)
        LOGGER.info("The list of adjustment is %s, the list of recovery is %s"
                    % (self.domain_adjust_dict, self.domain_recovery_list))

    def refresh_adjust_recover_list(self):
        self.domain_recovery_list.clear()
        for domain_id in self.domain_adjust_dict:
            self.domain_adjust_dict[domain_id] -= 1
