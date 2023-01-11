import enum
import click
import time
import usb.core
import usb.util
import struct

class Handle:
    def __init__(self, vid, pid):
        self.handle = usb.core.find(idVendor = vid, idProduct = pid)

        try:
            cfg = self.handle.get_active_configuration()
            cfgno = cfg.bConfigurationValue
        except:
            cfgno = 0
        if cfgno == 0:
            self.handle.set_configuration(1)
        cfg = self.handle.get_active_configuration()
        self.intf = None

    def interface_open(self):
        if self.intf is not None:
            return

        try:
            self.handle.detach_kernel_driver(0)
        except:
            pass
        
        for intf in cfg:
            if intf.bInterfaceClass == 0xfe and \
               intf.bInterfaceSubClass == 0x03 and \
               intf.bInterfaceProtocol == 0x01:
                self.intf = intf
                break

        usb.util.claim_interface(self.handle, self.intf)

        self.ep_in = usb.util.find_descriptor(
            self.intf,
            custom_match = lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) ==
            usb.util.ENDPOINT_IN)
        self.ep_out = usb.util.find_descriptor(
            self.intf,
            custom_match = lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) ==
            usb.util.ENDPOINT_OUT)

    def control(self, bmRequestType, bRequest, wIndex, wValue, data_or_wLength):
        v = self.handle.ctrl_transfer(bmRequestType, bRequest = bRequest,
                                      wIndex = wIndex,
                                      wValue = wValue,
                                      data_or_wLength = data_or_wLength)
        if isinstance(data_or_wLength, int):
            v = bytes(v)
        return v

    def bulk_read(self):
        self.interface_open()
        data = self.handle.read(self.ep_in.bEndpointAddress, self.ep_in.wMaxPacketSize)
        return bytes(data)
    
    def bulk_write(self, data):
        self.interface_open()
        return self.handle.write(self.ep_out.bEndpointAddress, data)

    def internal_config_set(self, k, v, legacy = False):
        if legacy:
            self.interface_open()
            status = self.control(0xa1, 0x40, 0, 0, 1)
            print(f"Status: {status.hex()}")
            self.bulk_write(f"!{k:02x}{v:02x}".encode("ascii"))
            print(f"Parameter {k:#04x} set to {v:#04x}")
        else:
            self.control(bmRequestType = 0x40,
                         bRequest = 0,
                         wIndex = k,
                         wValue = v,
                         data_or_wLength = b'')

    def internal_config_get(self, k):
        value = self.control(bmRequestType = 0xc0,
                             bRequest = 0,
                             wIndex = k,
                             wValue = 0, data_or_wLength = 1)
        return value[0]

    @staticmethod
    def cmd_pack(command, tag = 1, eom = 1):
        command = command.encode("ascii")
        size = len(command)
        return (
            struct.pack("BBBx", 1, tag, ~tag & 0xFF)
            + struct.pack("<LBxxx", size, eom)
            + command
            + b"\0" * ((4 - size) % 4)
        )

    def cmd_write(self, cmd, tag = 2):
        data = self.cmd_pack(cmd, tag = tag)
        return self.bulk_write(data)

@click.group()
def group():
    pass

class ConfigItem(enum.IntEnum):
    AutoId = 0
    LineTerm = 1

class LineTerm(enum.IntEnum):
    EOI = 0 # Handshake only
    CR = 1 # \r
    LF = 2 # \n

class AutoId(enum.IntEnum):
    Enabled = 0
    Disabled = 1

@group.command()
@click.argument("mode", type = str)
@click.option("--vid", type = int, default = 0x3eb)
@click.option("--pid", type = int, default = 0x2065)
def line_term(mode, vid, pid):
    """
    Set line term mode

    Mode may be EOI, CR, LF or raw integer value
    """
    d = Handle(vid, pid)
    try:
        value = int(mode)
        value = LineTerm(value)
    except ValueError:
        value = None
    if value is None:
        value = LineTerm[mode]
    d.internal_config_set(ConfigItem.LineTerm, value)

@group.command()
@click.argument("mode", type = str)
@click.option("--vid", type = int, default = 0x3eb)
@click.option("--pid", type = int, default = 0x2065)
def auto_id(mode, vid, pid):
    """
    Set auto ID feature
    
    mode may be Enabled, on, true or raw integer value (active = 0)
    """
    value = AutoId.Enabled if mode.lower() in ["on", "true", "enabled"] else AutoId.Disabled
    d = Handle(vid, pid)
    d.internal_config_set(ConfigItem.AutoId, value)

@group.command()
@click.option("--vid", type = int, default = 0x3eb)
@click.option("--pid", type = int, default = 0x2065)
def info(vid, pid):
    """
    Retrieve information about configuration of device
    """
    d = Handle(vid, pid)
    auto_id_value = d.internal_config_get(ConfigItem.AutoId)
    line_term_value = d.internal_config_get(ConfigItem.LineTerm)
    print(f"Auto ID: {AutoId(auto_id_value).name}")
    print(f"Line Term: {LineTerm(line_term_value).name}")

if __name__ == "__main__":
    group()
