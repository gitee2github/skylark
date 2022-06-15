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
Description: This file is used for providing a data collector.
"""
# @code

import data_collector.hostinfo as hostinfo
import data_collector.guestinfo as guestinfo


class DataCollector:
    def __init__(self):
        self.host_info = hostinfo.HostInfo()
        self.guest_info = guestinfo.GuestInfo()

    def set_static_base_info(self):
        self.host_info.set_host_base_attribute()

    def set_static_power_info(self):
        self.host_info.set_host_power_attribute()

    def reset_base_info(self, vir_conn):
        self.guest_info.clear_guest_info()
        self.guest_info.update_guest_info(vir_conn, self.host_info.host_topo)

    def reset_power_info(self):
        self.host_info.update_host_power_info()

    def update_base_info(self, vir_conn):
        self.guest_info.update_guest_info(vir_conn, self.host_info.host_topo)

    def update_power_info(self):
        self.host_info.update_host_power_info()
