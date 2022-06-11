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
Description: This file is used for logger
"""
# @code

import logging
import logging.handlers

DEFAULT_LOG_FMT = '%(asctime)s|%(filename)s|%(process)d|%(levelname)s:%(message)s'
DEFAULT_LOG_DATEFMT = '%Y-%m-%d %H:%M:%S'
DEFAULT_LOG_PATH = '/var/log/skylark'


class Logger:
    def __init__(self):
        self._logger = logging.getLogger()
        self._logger.addHandler(self._get_rotate_handler())
        self._logger.setLevel(logging.INFO)

    @staticmethod
    def _get_rotate_handler():
        file_handler = logging.handlers.TimedRotatingFileHandler(filename='{0}.log'.format(DEFAULT_LOG_PATH),
                                                                 when='d', interval=7, backupCount=4)
        formatter = logging.Formatter(fmt=DEFAULT_LOG_FMT, datefmt=DEFAULT_LOG_DATEFMT)
        file_handler.setFormatter(formatter)
        return file_handler

    def logger(self):
        return self._logger


LOGGER = Logger().logger()
