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
Author: Keqian Zhu
Create: 2022-06-08
Description: This file is used for network qos management
"""
# @code

import os
import atexit
import subprocess

from data_collector.guestinfo import GuestInfo
from logger import LOGGER
import util

NET_CGRP_PATH = "/sys/fs/cgroup/net_cls/low_prio_machine.slice"
PID_CGRP_PATH = "/sys/fs/cgroup/pids/low_prio_machine.slice"


class NetController:
    def __init__(self):
        self.enable_management = os.getenv("NET_QOS_MANAGEMENT", "false").lower()
        self.bandwidth_low = os.getenv("NET_QOS_BANDWIDTH_LOW", "20MB").lower()
        self.bandwidth_high = os.getenv("NET_QOS_BANDWIDTH_HIGH", "1GB").lower()
        self.water_line = os.getenv("NET_QOS_WATER_LINE", "20MB").lower()

    def init_net_controller(self):
        if not self.enable_management == "true":
            LOGGER.info("Net QoS Management is configured as disabled.")
            return

        atexit.register(self.__finalize_net_controller)
        self.__enable_net_devs()
        self.__set_cgroup_priority()
        self.__set_low_prio_bandwidth()
        self.__set_high_prio_waterline()

    def domain_updated(self, dom, guest_info: GuestInfo):
        if not self.enable_management == "true":
            return

        if dom.ID() in guest_info.low_prio_vm_dict:
            self.__net_add_vm_pids(guest_info.vm_dict[dom.ID()].cgroup_name)

    def __finalize_net_controller(self):
        self.__bwmcli("-d")

    def __enable_net_devs(self):
        nics_all = os.listdir("/sys/class/net")
        nics_vir = os.listdir("/sys/devices/virtual/net")
        nics_phy = set(nics_all) - set(nics_vir)
        if len(nics_phy) == 0:
            LOGGER.error("No physical NIC found, Net QoS management is not able to start.")
            raise OSError
        for nic in nics_phy:
            self.__bwmcli("-e", nic)

    @staticmethod
    def __net_add_vm_pids(cgrp_name):
        tasks_path = os.path.join(PID_CGRP_PATH, cgrp_name, "tasks")
        if not os.access(tasks_path, os.R_OK):
            LOGGER.warning("The path %s is not readable, please check." % tasks_path)
            return
        with open(tasks_path) as tasks:
            for task in tasks:
                util.file_write(os.path.join(NET_CGRP_PATH, "tasks"), task)

    def __set_cgroup_priority(self):
        if not os.path.exists(NET_CGRP_PATH):
            os.mkdir(NET_CGRP_PATH)
        self.__bwmcli("-s", NET_CGRP_PATH, "-1")

        with os.scandir(PID_CGRP_PATH) as it:
            for entry in it:
                if entry.is_file():
                    continue
                self.__net_add_vm_pids(entry.name)

    def __set_low_prio_bandwidth(self):
        bandwidth_range = "%s,%s" % (self.bandwidth_low, self.bandwidth_high)
        self.__bwmcli("-s", "bandwidth", bandwidth_range);
        LOGGER.info("The bandwidth range of low priority VMs is set to %s" % bandwidth_range)

    def __set_high_prio_waterline(self):
        self.__bwmcli("-s", "waterline", self.water_line);
        LOGGER.info("The water line of high priority VMs is set to %s" % self.water_line)

    @staticmethod
    def __bwmcli(*args):
        bwmcli_path = "/usr/bin/bwmcli"
        if not os.access(bwmcli_path, os.X_OK):
            LOGGER.error("The bwmcli tool is not found or not executable.")
            raise IOError

        child = subprocess.Popen([bwmcli_path] + list(args),
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT)
        outs = child.communicate(timeout=5)[0]
        if child.returncode:
            LOGGER.error("Failed to execute bwmcli command %s" % str(args))
            LOGGER.error("The output: %s" % str(outs))
            raise OSError
