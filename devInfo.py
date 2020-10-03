#!/usr/bin/python
# -*- coding: UTF-8 -*-
import json

# 获取用户设置
setting = json.load(open("/home/pi/pDock/config.json", encoding='utf-8'))


def get_dev():
    return setting['dev']


def get_time():
    return setting['time']

