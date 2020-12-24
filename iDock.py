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
            # modbus client
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
            # azure iothub client
            self.iothub_client = IoTHubDeviceClient.create_from_connection_string(connection_string)
        except Exception as e:
            logging.error(str(e))

        self.reconnect_period = reconnect_period
        self.update_period = update_period
        # number of float elements
        self.float_ele_number = 12
        # number of uint8_t elements
        self.char_ele_number = 8
        # number of short(uint16_t) elements
        self.short_ele_number = 1

        # analog input values  (in Volt)
        self.vin = [0] * self.float_ele_number
        # digital io inout status (0 -> off 1 -> flash 2-> on)
        self.din = [0] * self.char_ele_number
        # board card address
        self.address = 0
        # data length (in word) to be read
        self.word2read = self.float_ele_number * 2 + self.char_ele_number / 2 + self.short_ele_number
        # original data from modbus
        self.original_list = [0] * int(self.word2read)
        # machine status
        self.status = 0
        self.status_old = 0
        # weld status
        self.weld_status = 0
        self.weld_status_old = 0
        # weld values
        self.weld_voltage = [0] * 4
        self.weld_current = [0] * 4

    def _read_data2list(self):
        try:
            # read data from hardware
            rsp_ = self.mb_client.execute(1,
                                          cst.READ_HOLDING_REGISTERS,
                                          0,
                                          int(self.word2read))
            logging.debug(rsp_)
            # 将读取的tuple 转换为 list 每元素2bytes
            self.original_list = list(tuple(rsp_))
        except Exception as e:
            logging.error(str(e))

    def _data_decode_vin(self):
        buf = [0] * self.float_ele_number * 4
        # 拆解2 bytes的list为1 byte的list(float 排序)
        try:
            for i in range(self.float_ele_number):
                buf[i * 4 + 1] = self.original_list[i * 2 + 1].to_bytes(2, 'little')[0]
                buf[i * 4 + 0] = self.original_list[i * 2 + 1].to_bytes(2, 'little')[1]
                buf[i * 4 + 3] = self.original_list[i * 2].to_bytes(2, 'little')[0]
                buf[i * 4 + 2] = self.original_list[i * 2].to_bytes(2, 'little')[1]
            # 将byte list转换为bytes
            temp_bytes = bytes(buf)
            # bytes 转换为 float
            for i in range(self.float_ele_number):
                self.vin[i] = struct.unpack_from('>f', temp_bytes, i * 4)[0]
            self.weld_voltage[0] = self.vin[8]
            self.weld_voltage[1] = self.vin[9]
            self.weld_voltage[2] = self.vin[10]
            self.weld_voltage[3] = self.vin[11]
            self.weld_current[0] = self.vin[0] * 50
            self.weld_current[1] = self.vin[1] * 50
            self.weld_current[2] = self.vin[2] * 50
            self.weld_current[3] = self.vin[3] * 50

            if self.weld_current[0] >= 30 or \
                    self.weld_current[1] >= 30 or \
                    self.weld_current[2] >= 30 or \
                    self.weld_current[3] >= 30:
                self.weld_status = 1
            else:
                self.weld_status = 0

        except Exception as e:
            logging.error(str(e))

    def _data_decode_char(self):
        try:
            for i in range(int(self.char_ele_number / 2)):
                self.din[i * 2 + 0] = self.original_list[i + self.float_ele_number * 2].to_bytes(2, 'little')[0]
                self.din[i * 2 + 1] = self.original_list[i + self.float_ele_number * 2].to_bytes(2, 'little')[1]

            # stop and emergency stop
            if self.din[7] != 0:
                self.status = 5
            # auto program and idle
            if self.din[5] == 1:
                self.status = 2
            # auto program and run
            if self.din[5] == 2:
                self.status = 1
            # menu program and idle
            if self.din[6] == 1:
                self.status = 4
            # menu program and run
            if self.din[6] == 2:
                self.status = 3
            # power off
            if self.din[7] == 0 and self.din[6] == 0 and self.din[5] == 0:
                self.status = 0
        except Exception as e:
            logging.error(str(e))

    def _data_decode_address(self):
        try:
            self.address = self.original_list[int(self.float_ele_number * 2 + self.char_ele_number / 2)]
        except Exception as e:
            logging.error(str(e))

    def _send_measure_message(self, time_):
        msg = {
            "U0": format(self.weld_voltage[0], '.3f'),
            "U1": format(self.weld_voltage[1], '.3f'),
            "U2": format(self.weld_voltage[2], '.3f'),
            "U3": format(self.weld_voltage[3], '.3f'),
            "I0": format(self.weld_current[0], '.3f'),
            "I1": format(self.weld_current[1], '.3f'),
            "I2": format(self.weld_current[2], '.3f'),
            "I3": format(self.weld_current[3], '.3f'),
            "Status": str(self.status),
            "WeldStatus": str(self.weld_status),
            "ID": str(self.address),
            "Length": str(0),
            "Speed": str(0),
            "Time": time_,
            "Type": "Measurement"
        }
        logging.info(msg)
        try:
            self.iothub_client.send_message(json.dumps(msg))
        except Exception as e:
            logging.error(str(e))

    def _send_status_message(self, time_):
        if self.status_old != self.status:
            msg = {
                "Status": str(self.status),
                "ID": str(self.address),
                "Time": time_,
                "Type": "StatusChanged"
            }
            logging.info(msg)
            try:
                self.iothub_client.send_message(json.dumps(msg))
            except Exception as e:
                logging.error(str(e))
        self.status_old = self.status

    def _send_weld_status_message(self, time_):
        if self.weld_status != self.weld_status_old:
            msg = {
                "WeldStatus": str(self.weld_status),
                "ID": str(self.address),
                "Time": time_,
                "Type": "WMStatusChanged"
            }
            logging.info(msg)
            try:
                self.iothub_client.send_message(json.dumps(msg))
            except Exception as e:
                logging.error(str(e))
        self.status_old = self.status

    def update(self):
        try:
            utc_tz = pytz.timezone('Asia/Shanghai')
            _time = datetime.datetime.now(tz=utc_tz).isoformat()
            self._read_data2list()
            self._data_decode_vin()
            self._data_decode_char()
            self._data_decode_address()
            self._send_measure_message(_time)
            self._send_status_message(_time)
            self._send_weld_status_message(_time)
        except Exception as e:
            logging.error(str(e))
        t = Timer(self.update_period, self.update)
        t.start()
