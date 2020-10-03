#!/usr/bin/python
# -*- coding: UTF-8 -*-
import datetime
import pytz
import serial
import modbus_tk.defines as cst
from modbus_tk import modbus_rtu
import logging
from threading import Timer
import struct
from azure.iot.device import IoTHubDeviceClient, Message
import json

class BaseDevice(object):

    def __init__(self,
                 port,
                 baudrate,
                 name,
                 reconnect_period,
                 update_period,
                 connection_string):
        self.name = name
        try:
            self.mb_client = modbus_rtu.RtuMaster(serial.Serial(port=port,
                                                                baudrate=baudrate,
                                                                bytesize=8,
                                                                parity='N',
                                                                stopbits=1,
                                                                xonxoff=0))
            self.mb_client.set_timeout(5.0)
            self.mb_client.set_verbose(True)
        except Exception as e:
            logging.error(str(e))
        try:
            self.iothub_client = IoTHubDeviceClient.create_from_connection_string(connection_string)
        except Exception as e:
            logging.error(str(e))
        self.reconnect_period = reconnect_period
        self.update_period = update_period
        self.result = 0
        self.float_ele_number = 12
        self.char_ele_number = 8
        self.short_ele_number = 1

    def update(self):
        buf = []
        vin = []
        din = []
        for i in range(self.float_ele_number * 4 + self.char_ele_number):
            buf.append(0)
        for i in range(self.float_ele_number):
            vin.append(0)
        for i in range(self.char_ele_number):
            din.append(0)
        try:
            temp_word2read = self.float_ele_number * 2 + self.char_ele_number / 2 + self.short_ele_number
            rsp_ = self.mb_client.execute(1,
                                          cst.READ_HOLDING_REGISTERS,
                                          0,
                                          int(temp_word2read))
            logging.debug(rsp_)
            # 将读取的tuple 转换为 list 每元素2bytes
            temp_list = list(tuple(rsp_))
            # 拆解2 bytes的list为1 byte的list(float 排序)
            for i in range(self.float_ele_number):
                buf[i * 4 + 1] = temp_list[i * 2 + 1].to_bytes(2, 'little')[0]
                buf[i * 4 + 0] = temp_list[i * 2 + 1].to_bytes(2, 'little')[1]
                buf[i * 4 + 3] = temp_list[i * 2].to_bytes(2, 'little')[0]
                buf[i * 4 + 2] = temp_list[i * 2].to_bytes(2, 'little')[1]
            for i in range(int(self.char_ele_number / 2)):
                din[i * 2 + 0] = temp_list[i + self.float_ele_number * 2].to_bytes(2, 'little')[0]
                din[i * 2 + 1] = temp_list[i + self.float_ele_number * 2].to_bytes(2, 'little')[1]
            dev_address = temp_list[int(self.float_ele_number * 2 + self.char_ele_number / 2)]

            # 将byte list转换为bytes
            temp_bytes = bytes(buf)
            # bytes 转换为 float
            for i in range(self.float_ele_number):
                vin[i] = struct.unpack_from('>f', temp_bytes, i * 4)[0]
            utc_tz = pytz.timezone('UTC')
            msg0 = {
                "U0": format(vin[0], '.3f'),
                "U1": format(vin[1], '.3f'),
                "U2": format(vin[2], '.3f'),
                "U3": format(vin[3], '.3f'),
                "I0": format(vin[4], '.3f'),
                "I1": format(vin[5], '.3f'),
                "I2": format(vin[6], '.3f'),
                "I3": format(vin[7], '.3f'),
                "Status": format(vin[8], '.3f'),
                "ID": str(dev_address),
                "Length": str(0),
                "Speed": str(0),
                "Time": datetime.datetime.now(tz=utc_tz).isoformat(),
                "Type": "Measurement"
            }
            logging.debug(msg0)
            logging.debug(din)
            logging.debug(dev_address)
            try:
                self.iothub_client.send_message(json.dumps(msg0))
            except Exception as e:
                logging.error(str(e))
        except:
            print('dev : %s read reg error' % self.name)
        t = Timer(self.update_period, self.update)
        t.start()
