#!/usr/bin/env python

import os
import sys
import json
import firmware

version = sys.argv[1]

local = firmware.Local("/opt/clot-io/boot")

local.create("version", f"clot-io-pi-{version}")

local.directory("config")
local.copy("config/account.yaml")
local.copy("config/network.yaml")
local.copy("config/kube-flannel.yml")

local.copy("requirements.txt")

local.directory("bin")
local.copy("bin/wifi.sh")
local.copy("bin/tmpfs.sh")
local.copy("bin/kubernetes.sh")
local.copy("bin/images.sh")
local.copy("bin/clot-io.sh")
local.copy("bin/daemon.py")

local.directory("service")
local.copy("service/clot-io-daemon.service")

local.replace("config.txt", [
    ("#hdmi_force_hotplug=1", "hdmi_force_hotplug=1"),
    ("#hdmi_group=1", "hdmi_group=2"),
    ("#hdmi_mode=1", "hdmi_mode=68")
])
local.append("config.txt", "enable_uart=1")
local.options("cmdline.txt", [
    'cgroup_enable=cpuset',
    'cgroup_enable=memory',
    'cgroup_memory=1'
])
