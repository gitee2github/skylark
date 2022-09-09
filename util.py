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
Description: This file is used for providing some utility functions
"""
# @code

import os

from logger import LOGGER


def file_read(file_path):
    try:
        with open(file_path, 'r') as file:
            file_data = file.readline().strip('\n')
        return file_data
    except FileNotFoundError as error:
        LOGGER.error(str(error))
        raise


def file_write(file_path, value, log=True):
    try:
        with open(file_path, 'wb') as file:
            file.truncate()
            file.write(str.encode(value))
    except FileNotFoundError as error:
        if log:
            LOGGER.error(str(error))
        raise


def remove_file(file_path):
    try:
        os.remove(file_path)
    except FileNotFoundError as error:
        LOGGER.error(str(error))
