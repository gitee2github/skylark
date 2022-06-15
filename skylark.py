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
Description: This file is used for skylark main framework
"""
# @code

from __future__ import division

import atexit
import fcntl
import os
import platform
import signal
import stat
import subprocess
import sys

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR
import libvirt

from data_collector.datacollector import DataCollector
from data_collector.msrlibrary import MsrLibrary
from logger import LOGGER
from qos_analyzer.poweranalyzer import PowerAnalyzer
from qos_controller.cpucontroller import CpuController
from qos_controller.netcontroller import NetController
from qos_controller.cachembwcontroller import CacheMBWController
import util

QOS_MANAGER_ENTRY = None
LIBVIRT_URI = None
LIBVIRT_CONN = None
LIBVIRT_DRIVE_TYPE = None
PID_FILE = None
MSR_PATH = "/dev/cpu/0/msr"
PID_FILE_NAME = "/var/run/skylarkd.pid"

STATE_TO_STRING = ['VIR_DOMAIN_EVENT_DEFINED',  'VIR_DOMAIN_EVENT_UNDEFINED',
                   'VIR_DOMAIN_EVENT_STARTED',  'VIR_DOMAIN_EVENT_SUSPENDED',
                   'VIR_DOMAIN_EVENT_RESUMED',  'VIR_DOMAIN_EVENT_STOPPED',
                   'VIR_DOMAIN_EVENT_SHUTDOWN', 'VIR_DOMAIN_EVENT_PMSUSPENDED',
                   'VIR_DOMAIN_EVENT_CRASHED',  'VIR_DOMAIN_EVENT_LAST']


class QosManager:
    def __init__(self, vir_conn):
        self.vir_conn = vir_conn
        self.data_collector = DataCollector()
        self.scheduler = BackgroundScheduler(logger=LOGGER)
        self.power_analyzer = PowerAnalyzer()
        self.cpu_controller = CpuController()
        self.net_controller = NetController()
        self.cachembw_controller = CacheMBWController()

    def scheduler_listener(self, event):
        if event.exception:
            self.scheduler.remove_all_jobs()

    def init_scheduler(self):
        self.scheduler.add_job(self.__do_power_manage, trigger='interval', seconds=1, id='do_power_manage')
        self.scheduler.add_listener(self.scheduler_listener, EVENT_JOB_ERROR)

    def init_data_collector(self):
        self.data_collector.set_static_base_info()
        self.data_collector.set_static_power_info()

    def init_qos_analyzer(self):
        self.power_analyzer.set_hotspot_threshold(self.data_collector)

    def init_qos_controller(self):
        self.cpu_controller.set_low_priority_cgroup()
        self.cachembw_controller.init_cachembw_controller(self.data_collector.host_info.resctrl_info)
        atexit.register(self.cpu_controller.reset_domain_bandwidth, self.data_collector.guest_info)
        self.net_controller.init_net_controller()

    def start_scheduler(self):
        self.scheduler.start()

    def reset_data_collector(self):
        self.scheduler.pause()
        self.data_collector.reset_base_info(self.vir_conn)
        self.data_collector.reset_power_info()
        self.scheduler.reschedule_job('do_power_manage', trigger='interval', seconds=1)
        self.scheduler.resume()

    def __do_power_manage(self):
        self.data_collector.update_base_info(self.vir_conn)
        self.data_collector.update_power_info()
        self.power_analyzer.power_manage(self.data_collector, self.cpu_controller)


def create_pid_file():
    global PID_FILE

    fd = os.open(PID_FILE_NAME, os.O_RDWR | os.O_CREAT, stat.S_IRUSR | stat.S_IWUSR)
    os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
    os.close(fd)
    try:
        PID_FILE = open(PID_FILE_NAME, 'w')
    except IOError:
        LOGGER.error("Failed to open pid file")
        exit(1)

    try:
        fcntl.flock(PID_FILE.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        LOGGER.error("A running service instance already creates the pid file! This service will exit!")
        os._exit(0)

    process_pid = os.getpid()
    PID_FILE.seek(0)
    PID_FILE.truncate()
    PID_FILE.write(str(process_pid))
    PID_FILE.flush()


def remove_pid_file():
    if PID_FILE is not None:
        PID_FILE.close()
        util.remove_file(PID_FILE.name)


def register_callback_event(conn, event_id, callback_func, opaque):
    if conn is not None and event_id >= 0:
        try:
            return conn.domainEventRegisterAny(None, event_id, callback_func, opaque)
        except libvirt.libvirtError as error:
            LOGGER.warning("Register event exception %s" % str(error))
    return -1


def deregister_callback_event(conn, callback_id):
    if conn is not None and callback_id >= 0:
        try:
            conn.domainEventDeregisterAny(callback_id)
        except libvirt.libvirtError as error:
            LOGGER.warning("Deregister event exception %s" % str(error))


def event_lifecycle_callback(conn, dom, event, detail, opaque):
    LOGGER.info("Occur lifecycle event: domain %s(%d) state changed to %s" % (
                dom.name(), dom.ID(), STATE_TO_STRING[event]))
    vm_started = (event == libvirt.VIR_DOMAIN_EVENT_STARTED)
    vm_stopped = (event == libvirt.VIR_DOMAIN_EVENT_STOPPED)
    if vm_started or vm_stopped:
        QOS_MANAGER_ENTRY.reset_data_collector()
        if vm_started:
            QOS_MANAGER_ENTRY.cachembw_controller.domain_updated(dom,
                                QOS_MANAGER_ENTRY.data_collector.guest_info)
    return 0


def event_device_added_callback(conn, dom, dev_alias, opaque):
    device_name = str(dev_alias[0:4])
    if device_name == "vcpu":
        LOGGER.info("Occur device added event: domain %s(%d) add vcpu" % (dom.name(), dom.ID()))
        QOS_MANAGER_ENTRY.reset_data_collector()
        QOS_MANAGER_ENTRY.cachembw_controller.domain_updated(dom,
                            QOS_MANAGER_ENTRY.data_collector.guest_info)


def event_device_removed_callback(conn, dom, dev_alias, opaque):
    device_name = str(dev_alias[0:4])
    if device_name == "vcpu":
        LOGGER.info("Occur device removed event: domain %s(%d) removed vcpu" % (dom.name(), dom.ID()))
        QOS_MANAGER_ENTRY.reset_data_collector()


def sigterm_handler(signo, stack):
    sys.exit(0)


def func_daemon():
    global LIBVIRT_CONN
    global QOS_MANAGER_ENTRY

    event_lifecycle_id = -1
    event_device_added_id = -1
    event_device_removed_id = -1

    signal.signal(signal.SIGTERM, sigterm_handler)
    signal.signal(signal.SIGABRT, sigterm_handler)

    @atexit.register
    def daemon_exit_func():
        deregister_callback_event(LIBVIRT_CONN, event_lifecycle_id)
        deregister_callback_event(LIBVIRT_CONN, event_device_added_id)
        deregister_callback_event(LIBVIRT_CONN, event_device_removed_id)
        LIBVIRT_CONN.close()
        remove_pid_file()

    create_pid_file()

    try:
        if libvirt.virEventRegisterDefaultImpl() < 0:
            LOGGER.error("Failed to register event implementation!")
            sys.exit(1)
    except libvirt.libvirtError:
        LOGGER.error("System internal error!")
        sys.exit(1)

    LOGGER.info("Try to open libvirtd connection")
    try:
        LIBVIRT_CONN = libvirt.open(LIBVIRT_URI)
    except libvirt.libvirtError:
        LIBVIRT_CONN = None
        LOGGER.error("System internal error, failed to open libvirtd connection!")
        sys.exit(1)

    LOGGER.info("QoS management started.")
    QOS_MANAGER_ENTRY = QosManager(LIBVIRT_CONN)
    QOS_MANAGER_ENTRY.init_scheduler()
    QOS_MANAGER_ENTRY.init_data_collector()
    QOS_MANAGER_ENTRY.init_qos_analyzer()
    QOS_MANAGER_ENTRY.init_qos_controller()
    QOS_MANAGER_ENTRY.start_scheduler()

    event_lifecycle_id = register_callback_event(LIBVIRT_CONN,
                                                 libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE,
                                                 event_lifecycle_callback, QOS_MANAGER_ENTRY)
    event_device_added_id = register_callback_event(LIBVIRT_CONN,
                                                    libvirt.VIR_DOMAIN_EVENT_ID_DEVICE_ADDED,
                                                    event_device_added_callback, QOS_MANAGER_ENTRY)
    event_device_removed_id = register_callback_event(LIBVIRT_CONN,
                                                      libvirt.VIR_DOMAIN_EVENT_ID_DEVICE_REMOVED,
                                                      event_device_removed_callback, QOS_MANAGER_ENTRY)
    if event_lifecycle_id < 0 or event_device_added_id < 0 or event_device_removed_id < 0:
        LOGGER.error("Failed to register libvirt event %d, %d, %d"
                     % (event_lifecycle_id, event_device_added_id, event_device_removed_id))
        sys.exit(1)

    LOGGER.info("Libvirtd connected and libvirt event registered.")

    while LIBVIRT_CONN.isAlive():
        if not QOS_MANAGER_ENTRY.scheduler.get_jobs():
            LOGGER.error("The Scheduler detects an exception, process will exit!")
            break
        try:
            if libvirt.virEventRunDefaultImpl() < 0:
                LOGGER.warning("Failed to run event loop")
                break
        except libvirt.libvirtError as error:
            LOGGER.warning("Run libvirt event loop failed: %s" % str(error))
            break
    sys.exit(1)


def create_daemon():
    try:
        pid = os.fork()
    except OSError as error:
        LOGGER.error('Fork daemon process failed: %d (%s)' % (error.errno, error.strerror))
        os._exit(1)
    else:
        if pid:
            os._exit(0)
        os.chdir('/')
        os.umask(0)
        os.setsid()
        func_daemon()


def setup_vm_env():
    global LIBVIRT_DRIVE_TYPE
    global LIBVIRT_URI

    conn = None
    try:
        conn = libvirt.open()
    except libvirt.libvirtError:
        if not conn:
            LOGGER.error("Can't connect libvirtd!")
        else:
            LOGGER.error("Can't get VMM type")
            conn.close()
        os._exit(1)
    else:
        LIBVIRT_DRIVE_TYPE = conn.getType()
        conn.close()
        if LIBVIRT_DRIVE_TYPE == 'QEMU':
            LIBVIRT_URI = 'qemu:///system'
        else:
            LOGGER.error('Unknown VMM type {}!'.format(LIBVIRT_DRIVE_TYPE))
            os._exit(0)
        LOGGER.info('The VMM type is {}'.format(LIBVIRT_DRIVE_TYPE))


def check_dev_msr():
    try:
        os.stat(MSR_PATH)
    except FileNotFoundError:
        child = subprocess.Popen(["/sbin/modprobe", "msr"])
        child.communicate(timeout=5)
        if child.returncode:
            LOGGER.error("No /dev/cpu/0/msr and failed to execute modprobe msr!")
            os._exit(0)

    if not os.access(MSR_PATH, os.R_OK):
        LOGGER.error(MSR_PATH + " open failed, try chown or chmod +r "
                                "/dev/cpu/*/msr")
        if os.getuid() != 0:
            LOGGER.error("Or simply run skylark as root.")
        os._exit(0)


def check_os_platform():
    if platform.system() != "Linux":
        LOGGER.warning("Skylark only supports linux platform.")
        os._exit(0)


def check_cpu_arch():
    extern_lib = None
    genuine_intel = 0

    child = subprocess.Popen(["/usr/bin/uname", "-a"], stdout=subprocess.PIPE)
    ret = child.communicate(timeout=5)[0].decode().find('x86')
    child.stdout.close()
    if ret == -1:
        LOGGER.warning("Skylark only supports x86 architecture.")
        os._exit(0)

    try:
        extern_lib = MsrLibrary()
    except OSError as error:
        LOGGER.error(str(error))
        os._exit(1)

    if extern_lib:
        genuine_intel = extern_lib.get_cpu_microarch()
    if not genuine_intel:
        LOGGER.warning("Skylark only supports Intel architecture.")
        os._exit(0)


def main():
    check_os_platform()
    check_cpu_arch()
    check_dev_msr()
    setup_vm_env()
    create_daemon()


if __name__ == '__main__':
    main()
