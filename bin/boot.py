#!/usr/bin/env python

import os
import sys
import json
import setup

version = sys.argv[1]

local = setup.Local("/opt/klot-io/boot")

local.create("version", f"klot-io-pi-{version}")

local.directory("config")
local.copy("config/account.yaml")
local.copy("config/network.yaml")

local.directory("kubernetes")
local.copy("kubernetes/klot-io-app-crd.yaml")
local.copy("kubernetes/klot-io-apps.yaml")

local.copy("requirements.txt", "requirements.txt")

local.directory("lib")
local.copy("lib/manage.py")
local.copy("lib/config.py")
local.copy("lib/name.py")

local.directory("etc")
local.copy("etc/nginx.conf")
local.copy("etc/rpi.conf")

local.copytree("www")

local.directory("bin")
local.copy("bin/wifi.sh")
local.copy("bin/tmpfs.sh")
local.copy("bin/k3s.sh")
local.copy("bin/klot-io.sh")
local.copy("bin/api.py")
local.copy("bin/daemon.py")
local.copy("bin/dns.py")
local.copy("bin/docker.sh")

local.directory("service")
local.copy("service/klot-io-api.service")
local.copy("service/klot-io-daemon.service")
local.copy("service/klot-io-dns.service")

local.replace("config.txt", [
    ("#hdmi_force_hotplug=1", "hdmi_force_hotplug=1"),
    ("#hdmi_group=1", "hdmi_group=2"),
    ("#hdmi_mode=1", "hdmi_mode=68")
])
local.append("config.txt", "enable_uart=1")
local.append("config.txt", "max_usb_current=1")
local.options("cmdline.txt", [
    'cgroup_enable=cpuset',
    'cgroup_enable=memory',
    'cgroup_memory=1'
])
