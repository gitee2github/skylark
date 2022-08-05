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
Author: Dongxu Sun
Create: 2022-05-30
Description: This file is used for control CACHE/MBW of low priority vms
"""
# @code

import os
import errno

import util
from logger import LOGGER
from data_collector.guestinfo import GuestInfo
from data_collector.hostinfo import ResctrlInfo

LOW_VMS_RESGROUP_PATH = "/sys/fs/resctrl/low_prio_machine"
LOW_VMS_PID_CGRP_PATH = "/sys/fs/cgroup/pids/low_prio_machine.slice"
LOW_MBW_INIT_FLOOR = 0.1
LOW_MBW_INIT_CEIL = 0.2
LOW_CACHE_INIT_FLOOR = 1
LOW_CACHE_INIT_CEIL = 3


class ResgroupFileOperations:
    """File operations for resctrl group"""
    @staticmethod
    def create_group_dir(resgroup_path: str):
        LOGGER.info("Make resctrl group dir: %s" % resgroup_path)
        try:
            os.makedirs(resgroup_path, exist_ok=True)
        except OSError as e:
            if e.errno == errno.ENOSPC:
                LOGGER.error("Create group dir failed, out of closids/RMIDs")
            raise OSError


class CacheMBWController:
    def __init__(self):
        self.dynamic_control = False
        self.low_vms_alloc = None
        self.low_vms_init_cache_alloc = None
        self.low_vms_init_mbw_alloc = None

    def init_cachembw_controller(self, resctrl_info: ResctrlInfo):
        ResgroupFileOperations.create_group_dir(LOW_VMS_RESGROUP_PATH)
        self.__get_low_init_alloc(resctrl_info)
        self.set_low_init_alloc(resctrl_info)
        with os.scandir(LOW_VMS_PID_CGRP_PATH) as it:
            for entry in it:
                if entry.is_file():
                    continue
                self.__add_vm_pids(entry.name)

    def __get_low_init_alloc(self, resctrl_info: ResctrlInfo):
        low_vms_mbw_init = float(os.getenv("MIN_MBW_LOW_VMS"))
        if not LOW_MBW_INIT_FLOOR <= low_vms_mbw_init <= LOW_MBW_INIT_CEIL:
            LOGGER.error("Invalid environment variables: MIN_MBW_LOW_VMS")
            raise Exception
        low_vms_cache_init = int(os.getenv("MIN_LLC_WAYS_LOW_VMS"))
        if not LOW_CACHE_INIT_FLOOR <= low_vms_cache_init <= LOW_CACHE_INIT_CEIL:
            LOGGER.error("Invalid environment variables: MIN_LLC_WAYS_LOW_VMS")
            raise Exception
        mbw_gran = resctrl_info.mbw_gran
        mbw_min = resctrl_info.mbw_min
        max_cache_ways = resctrl_info.max_cache_ways
        if low_vms_cache_init >= max_cache_ways:
            LOGGER.error("Cache ways: %d, low_vms_cache_init: %d" %
                         (max_cache_ways, low_vms_cache_init))
            raise Exception
        low_vms_cache_bit_mask = \
            "0" * (max_cache_ways - low_vms_cache_init) + "1" * low_vms_cache_init
        self.low_vms_init_cache_alloc = hex(int(low_vms_cache_bit_mask, 2))[2:]
        if mbw_gran == 0:
            LOGGER.error("Found mbw_gran == 0, skylark exit...")
            raise Exception
        low_vms_env_mbw = int((low_vms_mbw_init * 100) // mbw_gran) * mbw_gran
        self.low_vms_init_mbw_alloc = str(max(low_vms_env_mbw, mbw_min))
        LOGGER.info("Get low vm init alloc, cache: %s, mbw: %s" %
                    (self.low_vms_init_cache_alloc, self.low_vms_init_mbw_alloc))

    def set_low_init_alloc(self, resctrl_info: ResctrlInfo):
        self.__set_low_cache_alloc(resctrl_info, self.low_vms_init_cache_alloc)
        self.__set_low_mbw_alloc(resctrl_info, self.low_vms_init_mbw_alloc)

    @staticmethod
    def __set_low_cache_alloc(resctrl_info: ResctrlInfo, cache_alloc: str):
        schemata_l3_alloc = "L3:"
        for id in range(resctrl_info.id_num):
            schemata_l3_alloc += "%d=%s;" % (id, cache_alloc)
        schemata_l3_alloc += "\n"
        util.file_write(os.path.join(
            LOW_VMS_RESGROUP_PATH, "schemata"), schemata_l3_alloc)

    @staticmethod
    def __set_low_mbw_alloc(resctrl_info: ResctrlInfo, mbw_alloc: str):
        schemata_mbw_alloc = "MB:"
        for id in range(resctrl_info.id_num):
            schemata_mbw_alloc += "%d=%s;" % (id, mbw_alloc)
        schemata_mbw_alloc += "\n"
        util.file_write(os.path.join(
            LOW_VMS_RESGROUP_PATH, "schemata"), schemata_mbw_alloc)

    def domain_updated(self, domain, guest_info: GuestInfo):
        if domain.ID() in guest_info.low_prio_vm_dict:
            self.__add_vm_pids(guest_info.vm_dict[domain.ID()].cgroup_name)

    @staticmethod
    def __add_vm_pids(vm_cgrp_name):
        tasks_path = os.path.join(LOW_VMS_PID_CGRP_PATH, vm_cgrp_name, "tasks")
        if not os.access(tasks_path, os.R_OK):
            LOGGER.warning(
                "The path %s is not readable, please check." % tasks_path)
            return
        LOGGER.info("Add %s pids to %s" %
                    (vm_cgrp_name, os.path.join(LOW_VMS_RESGROUP_PATH, "tasks")))
        try:
            with open(tasks_path) as tasks:
                for task in tasks:
                    util.file_write(os.path.join(LOW_VMS_RESGROUP_PATH, "tasks"), task)
        except IOError as e:
            LOGGER.error("Failed to add VM(%s) pids to resctrl: %s" % (vm_cgrp_name, str(e)))
            # If the VM doesn't stop, raise exception.
            if os.access(tasks_path, os.F_OK):
                raise
