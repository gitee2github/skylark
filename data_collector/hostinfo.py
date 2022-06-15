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
Description: This file is used for setting and updating of host info
"""
# @code

import atexit
import ctypes
import copy
import os
import subprocess
import re
import time

from data_collector import intelfamily as intel
from data_collector import msrlibrary
from data_collector import msrindex as msr
from logger import LOGGER
import util

SECOND_TO_NANOSECOND = 1000000000
WATT_TO_UWATT = 1000000
INTEL_FAM6_ATOM_SILVERMONT = 0x37
RESCTRLPATH = "/sys/fs/resctrl"


class StructPointer(ctypes.Structure):
    _fields_ = [("aperf", ctypes.c_ulonglong), ("mperf", ctypes.c_ulonglong)]


class HostTopology:
    def __init__(self):
        self.max_package_nums = 0
        self.max_cpu_nums = 0
        self.cpu_topo_list = []
        self.package_set = set()

    @staticmethod
    def get_first_core_in_package(cpu):
        return int(re.split('[-]', util.file_read("/sys/devices/system/cpu/cpu%d/topology/core_siblings_list"
                                                  % cpu))[0])

    @staticmethod
    def __get_physical_package_id(cpu):
        return int(util.file_read("/sys/devices/system/cpu/cpu%d/topology/physical_package_id" % cpu))

    def get_total_cpu(self):
        cpu_present = util.file_read("/sys/devices/system/cpu/present")
        self.max_cpu_nums = int(cpu_present.strip('\n').split('-')[1]) + 1
        LOGGER.info("Max cpu nums is %d" % self.max_cpu_nums)

    def get_cpu_topo(self):
        self.cpu_topo_list = [0] * self.max_cpu_nums
        for cpu in range(self.max_cpu_nums):
            package_id = self.__get_physical_package_id(cpu)
            self.package_set.add(package_id)
            self.cpu_topo_list[cpu] = package_id

        self.max_package_nums = len(self.package_set)

        LOGGER.info("Max package nums is %d" % self.max_package_nums)


class CpuData:
    def __init__(self, cpu_id, package_id):
        self.cpu_id = cpu_id
        self.package_id = package_id
        self.aperf = 0
        self.mperf = 0
        self.curr_freq = 0
        self.cpu_is_first_core_in_package = \
            self.cpu_id == HostTopology.get_first_core_in_package(self.cpu_id)

    def get_cpu_status_data(self, extern_lib, aperf_mperf_multiplier):
        perf_data = StructPointer()
        perf_data.aperf = 0
        perf_data.mperf = 0

        ret = extern_lib.get_cpu_status_data(self.cpu_id, ctypes.byref(perf_data))
        if ret == -1 or perf_data.aperf == 0 or perf_data.mperf == 0:
            LOGGER.error("CPU %d: msr aperf or mperf read failed!", self.cpu_id)
            raise OSError
        elif ret == -2:
            LOGGER.error("CPU %d has jitter", self.cpu_id)
            raise TimeoutError
        else:
            self.aperf = perf_data.aperf * aperf_mperf_multiplier
            self.mperf = perf_data.mperf * aperf_mperf_multiplier


class PackageData:
    def __init__(self, cpu, package):
        self.cpu_id = cpu
        self.package_id = package
        self.energy_pkg = 0
        self.energy_watt = 0
        self.update_time = 0

    def get_energy_data(self, extern_lib):
        self.update_time = time.time_ns()
        self.energy_pkg = extern_lib.get_msr(self.cpu_id, msr.MSR_PKG_ENERGY_STATUS)


class HostStatusData:
    def __init__(self, host_topo):
        self.cpu_data_list = []
        self.package_data_dict = {}

        for cpu in range(host_topo.max_cpu_nums):
            self.cpu_data_list.append(CpuData(cpu, host_topo.cpu_topo_list[cpu]))
            if self.cpu_data_list[cpu].cpu_is_first_core_in_package:
                if self.cpu_data_list[cpu].package_id not in self.package_data_dict:
                    self.package_data_dict[self.cpu_data_list[cpu].package_id] = \
                        PackageData(cpu, host_topo.cpu_topo_list[cpu])

    def get_status_data(self, extern_lib, aperf_mperf_multiplier):
        for cpu in range(len(self.cpu_data_list)):
            self.cpu_data_list[cpu].get_cpu_status_data(extern_lib, aperf_mperf_multiplier)
        for package in self.package_data_dict:
            self.package_data_dict.get(package).get_energy_data(extern_lib)

    def format_status_data(self, old_status_data, base_freq, rapl_energy_unit):
        for cpu in range(len(self.cpu_data_list)):
            LOGGER.debug("CPU %d: Last time aperf was %d, mperf was %d; curr aperf is %d, mperf is %d"
                         % (cpu, old_status_data.cpu_data_list[cpu].aperf,
                            old_status_data.cpu_data_list[cpu].mperf,
                            self.cpu_data_list[cpu].aperf, self.cpu_data_list[cpu].mperf))

            aperf_delta = (self.cpu_data_list[cpu].aperf - old_status_data.cpu_data_list[cpu].aperf)
            mperf_delta = (self.cpu_data_list[cpu].mperf - old_status_data.cpu_data_list[cpu].mperf)
            if mperf_delta != 0:
                self.cpu_data_list[cpu].curr_freq = base_freq * aperf_delta / mperf_delta
            else:
                raise OSError

            LOGGER.debug("The curr_freq of cpu %d is %.2f" % (cpu, self.cpu_data_list[cpu].curr_freq))

        for package in self.package_data_dict:
            update_interval = (self.package_data_dict.get(package).update_time -
                               old_status_data.package_data_dict.get(package).update_time)
            energy_delta = (self.package_data_dict.get(package).energy_pkg -
                            old_status_data.package_data_dict.get(package).energy_pkg)
            if update_interval != 0:
                self.package_data_dict.get(package).energy_watt = energy_delta * rapl_energy_unit / \
                                                              update_interval * SECOND_TO_NANOSECOND
            else:
                LOGGER.error("The update interval is zero!")
                raise OSError
            LOGGER.debug("The power of package %d is %.2f, interval is %.3fs"
                         % (package, self.package_data_dict.get(package).energy_watt, update_interval))
            LOGGER.debug("Last time energy was %d, update time was %d ns,"
                         "curr energy is %d, update_time is %d ns"
                         % (old_status_data.package_data_dict.get(package).energy_pkg,
                            old_status_data.package_data_dict.get(package).update_time,
                            self.package_data_dict.get(package).energy_pkg,
                            self.package_data_dict.get(package).update_time))


class ResctrlInfo:
    def __init__(self):
        self.max_cache_ways = None
        self.min_cache_ways = None
        self.mbw_gran = None
        self.mbw_min = None
        self.id_num = None

    def get_resctrl_infos(self):
        def value_of_subpath(subpath):
            return util.file_read(os.path.join(RESCTRLPATH, subpath))

        cache_allocation_enabled = os.access(
            os.path.join(RESCTRLPATH, "info/L3"), os.R_OK)
        mbw_allocation_enabled = os.access(
            os.path.join(RESCTRLPATH, "info/MB"), os.R_OK)
        if not cache_allocation_enabled or not mbw_allocation_enabled:
            LOGGER.error("Resctrl's cache/mbw allocation disabled, skylark exit")
            raise OSError

        self.max_cache_ways = bin(int(
            value_of_subpath("info/L3/cbm_mask"), 16)).count("1")
        self.min_cache_ways = int(value_of_subpath("info/L3/min_cbm_bits"))
        self.mbw_min = int(value_of_subpath("info/MB/min_bandwidth"))
        self.mbw_gran = int(value_of_subpath("info/MB/bandwidth_gran"))
        self.id_num = len(value_of_subpath("schemata").split(";"))

    @staticmethod
    def mount_resctrl():
        task_path = os.path.join(RESCTRLPATH, "tasks")
        if os.access(task_path, os.W_OK):
            return
        child = subprocess.Popen(
            ["mount", "-t", "resctrl", "resctrl", "/sys/fs/resctrl"])
        child.communicate(timeout=5)
        if not os.access(task_path, os.W_OK):
            LOGGER.error("Mount resctrl failed. skylark exit...")
            raise OSError


class HostInfo:
    def __init__(self):
        self.base_cpu = 0
        self.cpu_basefreq_mhz = 0
        self.cpu_turbofreq_mhz = 0
        self.cpu_tdp_watt = {}
        self.host_topo = HostTopology()
        self.rapl_energy_units = 0
        self.has_aperf = False
        self.aperf_mperf_multiplier = 0
        self.family = 0
        self.model = 0
        self.old_host_status_data = None
        self.turbo_is_enable = False
        self.extern_lib = None
        self.resctrl_info = ResctrlInfo()

    def set_host_attribute(self):
        self.host_topo.get_total_cpu()
        self.host_topo.get_cpu_topo()

        self.extern_lib = msrlibrary.MsrLibrary()
        atexit.register(self.__clear_fd_percpu)
        self.extern_lib.allocate_fd_percpu(self.host_topo.max_cpu_nums)

        self.resctrl_info.mount_resctrl()
        self.resctrl_info.get_resctrl_infos()

        self.__get_cpu_family_model()
        self.__get_cpu_base_freq_mhz()
        self.__get_cpu_turbo_freq_mhz()

        self.__get_cpu_tdp()
        self.__get_rapl_energy_unit()
        self.__check_has_aperf()

        self.old_host_status_data = HostStatusData(self.host_topo)
        self.old_host_status_data.get_status_data(self.extern_lib, self.aperf_mperf_multiplier)

    def update_host_info(self):
        curr_host_status_data = HostStatusData(self.host_topo)

        curr_host_status_data.get_status_data(self.extern_lib, self.aperf_mperf_multiplier)

        curr_host_status_data.format_status_data(self.old_host_status_data, self.cpu_basefreq_mhz,
                                                 self.rapl_energy_units)

        self.old_host_status_data = copy.deepcopy(curr_host_status_data)

    def __clear_fd_percpu(self):
        self.extern_lib.clear_memory()

    def __get_cpu_family_model(self):
        fms = self.extern_lib.get_family_model()
        self.family = (fms >> 8) & 0xF
        self.model = (fms >> 4) & 0xF
        if self.family == 0xF:
            self.family += (fms >> 20) & 0xFF
        if self.family >= 6:
            self.model += ((fms >> 16) & 0xF) << 4
        LOGGER.info("CPU family is %d, model is %d" % (self.family, self.model))

    def __get_cpu_base_freq_mhz(self):
        bclk = self.__discover_bclk()
        base_ratio = (self.extern_lib.get_msr(self.base_cpu, msr.MSR_PLATFORM_INFO) >> 8) & 0xFF
        self.cpu_basefreq_mhz = base_ratio * bclk
        LOGGER.info("Base frequency is %.2f MHz" % self.cpu_basefreq_mhz)

    def __is_turbo_enable(self):
        try:
            self.turbo_is_enable = util.file_read("/sys/devices/system/cpu/intel_pstate/no_turbo") == 0
        except FileNotFoundError:
            self.turbo_is_enable = False

    def __get_cpu_turbo_freq_mhz(self):
        self.__is_turbo_enable()
        if self.turbo_is_enable:
            ratio = (self.extern_lib.get_msr(self.base_cpu, msr.MSR_TURBO_RATIO_LIMIT) >> 56) & 0xFF
            bclk = self.__discover_bclk()
            self.cpu_turbofreq_mhz = ratio * bclk
            LOGGER.info("Turbo frequency is %.2f MHz" % self.cpu_turbofreq_mhz)
        else:
            LOGGER.info("Turbo boost is disabled, can't get cpu turbo frequency.")
            self.cpu_turbofreq_mhz = self.cpu_basefreq_mhz

    def __get_cpu_tdp(self):
        for package in self.host_topo.package_set:
            cpu_tdp_uwatt = int(util.file_read("/sys/class/powercap/intel-rapl/intel-rapl:%s/"
                                               "constraint_0_max_power_uw"
                                               % str(package)))
            self.cpu_tdp_watt[package] = cpu_tdp_uwatt / WATT_TO_UWATT
            LOGGER.info("The TDP of package %d is %d W" % (package, self.cpu_tdp_watt.get(package)))

    def __get_rapl_energy_unit(self):
        rapl_unit = self.extern_lib.get_msr(self.base_cpu, msr.MSR_RAPL_POWER_UNIT)
        rapl_energy_units_reciprocal = (1 << (rapl_unit >> 8 & 0x1F))
        if not rapl_energy_units_reciprocal:
            raise OSError

        if self.model == INTEL_FAM6_ATOM_SILVERMONT:
            self.rapl_energy_units = 1.0 / rapl_energy_units_reciprocal / 100000
        else:
            self.rapl_energy_units = 1.0 / rapl_energy_units_reciprocal
        LOGGER.info("RAPL energy units is %.6f Joules" % self.rapl_energy_units)

    def __check_has_aperf(self):
        if self.extern_lib.check_has_aperf():
            self.__get_aperf_mperf_multiplier()
            LOGGER.info("The aperf_mperf_multiplier is %d" % self.aperf_mperf_multiplier)
        else:
            LOGGER.error("The host doesn't have aperf register so that can't get CPU frequency.")
            raise OSError

    def __get_aperf_mperf_multiplier(self):
        if self.__is_knl():
            self.aperf_mperf_multiplier = 1024
        else:
            self.aperf_mperf_multiplier = 1

    def __discover_bclk(self):
        if self.__has_snb_msrs() or self.__is_knl():
            return 100.00
        if self.__is_slm():
            return self.__slm_bclk()
        return 133.33

    def __has_snb_msrs(self):
        snb_model = ('INTEL_FAM6_SANDYBRIDGE', 'INTEL_FAM6_SANDYBRIDGE_X',
                     'INTEL_FAM6_IVYBRIDGE', 'INTEL_FAM6_IVYBRIDGE_X',
                     'INTEL_FAM6_HASWELL', 'INTEL_FAM6_HASWELL_X',
                     'INTEL_FAM6_HASWELL_L', 'INTEL_FAM6_HASWELL_G',
                     'INTEL_FAM6_BROADWELL', 'INTEL_FAM6_BROADWELL_G',
                     'INTEL_FAM6_BROADWELL_X', 'INTEL_FAM6_SKYLAKE_L',
                     'INTEL_FAM6_CANNONLAKE_L', 'INTEL_FAM6_SKYLAKE_X',
                     'INTEL_FAM6_ICELAKE_X', 'INTEL_FAM6_ATOM_GOLDMONT',
                     'INTEL_FAM6_ATOM_GOLDMONT_PLUS', 'INTEL_FAM6_ATOM_GOLDMONT_D',
                     'INTEL_FAM6_ATOM_TREMONT', 'INTEL_FAM6_ATOM_TREMONT_D')

        if self.model in intel.INTEL_NUMTOMODEL_DICT:
            if intel.INTEL_NUMTOMODEL_DICT.get(self.model) in snb_model:
                return True
        else:
            LOGGER.error("Unknown cpu model : %d" % self.model)
        return False

    def __is_knl(self):
        knl_model = 'INTEL_FAM6_XEON_PHI_KNL'

        if self.model in intel.INTEL_NUMTOMODEL_DICT:
            if intel.INTEL_NUMTOMODEL_DICT.get(self.model) in knl_model:
                return True
        else:
            LOGGER.error("Unknown cpu model : %d" % self.model)
        return False

    def __is_slm(self):
        slm_model = ('INTEL_FAM6_ATOM_SILVERMONT', 'INTEL_FAM6_ATOM_SILVERMONT_D')

        if self.model in intel.INTEL_NUMTOMODEL_DICT:
            if intel.INTEL_NUMTOMODEL_DICT.get(self.model) in slm_model:
                return True
        else:
            LOGGER.error("Unknown cpu model : %d" % self.model)
        return False

    def __slm_bclk(self):
        slm_freq_table = [83.3, 100.0, 133.3, 116.7, 80.0]

        index = self.extern_lib.get_msr(self.base_cpu, msr.MSR_FSB_FREQ) & 0xf
        if index >= len(slm_freq_table):
            LOGGER.info("SLM BCLK[%d] is invalid" % index)
            index = 3

        return slm_freq_table[index]
