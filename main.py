#!/usr/bin/python
# -*- coding: UTF-8 -*-

import logging
import devInfo
import iDock
import time


logging.basicConfig(level=logging.INFO)

device = []

if __name__ == '__main__':

    _dev_array = devInfo.get_dev()
    # 延时等待网络等就绪
    # time.sleep(10)
    for _dev in _dev_array:
        device.append(iDock.BaseDevice(
            _dev['port'],
            _dev['baudrate'],
            _dev['DeviceName'],
            devInfo.get_time()['reconnect'],
            devInfo.get_time()['telemetry'],
            _dev['connectionString']))
        logging.info("dev : %s installed !" % str(_dev['DeviceName']))
        device[-1].update()
        # device[-1].reconnect()
