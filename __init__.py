# -*- coding: utf-8 -*-
"""
APC PDU Monitor and Control

This module provides monitor and control of the DTO rack's power
distribution unit (PDU) via the Simple (yeah! sure!) Network Management
Protocol (SNMP).

Requirements
============
Besides the Python netsnmp package, it's hard to manage SNMP without the
'snmp' package, which provides command line tools.

Configuration
=============
Management Information Base (MIB) files are used to describe the
managed object IDs (OID).  These files must be on the MIB path, which for
Debian Linux 6 is found by::
  kuiper@dto:/usr/share/mibs/site$ net-snmp-config --default-mibdirs
  /home/kuiper/.snmp/mibs:\
  /usr/share/mibs/site:\
  /usr/share/snmp/mibs:\
  /usr/share/mibs/iana:\
  /usr/share/mibs/ietf:\
  /usr/share/mibs/netsnmp
MIBS must be listed in /etc/snmp/snmp.conf in such an order that
dependencies are satisfied.  On 'dto' the snmp.conf entries are::
  mibs  SNMPv2-SMI
  mibs  PowerNet-MIB
These files must be obtained from the web and usually modified so that
the first line and last lines are, for example::
  PowerNet-MIB DEFINITIONS ::= BEGIN
  ...
  END
In this example "PowerNet-MIB" is also the file name, in this case located
in /usr/share/mibs/site.  The file will have an IMPORTS section which
lists all the MIBS which might be searched before this one.  As it happens,
for now, we only need a definition of 'DisplayString' which comes from
RFC1213-MIB. Alas, that file has so many dependencies that it was easier
to 'steal' the definition and add it here::
  kuiper@dto:/usr/share/mibs/site$ diff PowerNet-MIB-save PowerNet-MIB
  5d4
  <    DisplayString                                        FROM RFC1213-MIB
  8a8,10
  >           DisplayString ::=
  >               OCTET STRING
With that, the two MIBS seem to be sufficient.

To Do
=====
Pending tasks::
 * Trap and handle anomalous conditions (like fan failure)
 * Monitor power usage
"""
import netsnmp
import socket
import logging

module_logger = logging.getLogger(__name__)

default_IP = socket.gethostbyname('pdu')

class PDU(object):
  """
  APC PDU class

  Public Attributes::
    hostname - entry in /etc/hosts
    hostIP   - IP of the PDU
  """
  def __init__(self, hostname=None, hostIP=None, name=None):
    """
    Create a PDU instance

    @param hostname : optional, has priority over hostIP
    @type  hostname : str

    @param hostIP : defaults to IP address of 'pdu'
    @type  hostIP : str
    """
    self.logger = logging.getLogger(__name__+".PDU")
    if hostname:
      self.hostname = hostname
      self.hostIP = socket.gethostbyname(self.hostname)
    elif hostIP:
      self.hostIP = hostIP
      self.hostname = socket.gethostbyaddr(hostIP)[0]
    else:
      self.hostIP = default_IP
      self.hostname = socket.gethostbyaddr(default_IP)[0]
    self.logger.debug("Host %s", self.hostname)
    self.logger.debug("IP %s", self.hostIP)
    if name:
      self.set_name(name)
    self._get_ident()

  def __repr__(self):
    """
    Text for object
    """
    return("%s %s, ser. %s, h/w rev. %s, f/w %s, made %s" %
           (self.name, self.model, self.serial, self.hw_rev, self.fw_rev,
            self.date))

  def _get_var(self,var):
    """
    Get OID data
    """
    return netsnmp.snmpget(var,
                           Version = 2,
                           DestHost =self.hostIP,
                           Community='public')

  def _get_ident(self):
    """
    Get identifying information
    """
    var = netsnmp.Varbind(tag="sPDUIdentModelNumber",iid='0')
    self.model = self._get_var(var)[0]
    var = netsnmp.Varbind("sPDUIdentSerialNumber", iid='0')
    self.serial = self._get_var(var)[0]
    var = netsnmp.Varbind("sPDUIdentHardwareRev", iid='0')
    self.hw_rev = self._get_var(var)[0]
    var = netsnmp.Varbind("sPDUIdentFirmwareRev", iid='0')
    self.fw_rev = self._get_var(var)[0]
    var = netsnmp.Varbind("sPDUIdentDateOfManufacture", iid='0')
    self.date = self._get_var(var)[0]
    var = netsnmp.Varbind("sPDUMasterConfigPDUName", iid='0')
    self.name = self._get_var(var)[0]

  def set_name(self, name):
    """
    Set the PDU name
    """
    netsnmp.Varbind(tag="sPDUMasterConfigPDUName",
                    iid='0',
                    val=name,
                    type='STRING')
    return netsnmp.snmpset(namevar,
                           Version = 2,
                           DestHost = self.hostIP,
                           Community='private')
  
  def get_outlet_states(self):
    """
    Get the states of all the outlets
    """
    var = netsnmp.Varbind(tag="sPDUMasterState",iid='0')
    response = self._get_var(var)
    return response[0].split()

  def get_pending(self):
    """
    Get outlets with pending actions
    """
    var = netsnmp.Varbind(tag="sPDUMasterPending",iid='0')
    response = self._get_var(var)
    return response[0].split()

  def get_outlet_names(self):
    """
    Report the names of all the outlets
    """
    var = netsnmp.Varbind(tag="sPDUOutletConfigTableSize",iid='0')
    num_switches = self._get_var(var)[0]
    OIDbase = 'sPDUOutletCtlName'
    names = {}
    for n in range(int(num_switches)):
      index = n+1
      namevar = netsnmp.Varbind(tag=OIDbase,
                                iid=str(index))
      names[index] = netsnmp.snmpget(namevar,
                                     Version = 2,
                                     DestHost = self.hostIP,
                                     Community='public')[0]
    return names

  def set_outlet_names(self, namelist):
    """
    Set the names of all the outlets
    """
    var = netsnmp.Varbind(tag="sPDUOutletConfigTableSize",iid='0')
    num_switches = int(self._get_var(var)[0])
    if len(namelist) != num_switches:
      self.logger.error("set_outlet_names: requires %d names", num_switches)
      raise RuntimeError("Incorrect number of names.")
    result = {}
    OIDbase = 'sPDUOutletName'
    for n in range(int(num_switches)):
      index = n+1
      namevar = netsnmp.Varbind(tag=OIDbase,
                                iid=str(index),
                                val=namelist[n])
      result[index] = bool(netsnmp.snmpset(namevar,
                                           Version = 2,
                                           DestHost = self.hostIP,
                                           Community='private'))
    return result
    
class Outlet(object):
  """
  Power outlet on an APC PDU

  Class variable::
    state - text describing the outlet state
    
  Public attributes::
    pdu    - PDU instance
    number - outlet number
    name   - outlet name
    state  - outlet state
    status - text version of 'state'

  Public methods::
    get_name  - query the PDU for the outlet's name
    get_state - query the PDU for the outlet's state
  """
  state = {1: 'on',
           2: 'off',
           3: 'rebooting',
           4: 'error'}
  def __init__(self, pdu, number, name=None):
    """
    Create an Outlet instance.

    @param pdu : PDU to which the outlet belongs
    @type  pdu : PDU instance

    @param number : outlet number
    @type  number : int
    """
    self.pdu = pdu
    self.number = str(number)
    self.get_name()
    self.logger = logging.getLogger(__name__+self.name)
    self.get_state()
    
  def get_name(self):
    """
    Set the 'name' attribute and return it.
    """
    OIDbase = 'sPDUOutletCtlName'
    namevar = netsnmp.Varbind(tag=OIDbase,
                              iid=str(self.number))
    self.name = netsnmp.snmpget(namevar,
                                Version = 2,
                                DestHost = self.pdu.hostIP,
                                Community='public')[0]
    return self.name

  def set_name(self,name):
    """
    Change the outlet's name
    """
    OIDbase = 'sPDUOutletName'
    namevar = netsnmp.Varbind(tag=OIDbase,
                              iid=str(self.number),
                              val=name,
                              type='STRING')
    result = netsnmp.snmpset(namevar,
                             Version = 2,
                             DestHost = self.pdu.hostIP,
                             Community='private')
    self.get_name()
    return bool(result)

  def get_state(self):
    """
    Set the 'state' attribute and return it.

    @return: (numeric state, status text)
    """
    OIDbase = 'sPDUOutletCtl'
    statvar = netsnmp.Varbind(OIDbase, str(self.number))
    self.state = int(netsnmp.snmpget(statvar,
                                     Version = 2,
                                     DestHost = self.pdu.hostIP,
                                     Community='public')[0])
    self.status = Outlet.state[self.state]
    return self.state, self.status

  def set_state(self,state):
    """
    Turn the outlet on or off

    @param state : True for 'on', False for 'off'
    @type  state : bool
    """
    OIDbase = 'sPDUOutletCtl'
    self.logger.debug("set_state: called with %s", state)
    if state:
      value = 1
    else:
      value = 2
    self.logger.debug("set_state: to %s",value)
    statvar = netsnmp.Varbind(OIDbase, str(self.number), val=value)
    result = bool(netsnmp.snmpset(statvar,
                                  Version = 2,
                                  DestHost = self.pdu.hostIP,
                                  Community='private'))
    self.get_state()
    return result


DTO_names = ["Rack Fan",    "TCT",    "gpu2 a",   "gpu2 b",       "roach1",
             "PWS USB hub", "SamGen", "roach2",   "Ether-switch", "gpu1 a",
             "gpu1 b",      "KVM",    "host dto", "IF switch",    "spare 15",
             "spare 16",    "tmp: noise gen",
                                      "tmp: amp", "tmp: preamp", "PWS Enet hub",
             "spare 21",    "spare 22","spare 23","spare 24"]